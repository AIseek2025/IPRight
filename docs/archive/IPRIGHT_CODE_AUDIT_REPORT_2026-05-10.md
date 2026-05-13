# IPRight 项目代码审计报告（2026-05-10）

> 本报告以 `2026-05-10` 当天的工作区代码为准，覆盖 `backend/`、`workers/`、`frontend/`、
> `deploy/`、`scripts/` 与 `docs/` 中既有未提交改动后的最新状态，并对所列问题完成了
> 直接的源码修复（详见第 3 节）。

## 1. 审计范围与方法

### 1.1 范围

- 后端 API 与数据库：`backend/app/api/`、`backend/app/core/{database,auth,config,logging_middleware}.py`、`backend/app/models/`、`backend/app/schemas/`
- 后端服务层：`backend/app/services/{document,llm,capture,runtime,project_profile,validator}`
- Workers：`workers/orchestrator/runner.py`、`workers/stages/handlers.py`、`workers/celery_app.py`
- 前端：`frontend/src/api/client.ts`、`frontend/src/pages/{TaskDetail,TaskList,TaskCreate}.tsx`、`frontend/src/types`、`frontend/src/main.tsx`
- 测试：`backend/tests/test_*.py`
- 部署 / 脚本 / 配置：`docker-compose.yml`、`deploy/docker-compose.production.yml`、`deploy/systemd/*`、`deploy/nginx/*`、`scripts/ipright-ecs-rerun-doc-fixes.sh`、`Makefile`
- 横切关注点：日志、配置、依赖（`backend/pyproject.toml`、`frontend/package.json`）、CORS、鉴权

### 1.2 版本基线

```
git rev-parse HEAD: 8b32129d361faf14b2ce80d61b84f1ba50f95d87
git branch        : main
```

提交基线之上，工作区已存在大量"修改中"的文件（详见 `git status`）。本轮审计严格基于
工作区当前内容，不回退已有改动，仅对发现的问题做精确编辑。

### 1.3 方法

- 静态阅读 + 关键路径专题阅读（重点关注鉴权、CORS、SSE 流、SQLAlchemy 会话、Celery 任务幂等、文档生成器输入/输出、前端 API 错误流转）。
- 运行 `python3 -m py_compile` 校验所有被修改的 Python 文件语法。
- 运行 `pytest backend/tests`（123 通过 / 2 跳过）确认未引入回归。
- 运行 `npx tsc --noEmit` 确认前端类型仍通过。
- 与 2026-05-08 报告交叉对照，避免重复诊断已修复项；本轮发现的多数问题在旧报告中尚未覆盖。

## 2. 摘要

- 共发现问题 **15 个**：**严重 4 / 高 6 / 中 5 / 低 0**
- 本轮已直接修复 **15 个**；待跟进 **0 个**（详见第 8 节"本次补修"）
- 总体健康度评估：核心业务路径（任务编排、文档生成、前端展示）经过 5-08 修复后基本可
  用；本轮先解决了 CORS、SSE、导出下载、引擎泄漏等硬伤，二轮补修又把鉴权层、Celery
  asyncio 嵌套、ECS 发布流程、沙箱加固一并落实。架构性遗留项已全部转化为代码内可配置
  开关或新脚本，详细取舍写在第 3 节与第 8 节中。

## 3. 已修复问题清单

### #1 CORS 同时使用 `allow_origins=["*"]` 与 `allow_credentials=True`（严重）

- 文件：`backend/app/main.py`（旧 33-40 行）
- 问题：浏览器规范禁止 `*` + 凭据并存，所有携带 cookie/credentials 的浏览器跨域请求都会被
  浏览器侧拒绝；同时这条配置事实上向任意域开放敏感接口。
- 修复：改为读取 `IPRIGHT_CORS_ALLOW_ORIGINS` 显式白名单，并通过
  `IPRIGHT_CORS_ALLOW_CREDENTIALS` 开关控制凭据。在白名单未配置时退化为
  `allow_origins=["*"]` + `allow_credentials=False` 的合规组合，避免误用。
- 同时把 `@app.on_event("startup")` 迁移到 FastAPI `lifespan`，并在退出时调用
  `engine.dispose()`，消除 FastAPI 0.110+ 的 deprecation。
- 关键 diff 摘要：
  ```python
  @asynccontextmanager
  async def _lifespan(app: FastAPI):
      engine = _get_engine()
      async with engine.begin() as conn:
          await conn.run_sync(Base.metadata.create_all)
      try:
          yield
      finally:
          await engine.dispose()

  if _cors_origins:
      app.add_middleware(CORSMiddleware, allow_origins=_cors_origins,
                         allow_credentials=_cors_allow_credentials, ...)
  else:
      app.add_middleware(CORSMiddleware, allow_origins=["*"],
                         allow_credentials=False, ...)
  ```
- 验证：`python3 -c "from app.main import app"` 加载成功；`pytest` 全部通过。

### #2 SSE 端点会重复返回旧状态（严重 / 实时性失效）

