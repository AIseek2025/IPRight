# IPRight 代码审计修复报告（2026-05-26）

## 1. 审计范围与方法

| 项 | 内容 |
|---|---|
| 仓库路径 | `/Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight` |
| 基准提交 | `039fce20f3acfe03b97af734232ae86c401bb1fc`（`git rev-parse HEAD`） |
| 审计日期 | 2026-05-26 |
| 方法 | 以当前工作区为准，按 Backend API/服务、Workers、Frontend、测试、部署脚本横切审查；发现问题后直接改代码并跑验证 |
| 参考文档 | 历史报告与规则文档作背景参考，不以旧结论替代本次实测 |

**验证命令：**

```bash
git rev-parse HEAD
python3 -m py_compile backend/app/main.py backend/app/api/tasks.py backend/app/api/exports.py workers/stages/build_support.py
python3 -m pytest backend/tests -q
cd frontend && npx tsc --noEmit
```

---

## 2. 摘要

| 指标 | 数量 |
|---|---|
| 发现问题 | 12 |
| 已修复 | 11 |
| 待跟进 | 1（W-02：慢测拆分，见 §4） |
| 健康度 | **良好**（`backend/tests` 298 passed / 2 skipped，含 `test_workers.py` 全绿） |

---

## 3. 已修复问题清单

### F-12｜中｜artifact 路径硬化对符号链接的拒绝顺序不正确（2026-06-04 复核补充）

- **路径**：`backend/app/api/tasks.py`、`backend/app/api/exports.py`
- **描述**：`_safe_task_artifact_path()` 与 export artifact 回退逻辑先 `resolve(strict=False)`，再检查 `is_symlink()`；这样会检查“解析后的目标路径”，不能正确拒绝原始输入路径本身是符号链接的情况。
- **修复**：改为先检查原始 `Path(...).expanduser()` 是否为 symlink，再做 `resolve()` 与 task-root 约束。
- **验证**：新增 `test_download_export_rejects_symlink_artifact_local_path` 与 `test_task_bundle_rejects_symlink_artifact_local_path`，定向通过。

### F-01｜严重｜`workers/stages/build_support.py` 语法错误阻断导入

- **描述**：f-string 内嵌套引号导致 `SyntaxError`，`pytest` 收集阶段即失败，Workers 与 `test_document` 无法加载。
- **修复**：提取 `route_label = route or "/dashboard"`，避免 f-string 嵌套 `'/dashboard'` 引号冲突。
- **验证**：`py_compile` 通过；`backend/tests` 可正常收集。

### F-02｜高｜生产代码残留调试探针（信息泄漏 + 旁路请求）

- **路径**：`backend/app/main.py`、`backend/app/api/tasks.py`
- **描述**：向 `127.0.0.1:7777` 上报异常/重试事件；500 响应带 `debug` 字段与 `X-IPRIGHT-Debug-*` 头；`/health` 含 `debug_probe`；重试失败事件写入 broker/redis/cwd。
- **修复**：删除 `_debug_report_*` 与所有 `#region debug` 调用；全局 500 仅返回通用 `INTERNAL_ERROR`；重试失败 `detail` 仅保留 `异常类型: 消息`。
- **验证**：`test_api_extended` 派发失败用例改为 fake `workers.celery_app` 模块，不依赖本机 Celery。

### F-03｜高｜公开下载接口路径穿越（bundle / export artifact 回退）

- **路径**：`backend/app/api/tasks.py`、`backend/app/api/exports.py`
- **描述**：`bundle/download` 与 `exports/.../download` 为免鉴权 URL；`Artifact.local_path` 若指向任务目录外文件，可被读入 ZIP 或直链下载。
- **修复**：新增 `_safe_task_artifact_path()`，限制在 `WORKSPACE_ROOT/tasks/{task_id}/`；export artifact 回退同样 `relative_to(task_root)` 并拒绝符号链接。
- **验证**：`test_api.py` 回退用例改为任务目录内路径；恶意路径将被拒绝。

### F-04｜高｜截图图片下载未校验 artifact 路径

- **路径**：`backend/app/api/tasks.py` → `download_task_screenshot_image`
- **修复**：复用 `_safe_task_artifact_path`，拒绝任务工作区外 `local_path`。
- **验证**：`test_task_screenshots_include_preview_url_and_image_download` 通过。

### F-05｜中｜空 ZIP 缓存导致 artifact 回退永不执行

- **路径**：`backend/app/api/tasks.py` → `download_task_bundle`
- **描述**：`_build_bundle` 生成 0 条目仍写出空 zip；因 `st_size > 0` 直接返回，`_hydrate_bundle_from_artifacts` 永不运行。
- **修复**：仅当 zip `namelist()` 非空时才复用缓存；损坏 zip 记录 warning 后重建。
- **验证**：`test_task_bundle_falls_back_to_artifact_local_paths` 通过。

### F-06｜中｜`force_safe_fallback` 覆盖已成功局部修复的模块页

- **路径**：`workers/stages/build_support.py` → `_synthesize_module_compile_files`
- **描述**：原逻辑在 `normalized != fallback_page` 时整页替换为 compile-safe 模板，抹掉 `RouteRecord` 等 TS 修复。
- **修复**：仅在 `force_safe_fallback and not changed` 时整页回退；保留增量修复结果。
- **验证**：`test_generate_task_app_code_repairs_module_compile_patterns_for_status_and_align` 等由 18 失败降至 14 失败（见 F-10）。

