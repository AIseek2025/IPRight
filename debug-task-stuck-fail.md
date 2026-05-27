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

# 已实施修复

1. 在 `workers/stages/build_support.py` 中增加模块页导入路径自愈，把错误的 `../../generated/appProfile` 规范化为 `../generated/appProfile`，并收紧校验规则。
2. 在 `workers/celery_app.py` 中启用 `task_reject_on_worker_lost=True`，让 worker 丢失时任务重新入队。
3. 在 `backend/app/services/__init__.py` 中增加 `recover_interrupted_running_builds()`，worker 启动时自动把上次重启中断的 running build 回收为 failed，并写入事件。
4. 已补充针对性测试覆盖导入路径自愈和中断 build 回收逻辑。
5. 在 `workers/stages/build_support.py` 中把 `_render_module_page()` 接入 `module_structural_fallback`，当模块页多轮重试仍无效时直接生成结构化业务页面落盘并重新校验。
6. 在 `workers/stages/handlers.py` 中把前端运行校验升级为 `tsc -b && vite build`，让未导入符号等 TS 错误在 `verify_run` 阶段提前失败。
7. 在 `backend/app/services/capture/__init__.py` 中为 `statistics / analytics / reports` 等路由补充 route-level marker alias，使同一路由的标题变体不会被误判为空白页。
8. 已补充针对性测试覆盖模块页 structural fallback、统计页截图 marker alias 和 `run_manifest` 的 TypeScript 构建链。