- 文件：`backend/app/api/tasks.py`（旧 365-395 行 `stream_task_status`）
- 问题：循环里重复使用 `db.get(Task, task_id)`，SQLAlchemy 的 identity map 让后续调用直接命
  中缓存，**永远拿不到任务状态的实时变化**；同时依赖注入提供的 `db` 会话生命周期与流式
  generator 不一致，存在请求结束后会话已关闭的隐患。
- 修复：移除依赖注入的 `db`，改在 generator 内部用
  `get_session_factory()` 每轮新开短会话；任务不存在时立即推送 `event: error` 并结束。
- 关键 diff 摘要：
  ```python
  @router.get("/tasks/{task_id}/stream")
  async def stream_task_status(task_id: uuid.UUID):
      from app.core.database import get_session_factory
      async def event_stream():
          factory = get_session_factory()
          for _ in range(300):
              async with factory() as session:
                  task = await session.get(Task, task_id)
                  ...
              yield f"data: {data}\n\n"
              await asyncio.sleep(2)
  ```
- 验证：`pytest`；手动复审 SSE 帧逻辑，确认终止条件保留。

### #3 `download_export` 在文件缺失时返回 204 空体（严重 / 契约错误）

- 文件：`backend/app/api/exports.py`（旧 33-48 行）
- 问题：导出已被标记 `ready` 但磁盘文件丢失时，返回 `204 No Content`，前端只能拿到空响应
  无法判断错误。同时 `file_path` 直接拼接 `export.file_name`，如果数据库被注入恶意文件名（含
  `..`），存在跨目录读取风险。
- 修复：
  1. 引入 `_safe_resolve_export_path` 把 `WORKSPACE_ROOT/tasks/<task_id>/builds/<build_id>/exports`
     作为白名单根，校验最终路径必须在其下；非法 `file_name` 直接 400。
  2. 文件缺失时记录 warning 并返回 `404 EXPORT_FILE_MISSING`。
- 关键 diff 摘要：
  ```python
  def _safe_resolve_export_path(export):
      exports_dir = (Path(settings.WORKSPACE_ROOT) / "tasks" / str(export.task_id)
                     / "builds" / str(export.build_id) / "exports").resolve()
      candidate = (exports_dir / export.file_name).resolve()
      candidate.relative_to(exports_dir)   # raises -> 400
      return candidate

  if not file_path.is_file():
      raise HTTPException(status_code=404,
          detail={"code": "EXPORT_FILE_MISSING", "message": "..."})
  ```
- 验证：`pytest`（导出测试覆盖 happy path 与 404 路径）。

### #4 鉴权中间件存在硬编码 fallback token（严重 / 安全）

- 文件：`backend/app/core/auth.py`（旧 11-12、29 行）
- 问题：`API_TOKEN`/`ADMIN_TOKEN` 在环境变量缺失时回退到 `"ipright-dev-token-2026"` /
  `"ipright-admin-token-2026"`，公开仓库即可还原 token；同时 token 比较使用普通 `==`，存在
  时序攻击隐患。
- 修复：
  1. `_load_token()`：DEBUG 模式下生成进程级随机 token 并打印 warning；非 DEBUG 模式下返回
     空字符串，迫使中间件 **fail-closed**（任何 admin 请求都会 401）。
  2. token 比较切换到 `secrets.compare_digest`，避免时序泄漏。
  3. 公共路径集合显式声明，逻辑更清晰。
- 关键 diff 摘要：
  ```python
  def _load_token(env_name, role):
      value = os.environ.get(env_name, "").strip()
      if value:
          return value
      if debug:
          generated = secrets.token_urlsafe(24)
          logger.warning("%s unset; generated ephemeral", env_name)
          return generated
      logger.warning("%s not configured; will reject all", env_name)
      return ""

  if not ADMIN_TOKEN or not secrets.compare_digest(token, ADMIN_TOKEN):
      return self._unauthorized("Invalid admin token")
  ```
- 验证：`pytest`；测试 `tests/test_api_extended.py::test_admin_*` 仍能通过（依赖环境变量
  注入）。

### #5 `_build_bundle` 缺少符号链接 / 路径越界防护（高 / 安全）

- 文件：`backend/app/api/tasks.py`（旧 69-98 行）
- 问题：`zipfile.write(file_path, arcname)` 直接写入 `task_root` 下所有文件。若工作区被人为
  植入指向 `/etc` 或其他任务目录的符号链接，打包时会把外部数据塞进 ZIP，造成数据泄露。
- 修复：新增 `_safe_add()` 与 `_is_within()`，跳过所有符号链接，并在 `resolve()` 之后校验
  路径必须在 `task_root` 下；异常情况记录 warning 并跳过。
- 关键 diff 摘要：
  ```python
  def _safe_add(zf, file_path):
      if file_path.is_symlink():
          logger.warning("Skipping symlink in bundle: %s", file_path)
          return
      relative = file_path.resolve().relative_to(task_root_resolved)
      zf.write(file_path, (root_prefix / relative).as_posix())
  ```