### F-07｜低｜`get_task_timeline` 未校验任务存在

- **路径**：`backend/app/api/tasks.py`
- **修复**：不存在任务时返回 404 `TASK_NOT_FOUND`，与其他子资源接口一致。

### F-08｜低｜`_build_bundle` 返回类型注解错误

- **路径**：`backend/app/api/tasks.py`
- **修复**：注解改为 `tuple[Path, str, Path, int]`，与实际返回值一致。

### F-09｜测试｜重试/幽灵构建/派发失败用例与现实现对齐

- **路径**：`backend/tests/test_api_extended.py`、`backend/tests/test_api.py`、`backend/tests/test_runtime_capture_flow.py`
- **修复**：
  - 幽灵 queued build 在 `start_build` 后应为 `aborted`；
  - 派发失败用例不 import 真实 Celery、先完成首构建再 retry；
  - 按 `event_type` 筛选 `task_retry_dispatch_failed`；
  - bundle/截图/导出回退路径放入任务目录；
  - `execute_capture_flow` 解包 3 返回值并在用例内 `create_all`。

### F-10｜测试｜capture 流程返回值契约

- **描述**：`execute_capture_flow` 返回 `(total, success_count, warnings)`，测试仍按 2 元组解包。
- **修复**：见 F-09。

### F-11｜中｜Worker support/compile 修复链与测试期望不一致（原 W-01）

- **路径**：`workers/stages/build_support.py`、`backend/tests/test_workers.py`
- **描述**：`generate_task_app_code` 在 LLM 未产出 support 文件时仍全量注入 `request_runtime`；`_synthesize_support_runtime_files` 枚举/`import.meta` 修复未标记 `changed`；编译回退阶段 `force_runtime_fallback` 覆盖 `as unknown as` 增量修复；`preserve_paths` 写入时被 `_strip_code_fence().strip()` 吃掉前导换行；终端安全页缺少固定标记文案。
- **修复**：
  - 初始 support 合成改为增量模式；仅在已有部分 LLM 内容时对 invalid support 启用 `force_runtime_fallback`；
  - 编译失败 support 路径仅用增量修复（不再全量替换 `api.ts`）；
  - 修复 `changed` 追踪、`import.meta` 变量引用、`apply_generated_code_bundle` 的 `preserve_paths`；
  - 终端安全模块页增加「当前页面已切换为终端编译安全模式」；`models.ts` 终端回退补充 `ApiResponse`/`PageResult`；
  - 模块占位页失败时走 `module_structural_fallback`（compile-safe），相关用例与 Dashboard 路由对齐。
- **验证**：`python3 -m pytest backend/tests/test_workers.py -q` → **158 passed, 1 skipped**；`python3 -m pytest backend/tests -q` → **298 passed, 2 skipped**。

---

## 4. 待跟进清单

| 编号 | 严重度 | 说明 |
|---|---|---|
| W-02 | 低 | 部分 Worker 用例执行时间较长（~70s），建议在 CI 中拆分 job 或标记慢测。 |

---

## 5. 模块健康度小结

| 模块 | 评级 | 说明 |
|---|---|---|
| Backend API | 良好 | 移除调试代码；下载与截图路径收敛；bundle 缓存逻辑修复 |
| 鉴权 (auth) | 良好 | 未改动 fail-closed 策略；公开下载面收敛到路径校验 |
| Workers / build_support | 良好 | support/compile/terminal 修复链与测试对齐 |
| Frontend | 良好 | `npx tsc --noEmit` 通过 |
| Worker 测试 | 良好 | 158 passed / 1 skipped（`test_workers.py`） |
| 全量测试 | 良好 | 298 passed / 2 skipped |

---

## 6. 改进建议（非阻塞）

1. 为 `Artifact.local_path` 写入侧增加「必须在 task 目录内」的校验，避免脏数据进入 DB。
2. 考虑将 `bundle/download` 改为短时签名 URL，降低长期公开链风险。
3. Worker support 修复链：已对 `api.ts` 采用「先增量、后全量 runtime」策略（见 F-11）；后续可考虑 AST 级修复降低正则误伤。
4. 统一测试库生命周期（`test_api.db` 与 engine 单例），减少偶发 `no such table`（本次已在 capture 用例内显式 `create_all` 缓解）。

---

## 7. 附录

### 7.1 验证结果

| 命令 | 结果（2026-06-03 复验） |
|---|---|
| `python3 -m py_compile`（见上） | 通过 |
| `python3 -m pytest backend/tests/test_workers.py -q` | **158 passed, 1 skipped** |
| `python3 -m pytest backend/tests -q` | **298 passed, 2 skipped** |
| `cd frontend && npx tsc --noEmit` | 通过（2026-05-26 基准） |

### 7.2 修改文件列表

```
backend/app/main.py
backend/app/api/tasks.py
backend/app/api/exports.py
workers/stages/build_support.py
backend/tests/test_api.py
backend/tests/test_api_extended.py
backend/tests/test_runtime_capture_flow.py
backend/tests/test_workers.py
docs/IPRIGHT_CODE_AUDIT_FIX_REPORT_2026-05-26.md
```

---

*报告由代码审计会话生成，未执行 git commit/push。*
