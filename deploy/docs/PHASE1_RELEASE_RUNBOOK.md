# IPRight Phase 1 发布 Runbook

本文档定义 `IPRight` 当前阶段的标准发布动作，重点覆盖 ECS 正式环境的“预检 -> 发布 -> 验收 -> 真实任务复跑 -> 报告沉淀”。

## 1. 适用范围

适用于以下场景：

- Worker / `build_support.py` / `runtime_support.py` 热修
- 前后端联动修复上线
- 审计修复上线
- 真实任务复跑验证

## 2. 发布前门槛

发布前至少满足：

- 关键测试已通过
- 变更已提交
- 目标 commit 可追踪
- 已确认 ECS 当前运行目录与 `current` 拓扑
- 已准备发布后要复跑的真实任务 id

## 3. 标准发布路径

### 路径 A：ECS 本机原地部署

```bash
cd /opt/ipright
git config --global --add safe.directory /opt/ipright
git pull --ff-only origin main
bash scripts/ipright-ecs-full-deploy.sh
```

### 路径 B：本地标准化 release 发布

```bash
cd /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight
scripts/ipright-release.sh admin@8.218.209.218 /opt/ipright
```

## 4. 发布后验收

### 4.1 基础服务

```bash
curl -fsSL http://127.0.0.1:18000/health
sudo systemctl status ipright-api --no-pager | tail -n 20
sudo systemctl status ipright-worker --no-pager | tail -n 20
```

### 4.2 公网入口

```bash
curl -I https://ipright.tech/
curl -I https://ipright.tech/health
```

### 4.3 真实任务复跑

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
```

## 5. 发布后记录

每次正式发布后至少补记：

- commit id
- 部署方式
- ECS 健康检查结果
- 真实任务 build_no / build_id
- 若失败，失败阶段与失败文件
- 对应报告文档路径