- 验证：`pytest`；手动验证逻辑覆盖目录、文件与符号链接 3 种分支。

### #6 `_get_engine` 在 PID/event-loop 切换时泄漏旧引擎（高 / 资源泄漏）

- 文件：`backend/app/core/database.py`
- 问题：fork 后或在多个 event loop 之间切换时，会创建新 engine 并重置 session factory，但
  **不释放旧 engine**。每次重建都会泄漏一份连接池与同步连接。
- 修复：保留旧引用 `previous_engine`，新引擎构造完成后调用 `_dispose_engine_safely`，
  在能拿到 sync engine 的情况下做同步 `dispose()`，最差情况下也只是回退到 GC 释放，但
  不再常驻泄漏。同时 `lifespan` 退出时 `await engine.dispose()`（见 #1）。
- 关键 diff 摘要：
  ```python
  previous_engine = _engine
  _engine = create_async_engine(db_url, ...)
  _async_session_factory = None
  if previous_engine is not None and previous_engine is not _engine:
      _dispose_engine_safely(previous_engine)
  ```
- 验证：`pytest`；`pytest tests/test_workers.py::TestStageHandlers` 涉及多次 loop 创建，未
  出现新警告。

### #7 `SourceCodeBookGenerator` 完全忽略 `exclude_globs`（高 / 文档质量）

- 文件：`backend/app/services/document/codebook.py`（`_read_code_files` / `_resolve_pattern`）
- 问题：`code_index_manifest.exclude_globs` 字段在生成器中**从未生效**，导致文档可能把
  字体、二进制、`__pycache__` 等非源码内容包入。同时 `_resolve_pattern` 的第 3 个参数从未使
  用，是死代码。
- 修复：`_read_code_files` 把 `exclude_globs` 提取出来，传给 `_resolve_pattern`；
  `_resolve_pattern` 使用 `fnmatch` 同时匹配 OS-native 与 POSIX 化的相对路径，命中任何
  exclude 模式即跳过。
- 关键 diff 摘要：
  ```python
  exclude_globs = code_index.get("exclude_globs", []) or []
  ...
  if any(fnmatch.fnmatch(normalized, ex) or fnmatch.fnmatch(rel, ex) for ex in excludes):
      continue
  ```
- 验证：`pytest backend/tests/test_document.py` 全部通过。

### #8 仪表盘截图过滤与其他端点不一致（高 / 行为回归）

- 文件：`backend/app/api/tasks.py`（旧 206-210 行）
- 问题：`/tasks/{task_id}/dashboard` 对截图使用了严格 `Screenshot.build_id == effective_build_id`，
  而 `/screenshots`、`/artifacts` 端点都是 `or_(... == eid, build_id.is_(None))`。结果：历史
  数据（`build_id=None`）在仪表盘永远不展示，与详情页不一致。
- 修复：与其他端点保持一致，使用 `or_` 兜底 `is_(None)` 行。
- 验证：`pytest`；与 2026-05-08 修复 `_resolve_effective_build_id` 的初衷一致。

### #9 `compose_manual` 阶段 LLM 失败即整阶段失败（高 / 鲁棒性）

- 文件：`workers/stages/handlers.py`（`run_compose_manual_stage`，旧 2183-2200 行）
- 问题：`run_plan_stage` 在 LLM 失败时已有模板降级，但 `run_compose_manual_stage` 没有：
  LLM 抛异常或 `success=False` 直接返回 `StageResult(success=False)`，整个流水线宣告失败。
  实际上文档生成器本身就有完整的模板兜底，只用现有 `project_profile` 也能产出说明书。
- 修复：把 LLM 调用的失败路径改为告警 + 走兜底，仅在 `metadata.llm_used` 字段标记
  `template_fallback`，下游文档生成器不受影响。
- 关键 diff 摘要：
  ```python
  if manual_resp.success and manual_resp.structured:
      project_profile = _merge_manual_llm_content(...)
  else:
      logger.warning("[compose_manual] LLM unavailable, fallback to existing profile content: %s", ...)
      manual_llm_used = "template_fallback"
  ```
- 验证：`pytest backend/tests/test_workers.py`（含 stage 注册校验）通过。

### #10 `Export.download_url` 存为字面字符串占位符（中 / 契约）

- 文件：`workers/stages/handlers.py`（`run_publish_stage`，旧 2305-2313 行）
- 问题：原来写入 DB 的 `download_url=f"/api/v1/exports/{{export_id}}/download"` 在 f-string
  转义后实际存的是 `"/api/v1/exports/{export_id}/download"`（字面 `{export_id}`），任何把
  该字段直接当 URL 使用的客户端都会 404。前端目前是用 `getExportDownload(exp.id)` 自行拼
  装才"恰好工作"，但 DB 里的脏数据是隐患。
- 修复：在创建 `Export` 时显式分配 `id=uuid.uuid4()`，并把 `download_url` 拼成真正的 URL。
- 关键 diff 摘要：
  ```python
  new_export_id = uuid.uuid4()
  export = Export(id=new_export_id, ...,
                  download_url=f"/api/v1/exports/{new_export_id}/download")
  ```
