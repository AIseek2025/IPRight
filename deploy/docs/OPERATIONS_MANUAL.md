# IPRight 运维手册

本文档用于沉淀 `IPRight` 日常值班、服务巡检、热修、回滚与真实任务复跑的标准操作。

## 1. 服务对象

- API：`ipright-api.service`
- Worker：`ipright-worker.service`
- Nginx：`nginx`
- 基础设施：PostgreSQL / Redis / MinIO

## 2. 常用巡检命令

### 2.1 systemd

```bash
sudo systemctl status ipright-api --no-pager | tail -n 30
sudo systemctl status ipright-worker --no-pager | tail -n 30
systemctl is-active ipright-api ipright-worker nginx
```

### 2.2 健康检查

```bash
curl -fsSL http://127.0.0.1:18000/health
curl -I https://ipright.tech/health
```

### 2.3 端口检查

```bash
sudo ss -ltnp | grep -E ':(80|443|18000|15432|16379|19000|19001)\\b'
```

## 3. 日志查看

### 3.1 API / Worker

```bash
sudo journalctl -u ipright-api -n 200 --no-pager
sudo journalctl -u ipright-worker -n 200 --no-pager
```

### 3.2 聚焦真实任务

```bash
sudo journalctl -u ipright-worker --no-pager | grep -E '678ea318-a606-43a9-8298-17bb737ac6a1|invalid frontend build artifacts|verify_run|Dependency installation/build failed' | tail -n 200
```

## 4. 真实任务操作

### 4.1 加载环境变量

```bash
set -a
. /opt/ipright/backend/.env.production
set +a
```

### 4.2 重试任务

注意：retry 请求体不能为空，最少需要 `-d '{}'`。

```bash
curl -sS \
  -X POST \
  -H "Authorization: Bearer $IPRIGHT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "http://127.0.0.1:18000/api/v1/tasks/<task_id>/retry" \
  | python3 -m json.tool
```

### 4.3 取消当前运行中的 build

```bash
curl -sS \
  -X POST \
  -H "Authorization: Bearer $IPRIGHT_API_TOKEN" \
  "http://127.0.0.1:18000/api/v1/tasks/<task_id>/cancel" \
  | python3 -m json.tool
```

### 4.4 查询最新 build

```bash
curl -sS \
  -H "Authorization: Bearer $IPRIGHT_ADMIN_TOKEN" \
  "http://127.0.0.1:18000/api/v1/admin/builds?task_id=<task_id>" \
  | python3 -m json.tool
```

## 5. 热修路径

当 GitHub push 或 ECS `git pull` 暂时不可用，但已确认需要紧急验证远端修复时，可使用：

1. 本地修补源码
2. 用 `scp` 上传到 ECS `/tmp/`
3. 用 `sudo install -m 644` 覆盖 `/opt/ipright/...` 与 `/opt/ipright/current/...`
4. 重启 `ipright-api` 与 `ipright-worker`
5. 重新触发真实任务验证

说明：

- 热修只适合应急验证，不替代正式 Git 发布
- 热修完成后仍需把同样变更提交回仓库

## 6. 回滚路径

### 6.1 release 目录回滚

如果使用 `scripts/ipright-release.sh` 发布：

```bash
readlink -f /opt/ipright/current
sudo ln -sfn /opt/ipright/releases/<old_release_id> /opt/ipright/current
sudo systemctl restart ipright-api ipright-worker
```

### 6.2 固定目录回滚

如果是直接在 `/opt/ipright` 原地热修，回滚需要：

- 从 Git checkout 回目标版本
- 或重新发布上一可用 commit
- 再重启服务并重新验收

## 7. 常见问题

- `fatal: detected dubious ownership`：补 `safe.directory`
- `retry` 422：补 `Content-Type: application/json` 与 `-d '{}'`
- `BUILD_ALREADY_RUNNING`：先查最新 build，再决定是否取消
- `verify_run.install_commands` 失败：优先看生成应用 `frontend/package.json` 和安装日志
- `playwright install-deps chromium` 报 `apt-get: command not found`：在当前 `dnf/yum` 系 ECS 上通常不是发布阻塞项，应结合系统包是否已安装判断
