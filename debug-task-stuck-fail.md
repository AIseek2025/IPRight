[OPEN] task-stuck-fail

# 调试会话

- session_id: `task-stuck-fail`
- 目标任务:
  - `3e7eff84-6a52-455e-8dd5-d6d3a3381772`
  - `c6f9ad0f-8884-456b-bd32-1e1af550aeb8`
- 症状:
  - 旧任务长时间未完成
  - 新任务先排队后失败

# 初始假设

1. Worker 实际卡在某个 stage，状态流仍在推进但前端未及时反映。
2. Worker 在 build/capture/manual 等阶段出现重试型异常，导致任务长期停滞或最终失败。
3. 队列消费正常，但同一任务的运行时依赖缺失或外部调用失败，导致排队中的后续任务在拿到执行权后快速失败。
4. 任务状态机存在异常分支，任务从 `queued` 进入 worker 后未正确写回中间状态或失败原因。
5. 某个共享资源（工作目录、Redis、数据库、MinIO、Playwright、前端构建环境）出现竞争或脏状态，影响连续任务执行。

# 取证计划

1. 查看两个任务的 dashboard / timeline / artifacts / screenshots 返回。
2. 核查 ECS 上 `ipright-api`、`ipright-worker` 日志与队列状态。
3. 必要时查看数据库中的任务状态、错误信息和更新时间。
4. 若现有日志不足，再补最小化插桩日志。

# 已收集证据

- `3e7eff84-6a52-455e-8dd5-d6d3a3381772`
  - Worker 日志显示该任务在 `build` 阶段启动后，`ForkPoolWorker-2` 于 `2026-05-27 11:35:53` 收到 `SIGTERM` 退出，并触发 `WorkerLostError`。
  - 数据库状态仍停留在 `tasks.status=building`、`task_builds.status=running`、`build_stage_runs(stage=build).status=running`，说明中断后没有回收成失败态。
- `c6f9ad0f-8884-456b-bd32-1e1af550aeb8`
  - 数据库与事件表显示该任务进入了 `verify_run`，并非在 `queued` 状态直接失败。
  - 运行目录复现 `npm run build` 后，明确报错：`Could not resolve "../../generated/appProfile" from "src/pages/SalesPage.tsx"`。
  - 说明失败根因是生成页面文件使用了错误的相对导入路径，导致 `verify_run` 的前端构建失败。

# 根因结论

1. Worker 重启/中断时，正在执行的 build 没有被自动回收，导致旧任务永久卡在 `running/building`。
2. 模块页面校验过于宽松，错误的 `../../generated/appProfile` 导入被当成合法输出放行，导致新任务在运行验证阶段失败。
3. 在模块页 `module_invalid_retry` 仍然失败时，现有逻辑没有把模板级 `_render_module_page()` 兜底真正落盘，导致 `3e7...` 后续重试直接在 `build` 阶段因缺失/无效模块页失败。
4. 截图判定对普通业务路由主要只认场景标题；`/statistics` 这类同一路由多标题场景下，页面真实标题为“履约分析与报表”，而另一个场景标题为“冷链监控看板”，因此被误判为空白/不匹配截图。
5. `verify_run` 仅执行 `vite build`，没有运行 `tsc -b`，会让 TypeScript 级错误延后到运行时或截图阶段才暴露。
6. demo seed 前端模板本身存在 TypeScript 质量问题：部分文件混入 Python 三引号，且 `validators.ts` 同时混用了“直接返回错误字符串”和“返回校验函数”两种接口，导致 schema 在 `tsc -b` 下统一报类型错误。

# 已实施修复