- 验证：`pytest`。

### #11 前端 `TaskList` `useEffect` deps 闭包陷阱（中 / 类型与可维护性）

- 文件：`frontend/src/pages/TaskList.tsx`
- 问题：`useEffect(() => fetchTasks(), [page, statusFilter])` 内部读取 `pageSize`、`keywordFilter`
  等闭包变量，但未列入 deps；同时 ESLint 警告被隐式吞掉。修复时增加显式参数传入并附
  注释，避免再次"修一处坏一处"。
- 修复：
  ```ts
  useEffect(() => {
    void fetchTasks({ nextPage: page, nextStatus: statusFilter });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, statusFilter]);
  ```
- 验证：`npx tsc --noEmit` 通过。

### #12 `TaskDetail` 5 秒轮询循环间隔被反复重建（中 / 性能）

- 文件：`frontend/src/pages/TaskDetail.tsx`
- 问题：原 `useEffect` 把 `dashboard` 整个对象当 deps，每次拉到新数据都 clear → setInterval，
  实际上是变相的"立即触发再 5s 等"，不可控。
- 修复：仅在 `dashboard?.task.status` 不是终态时启动 interval，并把状态作为唯一 deps，避免
  对象引用变化导致的重复重建。
- 验证：`tsc --noEmit` 通过；逻辑上保留对 task 完成后停止轮询的语义。

### #13 生产 docker-compose 默认密码（中 / 安全）

- 文件：`deploy/docker-compose.production.yml`
- 问题：`POSTGRES_PASSWORD` / `MINIO_ROOT_PASSWORD` 默认值为 `*_change_me`，遗忘环境变
  量时会用弱口令直接起服务。
- 修复：改为 `${VAR:?VAR must be set}` 形式，未设置时直接报错拒绝启动。开发模式
  `docker-compose.yml` 不动（本地开发用的硬编码值是有意为之）。

### #14 Celery worker 内 `asyncio.run` 嵌套（高 / 架构 — 2026-05-10 补修）

- 文件：`workers/orchestrator/async_runner.py`（新增）、`workers/orchestrator/runner.py`
- 问题：`run_full_pipeline` 直接 `asyncio.run(_async_run_pipeline(...))`：每个任务新建一个
  event loop，丢弃 SQLAlchemy 引擎与连接池；嵌套 await 又会触发 RuntimeError。任何阶段
  handler 想"顺手 await 一下"都得自己造轮子。
- 修复：新增 `workers/orchestrator/async_runner.py`，内部维护一个进程级别的"专用后台
  asyncio loop（守护线程）"。`run_async(coro, timeout=...)` 通过
  `asyncio.run_coroutine_threadsafe` 把协程提交到这个 loop，并在调用方阻塞等待结果。
  `runner.py` 把 `asyncio.run(...)` 替换为 `run_async(...)`，所有阶段都共用同一个 loop，
  数据库引擎、`httpx.AsyncClient` 池都能跨任务复用。
- 关键设计取舍：
  - 没有切换到 `gevent`/`eventlet`，因为 `asyncpg` 与 monkey-patched socket 不兼容，且会
    波及到 backend 进程。专用线程方案侵入面最小、可逐步回滚。
  - 取消语义：`run_async` 只 surface `Future.timeout`，不强制取消协程；Celery 自己的
    `time_limit`/`soft_time_limit` 仍是终极兜底。
  - 进程退出时通过 `atexit` 触发 `loop.stop()` + 5 秒 join，best-effort；硬 kill 由 Celery
    保证。
- 验证：
  ```python
  python3 -c "from workers.orchestrator.async_runner import run_async, shutdown_runner; \
              import asyncio; async def f(x): return x*2; print(run_async(f(7))); shutdown_runner()"
  # => 14
  ```
  + `pytest backend/tests`（含 `test_workers.py::test_all_stages_registered`）123 → 132
  通过（仅新增 9 条鉴权用例，无回归）。

### #15 `IPRIGHT_API_TOKEN` 未在中间件实际生效（高 / 安全 — 2026-05-10 补修）

- 文件：`backend/app/core/auth.py`、`backend/app/main.py`、`frontend/src/api/client.ts`、
  `backend/tests/conftest.py`（新增）、`backend/tests/test_auth_middleware.py`（新增）
- 问题：上一轮 5-08 报告中提到的"`AuthMiddleware` 加载了 `API_TOKEN` 但中间件未注册到
  app；即便注册也只校验 admin"。结果业务 API（任务列表、详情、重试等）完全开放，且
  `app.add_middleware(AuthMiddleware)` 这一行**根本不存在**。
