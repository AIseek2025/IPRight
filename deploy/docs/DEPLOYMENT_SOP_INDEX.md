# IPRight 部署 SOP 索引

本文件用于把 `IPRight` 的生产部署、上线验收、值班排障与历史发布报告收敛为一个入口页。后续所有 ECS 发布、复跑、回滚与巡检，统一从这里进入。

## 1. 生产架构口径

- 域名：`https://ipright.tech`
- 代码根目录：`/opt/ipright`
- 当前发布目录：`/opt/ipright/current`
- 后端 API：`127.0.0.1:18000`
- 前端静态目录：`/var/www/ipright/current`
- API 服务：`ipright-api.service`
- Worker 服务：`ipright-worker.service`
- Nginx 配置：`/etc/nginx/conf.d/ipright.conf`
- 生产环境文件：`/opt/ipright/backend/.env.production`
- 任务工作区：`/opt/ipright/shared/workspace`

固定验收门槛：

- `GET http://127.0.0.1:18000/health` 必须返回 `200`
- `systemctl is-active ipright-api ipright-worker nginx` 必须为 `active`
- `https://ipright.tech/health` 必须返回 `200`
- 真实任务重试后，最新 build 必须能进入 `plan/build`，不能卡在 `queued`
- 查询真实任务 build 时，不允许继续出现已知的陈旧失败模式且无人跟进

## 2. 一键入口

推荐优先顺序：

1. ECS 本机全量部署：`scripts/ipright-ecs-full-deploy.sh`
2. ECS 上线前预检：`scripts/ipright-ecs-preflight-check.sh`
3. 标准化版本发布：`scripts/ipright-release.sh <ssh_target> [remote_app_root]`
4. 文档修复后定向复跑：`scripts/ipright-ecs-rerun-doc-fixes.sh`

说明：

- `ipright-ecs-full-deploy.sh` 适合在 ECS 本机或已切到目标 release 后执行，负责 venv、迁移、前端构建、静态发布、systemd 重启与健康检查。
- `ipright-release.sh` 适合从本地把一个明确 Git commit 发布到 ECS，带 release 目录与 `current` 软链切换。
- 如果服务器上的 `current` 不是最新代码，请优先修正 `current` 拓扑，不要直接在旧 release 上排障。

## 3. 最短 SOP

### 3.1 本地准备

```bash
cd /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight
python3 -m pytest backend/tests/test_workers.py -q
```

如需完整预检，可加跑：

```bash
bash scripts/ipright-ecs-preflight-check.sh
```

### 3.2 ECS 发布

在 ECS 本机执行：

```bash
cd /opt/ipright
git config --global --add safe.directory /opt/ipright
git pull --ff-only origin main
bash scripts/ipright-ecs-full-deploy.sh
```

若采用标准 release 目录方式：

```bash
cd /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight
scripts/ipright-release.sh admin@8.218.209.218 /opt/ipright
```

### 3.3 ECS 本机验收

```bash
curl -fsSL http://127.0.0.1:18000/health
sudo systemctl status ipright-api --no-pager | tail -n 20
sudo systemctl status ipright-worker --no-pager | tail -n 20
sudo nginx -t
sudo ss -ltnp | grep -E ':(80|443|18000)\\b'
```

### 3.4 公网验收

```bash
curl -I https://ipright.tech/
curl -I https://ipright.tech/health
```

### 3.5 真实任务复跑验收

```bash
set -a
. /opt/ipright/backend/.env.production
set +a

curl -sS \
  -X POST \
  -H "Authorization: Bearer $IPRIGHT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "http://127.0.0.1:18000/api/v1/tasks/678ea318-a606-43a9-8298-17bb737ac6a1/retry" \
  | python3 -m json.tool

curl -sS \
  -H "Authorization: Bearer $IPRIGHT_ADMIN_TOKEN" \
  "http://127.0.0.1:18000/api/v1/admin/builds?task_id=678ea318-a606-43a9-8298-17bb737ac6a1" \
  | python3 -m json.tool
```

## 4. 值班排障导航

- `BUILD_ALREADY_RUNNING`：优先查 `admin/builds?task_id=...`，确认是否已有新 build 在跑，再决定是否 `cancel`。
- `retry` 返回 `422 Field required`：说明 body 缺失，必须使用 `-H 'Content-Type: application/json' -d '{}'`。
- ECS `git pull` 提示 `dubious ownership`：先执行 `git config --global --add safe.directory /opt/ipright`。
- `/opt/ipright/current` 落后：不要在旧 release 上做 Git 判断，统一以 `/opt/ipright` 为 Git 工作目录。
- 前端 build artifacts invalid：优先查看 `app_codegen_report.json`、`workspace/app/frontend/package.json` 与 worker 日志中的精确报错文件。
- `verify_run` 失败：优先排查生成应用依赖安装、运行时端口探活和生成 workspace 的 `package.json`/runtime logs。

## 5. 文档索引

- 生产主手册：`deploy/docs/IPRIGHT_ECS_DEPLOY_PRODUCTION_README.md`
- 上线检查清单：`deploy/docs/DEPLOY_CHECKLIST.md`
- 运维手册：`deploy/docs/OPERATIONS_MANUAL.md`
- 发布 Runbook：`deploy/docs/PHASE1_RELEASE_RUNBOOK.md`
- 发布门禁与灰度：`deploy/docs/PHASE1_RELEASE_GATES_AND_GRADUAL_ROLLOUT.md`
- deploy 目录说明：`deploy/README.md`
- 2026-06-04 真实部署报告：`deploy/docs/IPRIGHT_ECS_DEPLOY_REPORT_20260604.md`
- 审计修复报告：`docs/IPRIGHT_CODE_AUDIT_FIX_REPORT_2026-05-26.md`
- 独立交付检查：`docs/IPRIGHT_INDEPENDENT_DELIVERY_CHECKLIST.md`