1. 在 `workers/stages/build_support.py` 中增加模块页导入路径自愈，把错误的 `../../generated/appProfile` 规范化为 `../generated/appProfile`，并收紧校验规则。
2. 在 `workers/celery_app.py` 中启用 `task_reject_on_worker_lost=True`，让 worker 丢失时任务重新入队。
3. 在 `backend/app/services/__init__.py` 中增加 `recover_interrupted_running_builds()`，worker 启动时自动把上次重启中断的 running build 回收为 failed，并写入事件。
4. 已补充针对性测试覆盖导入路径自愈和中断 build 回收逻辑。
5. 在 `workers/stages/build_support.py` 中把 `_render_module_page()` 接入 `module_structural_fallback`，当模块页多轮重试仍无效时直接生成结构化业务页面落盘并重新校验。
6. 在 `workers/stages/handlers.py` 中把前端运行校验升级为 `tsc -b && vite build`，让未导入符号等 TS 错误在 `verify_run` 阶段提前失败。
7. 在 `backend/app/services/capture/__init__.py` 中为 `statistics / analytics / reports` 等路由补充 route-level marker alias，使同一路由的标题变体不会被误判为空白页。
8. 已补充针对性测试覆盖模块页 structural fallback、统计页截图 marker alias 和 `run_manifest` 的 TypeScript 构建链。
9. 在 `examples/demo_app/frontend/src/hooks/useAppState.ts` 与 `src/types/constants.ts` 中把错误的 Python 三引号注释改为合法的 TS 块注释，并补充回归测试防止 seed 再次混入 `"""`。
10. 在 `examples/demo_app/frontend/src/utils/validators.ts` 中把 `required / email / phone / number / integer / url / ipAddress / password` 统一为 rule factory，和 `minLength / maxLength / min / max` 一样返回 `ValidationRule`，消除表单 schema 的类型不一致问题。
11. 本地已验证 `examples/demo_app/frontend` 可通过 `node node_modules/typescript/bin/tsc -b` 与 `node node_modules/vite/bin/vite.js build`，说明 seed 模板已满足当前 `verify_run` 构建链要求。
12. 两条任务在新版本上重试后已越过 seed 模板错误，新的 `verify_run` 失败点转移到任务生成代码本身：核心壳层页引用了 `APP_PROFILE.navigation / name / appName` 等不存在字段，部分模块页 fallback 模板也存在 `style={{panelStyle}}` 和字面量 `pageVariant` 比较导致的 TypeScript 报错。
13. 已修复 `build_frontend_profile_source()` 的前端类型面，补充 `ModuleProfile.steps / business_value / page_variant`；同时修复模块页 fallback 模板的 `pageVariant` 类型与 `panelStyle` 写法，并在 core 校验器中拦截错误的 `APP_PROFILE` 字段引用，强制回退到模板壳层页。
14. `3e7...` 在新版本 `build 5` 上已越过上一轮固定卡点，但仍在 `verify_run` 的 `tsc -b` 暴露出新的生成代码问题：`Login` 缺少 `onLogin` 类型签名、模块页混用 `productName / visualConfig`、直接访问可选 `APP_PROFILE.visual_profile`、以及 support 文件可能写出 `import.meta.env`。
15. 已新增 support 文件校验与模板回退逻辑，并收紧模块页校验规则：一旦检测到 `productName / visualConfig / APP_PROFILE.visual_profile.` 或未导入的 `Statistic`，就改走结构化 fallback，而不是把问题拖到运行验证阶段。
16. 两条任务在 `build 6` 上的新失败不是 `verify_run`，而是更早被 support 校验拦下：`frontend/src/services/api.ts`、`frontend/src/types/constants.ts`、`frontend/src/types/models.ts` 被识别为无效，但二次 fallback 没有真正覆盖原有坏文件。
17. 根因是 `_synthesize_support_runtime_files()` 默认只在目标文件为空时写入模板；对“非空但无效”的 support 文件，第二次调用仍会跳过写入。已补 `overwrite_existing=True` 通道，并增加回归测试锁定“识别无效后必须覆盖”的行为。
18. `build 7` 穿过 support 批次后，两条任务新的共同失败点收敛到 `frontend/src/pages/StatisticsPage.tsx`。该文件其实已走模块结构化 fallback，但模块校验器误把 `StatisticsPage` 文件名中的 `Statistic` 子串当作 Antd `Statistic` 组件使用，导致统计页被错误判为无效。
19. 已将 `Statistic` 校验从宽泛子串匹配改为更接近真实 JSX/属性访问的 token 识别（如 `<Statistic` / ` Statistic.` / ` Statistic `），并补回归测试，确保 `StatisticsPage` 这种文件名不再触发误判。
20. `build 8` 已真正穿过 build 并进入 `verify_run`，两条任务的新共同失败点重新收敛为前端 `tsc -b`。这轮暴露出的高频问题包括：`App.tsx` 向 `Login` 传递错误回调签名、`Dashboard.tsx` 把 `dashboard_metrics` 数组误当成对象字段、错误使用未导入图标名、`Login.tsx` 中 `loginVariant` 被字面量推断导致 `briefing/workspace` 比较触发 TS2367，以及模块页错误访问 `APP_PROFILE.title`。
21. 已收紧 core/module 校验器并修正模板：`_render_login_page()` / `_render_dashboard_page()` 的变体常量改为 `string` 显式类型；`repair_invalid_core_files()` 新增对 `handleLogin(token)`、缺失 `onLogin` 传递、`dashboard_metrics.totalCases`、未导入图标、未类型化 variant 常量等错误模式的拦截；模块页新增 `APP_PROFILE.title` 误用拦截。已补 7 条针对性回归测试。
22. `build 9` 结果出现分叉：`3e7...` 已完整通过 `verify_run`、`capture`、`compose_manual`、`compose_code_book` 和 `publish`，成功完成交付；`c6f...` 仍在 `verify_run` 的 `tsc -b` 失败。
23. `c6f...` 当前最新的真实 TS 失败点已进一步收敛为两类：`Dashboard.tsx` 在 `APP_PROFILE.dashboard_metrics` 上使用 `metric.icon` 造成联合类型不兼容，以及 `InventoryPage.tsx` 误访问不存在的 `APP_PROFILE.description`。已在校验器中新增这两类坏模式的拦截，并补对应回归测试。
24. 在继续推进 `c6f... build 10` 后，新的真实 `verify_run` 失败点进一步收敛为 support 常量缺口：`OrdersPage.tsx` 和 `StatisticsPage.tsx` 都从 `../types/constants` 导入 `COLORS`，但 seed 与 support fallback 的 `constants.ts` 里没有导出该常量，导致 `tsc -b` 与 `vite build` 同时失败。
25. 已在 seed 常量文件与 support 结构化 fallback 模板中补充 `COLORS` 导出，并把 `repair_invalid_support_files()` 的 `constants.ts` 校验同步升级，确保未来一旦页面引用 `COLORS` 时不会再次因模板缺口而在 `verify_run` 失败。
26. `c6f... build 11` 再次进入 `verify_run` 后，`vite build` 已通过，但 `tsc -b` 仍收敛到单点失败：`AlertsPage.tsx` 的 `ColumnsType` 列配置中混入 `editable: true`，该属性不属于 antd 表格列定义。已将 `editable:` 纳入模块页坏模式拦截，并补对应回归测试，后续会让这类页面直接回退到结构化模块模板，而不是在 `verify_run` 才报类型错。
27. `c6f... build 12` 在最新线上版本上没有再卡在 `editable` 或 `COLORS`，而是长时间停留在 `build`。数据库事件与 worker 日志显示它先后穿过 `support`、多页模块生成和 `core_invalid_retry`，但 `deepseek-v4-pro` 在 `core_invalid_retry` / `module_invalid_retry` 中多次返回被截断的超长 JSON，导致同一批次反复解析失败并长时间重试。为降低后续重试的响应体体积，已在本地把 `core_invalid_retry` 改为按单文件分块重试，并补回归测试；当前等待 `build 12` 在旧 worker 上收敛，若失败则立即携带该补丁发版重试。
28. `c6f... build 12` 最终仍进入 `verify_run` 失败，但新的真实单点已进一步收敛为 `Dashboard.tsx`：页面用 `useState({ anomalyTotal, pendingTasks, closureRate, avgProcessHours })` 维护对象态指标后，又直接执行 `setMetrics(APP_PROFILE.dashboard_metrics)`，把 `dashboard_metrics` 的数组值写入对象态 state，触发 `TS2345`。已在 core 校验器中新增对 `setMetrics(APP_PROFILE.dashboard_metrics)`、`anomalyTotal / pendingTasks / closureRate / avgProcessHours` 这类坏模式的拦截，并补回归测试；后续这类首页将直接回退到结构化 `Dashboard` 模板，而不是在 `verify_run` 才报错。
29. `c6f... build 13` 已成功穿过上一轮 `Dashboard` 问题，但 `verify_run` 又暴露出新的模块页坏模式：`OrdersPage.tsx` / `StatisticsPage.tsx` 重新引入了 `APP_PROFILE.theme.*`，并从 `../types/models` 导入不存在的业务类型（如 `Supplier` / `ReportRecord`），导致 `tsc -b` 报 `TS2305` / `TS2339`。已在模块页校验器中新增对 `APP_PROFILE.theme` 和 `../types/models` 导入的拦截，并补回归测试；后续这类页面将直接回退到结构化模块模板，而不是在运行验证阶段失败。
30. `c6f... build 14` 又成功穿过上一轮模块页问题，但 `verify_run` 再次收敛出新的 `Dashboard.tsx` 坏模式：页面改用 `echarts-for-react/lib/core`、`echarts/core`、`echarts/charts`、`echarts/components`、`echarts/renderers` 这些当前基础环境未覆盖的子路径导入，同时把 `APP_PROFILE.dashboard_metrics` 数组当成对象读取 `todayAlerts / processing / overdueWarnings / closed`，导致 `tsc -b` 与 `vite build` 同时失败。已在 core 校验器中新增对这些 `echarts` 子路径导入和数组对象化字段访问的拦截，并补回归测试；后续这类首页将直接回退到结构化 `Dashboard` 模板。
31. `c6f... build 15` 已成功穿过上一轮 `Dashboard`/`echarts` 单点，但 `verify_run` 的 `tsc -b` 又暴露出两类新的生成坏模式：`App.tsx` 重复导入同一个页面组件并重复声明相同 `Route path`（如重复 `StatisticsPage` / `/statistics`），以及 `Dashboard.tsx` 再次把 `APP_PROFILE.dashboard_metrics` 数组当对象，访问 `openIncidents / inProgress / resolvedToday / escalation`。已在 core 校验器中新增对重复页面导入、重复路由和这组新字段名的拦截，并补回归测试；后续这类输出会直接回退到结构化 `App`/`Dashboard` 模板，而不是在 `verify_run` 才失败。
32. 在携带 `build 15` 修复的新版本上重试 `c6f...` 后，任务没有再直接掉进 `verify_run`，而是重新在 `build` 的首个 `core` 批次暴露出更早的真实瓶颈：页面时间线显示 `core` 一次生成 `App.tsx + Login.tsx + Dashboard.tsx` 时再次触发 `LLM JSON parse error (deepseek-v4-pro): Unterminated string ... frontend/src/App.tsx`，说明不仅 `core_invalid_retry`，连初始 `core` 3 文件批次本身也已经足够大，会在模型首轮响应阶段被截断。已将 `build_codegen_batches()` 调整为把初始 `App/Login/Dashboard` 拆成单文件 core 批次，并补回归测试；后续不再等到 `core_invalid_retry` 才分块。
33. 在初始 `core` 单文件分批版本上再次重试 `c6f...` 后，任务已成功穿过 `build` 并进入 `verify_run`，但新的真实单点收敛为 `Login.tsx` 与 `App.tsx` 的契约不一致：`App.tsx` 继续以 `<Login onLogin={handleLogin} />` 方式使用登录页，而生成出的 `Login.tsx` 是零参数组件，内部自行 `navigate('/dashboard')`，导致 `tsc -b` 报 `TS2322: Property 'onLogin' does not exist on type 'IntrinsicAttributes'`。已在 core 校验器中补上“只要 App 以 `onLogin` 方式使用 Login，Login 就必须显式声明 `onLogin: () => void`”的约束，并补回归测试；后续这类登录页会直接回退到结构化 `Login` 模板。
34. 在继续重试 `c6f...` 的过程中，新的 `build` 卡点进一步明确：并非只有 LLM 首轮响应会把 core 写坏，后续某些 `page:*` 模块页批次也会夹带额外的 `App.tsx` / `Login.tsx` / `Dashboard.tsx` 返回；原逻辑只要这些路径属于整任务 `required_files` 就会直接写入 `generated_files`，导致前面已经修好的 core 文件再次被模块页批次覆盖，最终触发 `core_invalid_retry` 长时间循环。已将批次写入逻辑收紧为“只接收当前批次 `required_files` 内的文件”，并补回归测试锁定“page batch 返回额外 core 文件时必须忽略”。
35. 即使禁止了 `page:*` 批次覆盖 core，`c6f...` 的最新 `build` 仍会在首个 `core`（只要求 `App.tsx`）阶段触发 `finish_reason=length` 的 DeepSeek 截断。worker 日志显示模型虽然只被要求生成一个文件，但仍在响应里夹带大量页面实现，导致 `App.tsx` JSON 头部就被截断。已将 `build_codegen_batches()` 中 `App` 批次携带的 `module_pages` 上下文进一步瘦身为仅保留 `title / route / file_path / component_name` 这组路由壳层必需字段，去掉 `rows / highlights / primary_action` 等重内容，并补回归测试锁定该最小化输入。
36. 在携带 `App` 批次上下文瘦身的新版本上重试 `c6f...` 后，首个 `core` 批次已成功补齐并继续推进，但新的瓶颈转移到 `module_invalid_retry`：页面时间线显示它一次补 2 个模块页时再次触发 `LLM JSON parse error`（包括 `empty response body` 和 `Unterminated string`），且连续停留在“待补齐 2 个文件”。已将 `_MODULE_INVALID_RETRY_BATCH_SIZE` 从 `2` 下调到 `1`，让模块页无效重试也改为单文件分块，并补回归测试同步更新重试批次断言。