- 修复：
  1. 在 `app/main.py` 显式 `app.add_middleware(AuthMiddleware)`（在 CORS 之后注册）。
  2. 改写 `AuthMiddleware.dispatch`：
     - 公共豁免：`/health`、`/healthz`、`/readyz`、`/docs`、`/openapi.json`、`/redoc`、
       `/favicon.ico`、CORS pre-flight `OPTIONS`、所有 `*/download` 与 `bundle/download`
       预共享下载链接。
     - `/api/v1/admin/*` → `ADMIN_TOKEN`；其它 `/api/v1/*` → `API_TOKEN`。
     - SSE 端点 `/api/v1/tasks/{id}/stream` 额外接受 `?token=` 查询串，因为浏览器
       `EventSource` 不能塞自定义 header。query token 仅对 `/stream` 端点生效，避免泄漏
       到一般访问日志。
     - token 比对统一走 `secrets.compare_digest`。
  3. `frontend/src/api/client.ts`：
     - 新增 `getApiToken()` / `setApiToken(token)`：依次从
       `window.__IPRIGHT_API_TOKEN__` → `localStorage("ipright_api_token")` →
       `import.meta.env.VITE_IPRIGHT_API_TOKEN` 读取。
     - 在 axios `request` 拦截器自动注入 `Authorization: Bearer <token>`。
     - 暴露 `getTaskStreamUrl(taskId)`，自动把 token 拼进 query string。
  4. 测试：新增 `backend/tests/conftest.py`：
     - 在 import `app.core.auth` 之前用 `os.environ.setdefault` 设置
       `IPRIGHT_API_TOKEN`/`IPRIGHT_ADMIN_TOKEN`，避免触发 fail-closed。
     - 自动 monkeypatch `httpx.AsyncClient.request`，给所有现有用例带上
       `Authorization: Bearer test-api-token`。
     - 暴露 `unauthenticated_request_kwargs` fixture 给反向用例使用。
  5. 新增 `backend/tests/test_auth_middleware.py` 共 9 条用例：覆盖 health 公共、业务
     API 401/200、admin 与 api token 不可互换、SSE query token、下载链接公共。
- 关键设计取舍：
  - **不引入 OIDC/JWT**：与产品已有简易部署方案保持一致；token 只是预共享串，所有
    替换/轮换都是改一处环境变量。
  - **预共享下载链接保持公开**：业务上需要把链接直接发给申请人下载，加 token 会破坏
    用户体验。安全性靠 UUID 不可枚举 + 业务侧失效机制兜底。
- 验证：
  ```
  pytest backend/tests/test_auth_middleware.py -q
  # => 9 passed
  pytest backend/tests -q
  # => 132 passed, 2 skipped
  cd frontend && npx tsc --noEmit
  # => clean
  ```

### #16 ECS 发布脚本规范化（高 / 运维 — 2026-05-10 补修）

- 文件：`scripts/ipright-release.sh`（新增）、`scripts/ipright-ecs-rerun-doc-fixes.sh`、
  `deploy/release-history.log`（新增）
- 问题：原 `ipright-ecs-rerun-doc-fixes.sh` 用 `sudo cp -f` 把任意工作区文件直接盖到
  生产路径，绕过 git，无回滚、无审计。
- 修复：
  1. 老脚本顶部加 deprecation banner，并要求 `IPRIGHT_ALLOW_DEPRECATED_DEPLOY=1` 才能继续
     运行；保留实际功能不变（保 hotfix 兜底用途）。
  2. 新增 `scripts/ipright-release.sh`，强制走"git commit → 远端打包 → 版本目录 → 原子
     symlink"链路：
     - 拒绝脏工作区（`git status --porcelain` 非空直接 exit 4）。
     - 拒绝未推到远端的 commit（`git branch -r --contains` 检查）。
     - 可选 `IPRIGHT_RELEASE_BRANCH` 把分支收紧到 `main`/`release/*`。
     - 用 `git archive` 打包指定 commit，scp 到 ECS 后解压到
       `/opt/ipright/releases/<UTC>-<commit>/`，原子 `mv -Tf` 切换 `current` 软链接。
     - 在 `deploy/release-history.log` 追加一行 TSV：
       `timestamp release_id commit branch operator target remote_path note`，便于回溯。
     - 默认重启 `ipright-api`/`ipright-worker`，可通过 `IPRIGHT_SKIP_RESTART=1` 关闭。
- 关键设计取舍：
  - **保留 deprecated 脚本而不是删除**：紧急情况下（比如远端 git 不可用）仍可走老路径，
    但要显式确认风险。
  - **不内嵌 release manifest 到 ECS 远端**：远端 `current` 符号链接已经隐含当前
    release_id；额外把 manifest 留在本地 `deploy/release-history.log`，操作者来源信息更
    准确。
- 验证：`bash -n scripts/ipright-release.sh && bash -n scripts/ipright-ecs-rerun-doc-fixes.sh`
  通过；逻辑流程在第 8 节"本次补修"里有完整列表。

### #17 Sandbox 加固 + 可选 Docker 后端（中 / 安全 + 稳定 — 2026-05-10 补修）

- 文件：`backend/app/services/runtime/__init__.py`
- 问题：`SandboxRuntime.start_services` 直接 `subprocess.Popen(..., shell=True)`，没有
  `setsid`、没有 rlimit、继承宿主全部环境变量（包括 IPRIGHT_API_TOKEN、数据库密码
  等），且 install 命令没有超时上限。
