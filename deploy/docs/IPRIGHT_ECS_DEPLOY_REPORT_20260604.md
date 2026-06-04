# IPRight ECS 部署报告 2026-06-04

## 1. 背景

本次发布的目标是继续修复真实任务 `678ea318-a606-43a9-8298-17bb737ac6a1` 的前端生成与运行态问题，并把修复真正落实到 ECS 生产环境，而不是停留在本地测试通过。

## 2. 本次关键结论

- ECS 发布链路已恢复可用
- `ipright-api` 与 `ipright-worker` 已能稳定启动
- 真实任务重试链路已恢复，新的 build 可以持续递增
- build 失败面已从早期的 5 个前端文件逐步缩小
- 新一轮修复已将问题推进到 `verify_run` 阶段
- `verify_run` 的根因之一已确认是生成应用前端依赖版本不可安装：`typescript@5.4.0`
- 该问题已修为可安装版本：`typescript@5.4.5`、`vite@5.4.21`

## 3. 已踩过并确认的坑

### 3.1 Git 与工作目录

- 在 ECS 上进入本机 Mac 路径会得到 `fatal: not a git repository`
- `/opt/ipright/current` 可能是旧 release，不适合作为 Git 判断依据
- root 下操作 `/opt/ipright` 时，首次可能需要补：

```bash
git config --global --add safe.directory /opt/ipright
```

### 3.2 retry 接口

- `POST /api/v1/tasks/{task_id}/retry` 不能发送空 body
- 正确方式必须至少包含：

```bash
-H "Content-Type: application/json" -d '{}'
```

### 3.3 真实 build 跟踪

- retry 接口只返回 `task_id`，不会直接返回 `build_id`
- 正确查询方式是：

```bash
/api/v1/admin/builds?task_id=<task_id>
```

## 4. build 演进记录

### build 4

失败面：

- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/DatasourcesIdPage.tsx`
- `frontend/src/pages/DatasourcesNewPage.tsx`
- `frontend/src/pages/Login.tsx`
- `frontend/src/pages/TasksNewPage.tsx`

### build 5

失败面缩小为：

- `frontend/src/pages/SourcesIdPage.tsx`
- `frontend/src/pages/TasksPage.tsx`

对应根因：

- `PageHeader` 在当前 `antd` 版本不可用
- `records?: number` 却写入字符串 `'-'`

### build 7

- 已越过前端坏页阶段
- 失败点转移到 `verify_run`
- 确认运行态依赖安装失败，核心报错为 `typescript@5.4.0` 不可安装

### build 9

- 已在新依赖版本修复后重新触发
- 使用更新后的 `build_support.py`
- 需要继续以最新 build 为准跟踪最终结果

## 5. 本次落地修复

- `PageHeader` 命中时直接切换到 compile-safe fallback
- `records?: number` + `records: '-'` 自动放宽为 `number | string`
- 生成应用前端 devDependencies 调整为可安装版本：
  - `typescript = 5.4.5`
  - `vite = 5.4.21`
- 已补对应定向回归测试

## 6. 建议后续动作

1. 继续只以最新 build 为准追踪结果
2. 若再次失败，优先抓 `app_codegen_report.json`、生成应用 `package.json`、runtime logs
3. 将热修过的远端源码尽快回灌到 Git 主线，避免仓库与 ECS 漂移
4. 后续发布和值班统一从 `deploy/docs/DEPLOYMENT_SOP_INDEX.md` 进入