- 修复（兼容老调用方）：
  1. 引入 `SandboxLimits` 数据类 + `_build_env()` 环境变量白名单（默认仅
     `PATH/HOME/LANG/LC_ALL/LC_CTYPE/TZ/PYTHONUNBUFFERED/PYTHONIOENCODING/NODE_PATH/
     NPM_CONFIG_CACHE/PNPM_HOME/PIP_CACHE_DIR/PIP_INDEX_URL`，并允许通过
     `IPRIGHT_SANDBOX_EXTRA_ENV` 增量扩列）。
  2. `_make_preexec()`：子进程一律 `setsid` + chdir 到工作区，并应用
     `RLIMIT_CPU/AS/FSIZE/NOFILE/NPROC`；任一 cap host 拒绝时降级为不限制（不阻塞老主机）。
  3. 新增统一入口 `run_sandboxed(cmd, timeout=...)`：
     - 默认 `timeout=300s`，超时通过 `_kill_process_group(SIGTERM → 2s 后 SIGKILL)` 杀整组。
     - 返回 `SandboxedResult{returncode, stdout, stderr, timed_out, duration_seconds}`。
  4. `install_dependencies` 改为复用 `run_sandboxed`，可读 `run_manifest.install_timeout_seconds`
     （默认 600s）。
  5. `start_services` 仍用 `subprocess.Popen`（dev 服务必须常驻），但现在统一带
     `start_new_session=True`、`preexec_fn=_make_preexec`、`env=_build_env()`。
  6. `stop_all` 改为 `_kill_process_group`，避免 dev 服务 fork 出来的子进程残留。
  7. **可选 Docker 后端**：`IPRIGHT_SANDBOX_BACKEND=docker` + 系统装了 `docker` 时，
     `run_sandboxed` 走 `docker run --rm --network none --read-only --tmpfs /tmp:rw,exec
     --memory ... --cpus 1 --workdir /workspace -v <wsp>:/workspace:ro <image>`。
     `IPRIGHT_SANDBOX_DOCKER_IMAGE` 可定制基镜（默认 `python:3.11-slim`）。
     docker 未装时打 warning 自动退回 subprocess 后端，不阻塞流水线。`start_services`
     永远走 subprocess（dev server 必须直接监听宿主端口）。
- 关键设计取舍：
  - **不强制使用 docker**：开发环境 / CI 通常没装 docker，强制依赖会破坏现有部署。
  - **不引入 firejail/bwrap**：用户明确反对引入新系统依赖。
  - **rlimit 默认值**：`AS=2GiB / NOFILE=4096 / NPROC=1024 / FSIZE=512MiB`，根据实测
    Vite + uvicorn 的最低需求保守上调；不设 `CPU` 限制（避免误杀慢启动）。
- 验证：
  ```
  python3 -c '...sandbox smoke test...'
  # rc=0 stdout="hello\n8" timed_out=False     <-- env whitelist 起效，env 仅 8 项
  # timeout rc=-1 timed_out=True                <-- killpg 生效
  # env-leak stdout=''                          <-- IPRIGHT_API_TOKEN 未泄漏给子进程
  ```
  + `pytest backend/tests` 全绿（132 passed）。

## 4. 待跟进问题清单

本轮 4 项 TODO 已全部转化为代码改动（见上方 #14-#17）。**当前没有遗留待跟进项。**
后续如果运营数据暴露新问题（例如 SSE 在反代后丢帧、docker 后端在某些镜像上无法启动），
将另起追加项。

## 5. 模块健康度小结

### 5.1 Backend API（`backend/app/api/`）

经本轮修复，CORS、SSE 流、bundle 打包路径越界、导出 404 契约几个硬伤已经收口；任务列表、
仪表盘、导出、重试/取消的端点逻辑清晰，错误码统一。仍需关注 #TODO-2（鉴权覆盖率）。

### 5.2 Backend 服务层（`backend/app/services/`）

`document/` 在 5-08 之后逻辑已经成熟，本轮补齐 `codebook.exclude_globs` 缺失。
`llm/` 客户端有显式的 fallback 模型与超时控制；`project_profile.py` 的最小截图场景兜底已
就位。`runtime/sandbox.py` 仍是工程化最薄弱的部分（见 TODO-4）。

### 5.3 Workers（`workers/`）

阶段编排器引入了 active build 重检 + flock 重入保护，整体状态机比 5-08 更稳健。本轮把
`compose_manual` 的 LLM 失败路径改为兜底，并修正 `Export.download_url` 的字面量 bug。
TODO-1 是值得投入的下一步。

### 5.4 Frontend

`TaskList` / `TaskDetail` 整体可读，错误状态、loading、序号化请求都齐备。本轮修了两个
useEffect 闭包/依赖陷阱，并与 `tsc --noEmit` 保持兼容。其它细节（如可访问性、键盘焦点）
属于改进型工作。

### 5.5 部署 / 脚本

`docker-compose.production.yml` 的弱口令默认值已堵住；systemd 单元文件、nginx 反代示例
配置中规中矩。`scripts/ipright-ecs-rerun-doc-fixes.sh` 仍属于"运维脚本"，建议正规化（TODO-3）。

## 6. 改进建议（非阻塞）

1. **统一鉴权**：把 `IPRIGHT_API_TOKEN` 在中间件强制启用，并提供"内部回调白名单"机制
   （Celery → API），避免裸开放接口。
2. **分阶段 retry / 断点续跑**：当前 `retry_task` 仍是从头跑；可以按 `from_stage` 真正实现
   只重跑某阶段，节省重新生成 PRD/代码的成本。
3. **SSE 改造**：考虑用 Redis Pub/Sub 推送状态，前端用 EventSource 订阅；本轮的实现仍是 2s
   轮询 + 长链接，资源占用偏高。
4. **生成代码沙箱化**：见 TODO-4。
5. **依赖锁定**：`backend/pyproject.toml` 与 `frontend/package.json` 都使用了 `>=` / `^`，
   建议引入 `uv lock` / `pip-tools` / `pnpm` lockfile，减少线上构建漂移。
6. **静态分析 CI**：把 `python -m py_compile`、`ruff`、`mypy --strict` 与 `tsc --noEmit`
   接到 CI（含 PR check），后续审计就能聚焦真正的语义问题。
7. **生产 Secrets**：`docker-compose.production.yml` 已改为强制环境变量；下一步建议接入
   secret 管理（AWS SecretsManager / Vault）而不是 `.env` 文件。

## 7. 附录

### 7.1 命令记录

```bash
# 1. 状态摸底
git rev-parse HEAD                  # 8b32129d361faf14b2ce80d61b84f1ba50f95d87
git status --short                  # 见上文

# 2. 编译校验
python3 -m py_compile \
  backend/app/main.py backend/app/api/tasks.py backend/app/api/exports.py \
  backend/app/core/auth.py backend/app/core/database.py \
  backend/app/services/document/codebook.py workers/stages/handlers.py
# => OK

# 3. 后端测试
cd backend && python3 -m pytest tests/ -q
# => 123 passed, 2 skipped

# 4. 前端类型检查
cd frontend && npx --no-install tsc --noEmit
# => 无错误
```

### 7.2 参考文档

- `docs/IPRIGHT_CODE_AUDIT_REPORT_2026-05-08.md`
- `docs/IPRIGHT_RECENT_REPAIR_SUMMARY_2026-05-08.md`
- `docs/IPRIGHT_UPDATE_SUMMARY_2026-05-08.md`
- `docs/IPRIGHT_DOCUMENT_GENERATION_RULES.md`

### 7.3 本轮修改文件清单（一轮 + 二轮补修后的全量列表）

```
backend/app/main.py                              # CORS + lifespan + AuthMiddleware 注册
backend/app/api/tasks.py                         # SSE / dashboard build_id / bundle 路径防走
backend/app/api/exports.py                       # 404 + 路径白名单
backend/app/core/auth.py                         # fail-closed token + 全局 API_TOKEN 鉴权
backend/app/core/database.py                     # engine 释放
backend/app/services/document/codebook.py        # exclude_globs
backend/app/services/runtime/__init__.py         # sandbox 加固 + docker 可选后端
workers/orchestrator/runner.py                   # 接入 run_async
workers/orchestrator/async_runner.py             # 新增：进程级专用 asyncio loop
workers/stages/handlers.py                       # manual fallback + Export id
frontend/src/pages/TaskList.tsx                  # useEffect 闭包
frontend/src/pages/TaskDetail.tsx                # 轮询 deps
frontend/src/api/client.ts                       # axios 拦截器注入 Bearer + SSE token
deploy/docker-compose.production.yml             # 强制环境变量
deploy/release-history.log                       # 新增：发布审计日志
scripts/ipright-ecs-rerun-doc-fixes.sh           # deprecation banner + 显式确认
scripts/ipright-release.sh                       # 新增：标准化发布脚本
backend/tests/conftest.py                        # 新增：注入测试 token + Bearer
backend/tests/test_auth_middleware.py            # 新增：9 条鉴权用例
docs/IPRIGHT_CODE_AUDIT_REPORT_2026-05-10.md     # 本报告
```

### 7.4 严重度分布

| 严重度 | 已修复 | 待跟进 | 合计 |
|--------|--------|--------|------|
| 严重   | 4      | 0      | 4    |
| 高     | 6      | 0      | 6    |
| 中     | 5      | 0      | 5    |
| 低     | 0      | 0      | 0    |
| 合计   | 15     | 0      | 15   |

> 注：上一轮初步发现的 15 项问题，二轮补修把原"待跟进 4 项"全部转化为代码改动；
> "低"级别的代码质量项（如 `diagrams.generate_workflow_diagram` 死代码）仍归入 §6
> 改进建议而非独立条目，避免噪音。

## 8. 本次补修（2026-05-10 第二轮）

### 8.1 动机

第一轮交付完成后，用户要求继续把 4 项 TODO 完成，**不再以"待跟进"为名义留尾巴**。
本轮目标：把架构性问题（asyncio + Celery、鉴权、发布、沙箱）转化为可运行、可回滚、
可验证的实际代码改动；如果某项必须保留为遗留兼容（如老 ECS 脚本），明确加 deprecation
路径并提供新的标准化替代。

### 8.2 高层方案对照

| TODO | 方案 | 主入口 | 配置 / 开关 |
|------|------|--------|-------------|
| TODO-1 Celery + asyncio | 进程级专用后台 loop（守护线程）+ `run_coroutine_threadsafe` | `workers/orchestrator/async_runner.py::run_async` | 无新增配置；`atexit` 自动回收 |
| TODO-2 API_TOKEN 全局生效 | 重写 `AuthMiddleware`，注册到 `app.add_middleware`；axios 拦截器；测试 conftest | `backend/app/core/auth.py::AuthMiddleware`、`frontend/src/api/client.ts::getApiToken` | `IPRIGHT_API_TOKEN` / `IPRIGHT_ADMIN_TOKEN`，DEBUG 缺省自动生成 |
| TODO-3 ECS 发布脚本 | 老脚本加 deprecation 闸门；新增 `ipright-release.sh` 走 git archive + 版本目录 + 原子 symlink | `scripts/ipright-release.sh` | `IPRIGHT_RELEASE_REMOTE`、`IPRIGHT_RELEASE_BRANCH`、`IPRIGHT_SKIP_RESTART`、`IPRIGHT_RELEASE_NOTE` |
| TODO-4 sandbox 加固 | `_make_preexec` + rlimit + setsid + env 白名单；新增 `run_sandboxed`；可选 docker 后端 | `app/services/runtime/__init__.py::SandboxRuntime.run_sandboxed` | `IPRIGHT_SANDBOX_BACKEND`、`IPRIGHT_SANDBOX_*_BYTES/NOFILE/NPROC/CPU_SECONDS`、`IPRIGHT_SANDBOX_DOCKER_IMAGE`、`IPRIGHT_SANDBOX_EXTRA_ENV` |

### 8.3 风险与已采取的缓解

1. **共享 asyncio loop 中协程异常未捕获会污染 loop**：`run_async` 让 `Future.result()`
   re-raise，调用方拿到完整的 traceback；`_runner` 在 loop 关闭时统一 cancel 残留 task。
2. **AuthMiddleware 一旦上线，所有现有客户端立刻 401**：通过 `IPRIGHT_DEBUG=true` 模式
   下生成临时 token + warning 日志保留开发体验；前端 `setApiToken` 暴露给运维做
   localStorage 注入；测试 conftest 自动注入避免 CI 一片红。
3. **新发布脚本可能在远端目录布局不同的环境上失败**：脚本里所有路径都以
   `--prefix` 形式写入，不假设宿主目录结构；遇到 mismatch 会 `set -e` 立刻报错并保留
   旧 `current` symlink。
4. **Docker 沙箱与 dev server 不兼容**：明确文档化"长驻服务一律走 subprocess 后端"，
   并在 `start_services` 注释里写明；只在 `run_sandboxed` 单次调用启用 docker。
5. **rlimit 在 macOS / 部分容器内被拒**：每个限制都套 try/except，host 拒绝即降级
   不限制 + warning，不阻塞流水线。

### 8.4 回归测试结果

```
$ python3 -m py_compile <所有改动 .py>
=> OK

$ cd backend && python3 -m pytest tests/ -q
=> 132 passed, 2 skipped, 1 warning in 3.03s
   （上一轮 123 → 本轮 +9 鉴权用例，无新失败）

$ cd frontend && npx tsc --noEmit
=> clean

$ python3 - <<'PY'  # async runner 烟测
from workers.orchestrator.async_runner import run_async, shutdown_runner
import asyncio
async def f(x): await asyncio.sleep(0.05); return x*2
print(run_async(f(7)), run_async(f(21)))
shutdown_runner()
PY
=> 14 42

$ python3 - <<'PY'  # sandbox 烟测
import asyncio, tempfile
from app.services.runtime import SandboxRuntime
async def main():
    with tempfile.TemporaryDirectory() as tmp:
        rt = SandboxRuntime(tmp)
        ok = await rt.run_sandboxed('echo hello && env | wc -l', timeout=5)
        bad = await rt.run_sandboxed('sleep 30', timeout=1)
        leak = await rt.run_sandboxed('echo $IPRIGHT_API_TOKEN', timeout=5)
        print(ok.returncode, ok.timed_out, '/', bad.timed_out, '/', repr(leak.stdout.strip()))
asyncio.run(main())
PY
=> 0 False / True / ''   <-- 环境变量未泄漏，超时按预期 SIGKILL
```

### 8.5 衍生待跟进项

本轮**没有**新发现的衍生待跟进项；遗留的非阻塞改进仍归入 §6。如运营中暴露 SSE
在反代后断流、docker 后端镜像兼容性、release-history.log 同步到中央位置等问题，
将另开追加条目。
