# IPRight deploy 总入口

`deploy/` 目录用于收敛 `IPRight` 的部署相关资产，包括部署文档、systemd 模板、Nginx 模板和生产基础设施配置。后续值班、上线、验收与回滚，建议优先从这里进入。

## 1. 目录用途

`deploy/` 下内容分为 4 类：

- `deploy/docs/`
  - 部署文档、验收清单、运维手册、发布 Runbook、部署报告
- `deploy/systemd/`
  - API / Worker 的 systemd 模板
- `deploy/nginx/`
  - Nginx 站点配置示例
- `deploy/docker-compose.production.yml`
  - 生产基础设施编排示例

## 2. 文档入口

推荐阅读顺序：

1. `deploy/docs/DEPLOYMENT_SOP_INDEX.md`
   - 统一入口页，适合值班和快速导航
2. `deploy/docs/IPRIGHT_ECS_DEPLOY_PRODUCTION_README.md`
   - 现网 ECS 主部署手册
3. `deploy/docs/DEPLOY_CHECKLIST.md`
   - 上线前后固定检查项
4. `deploy/docs/OPERATIONS_MANUAL.md`
   - 巡检、热修、回滚、真实任务复跑手册
5. `deploy/docs/PHASE1_RELEASE_RUNBOOK.md`
   - 当前阶段标准发布路径
6. `deploy/docs/PHASE1_RELEASE_GATES_AND_GRADUAL_ROLLOUT.md`
   - 发布门禁、灰度和回退触发条件
7. `deploy/docs/IPRIGHT_SSH_ACCESS_RUNBOOK.md`
   - SSH 最终入口、`2222` 值班口径与恢复记录
8. `deploy/docs/IPRIGHT_ECS_DEPLOY_REPORT_20260604.md`
   - 2026-06-04 真实 ECS 部署与 build 复跑报告
9. `deploy/docs/IPRIGHT_DEPLOYMENT_REFERENCE_MANUAL.md`
   - 生产部署补充手册

## 3. 配置模板

- `deploy/systemd/ipright-api.service`
  - API systemd 模板，当前基线为 `WorkingDirectory=/opt/ipright/current/backend`
- `deploy/systemd/ipright-worker.service`
  - Worker systemd 模板，当前基线为 `WorkingDirectory=/opt/ipright/current`
- `deploy/nginx/ipright.conf.example`
  - `ipright.tech` / `www.ipright.tech` 的 Nginx 示例
- `deploy/docker-compose.production.yml`
  - PostgreSQL / Redis / MinIO 等基础设施的生产编排参考

说明：

- 模板文件用于提供基线，不应假设和 ECS 实机配置始终完全一致
- 线上排障与核对应优先使用 `systemctl cat`、`nginx -t` 和 ECS 实际磁盘文件

## 4. 脚本入口

虽然脚本位于项目根目录 `scripts/`，但部署时通常与 `deploy/` 一起使用，建议记住以下入口：

- `scripts/ipright-ecs-full-deploy.sh`
  - ECS 本机全量部署
- `scripts/ipright-ecs-preflight-check.sh`
  - ECS 预检
- `scripts/ipright-release.sh`
  - 标准化 release 发布，带 `current` 软链切换
- `scripts/ipright-ecs-rerun-doc-fixes.sh`
  - 文档修复后的定向复跑辅助脚本

当前 SSH 入口基线：

- 远程登录、发布和巡检统一优先走 `admin@2222`
- 若本地使用 `~/.ssh/config`，建议把 `ipright-ecs` 映射到 `8.218.209.218:2222`
- 若临时不用别名，需为 `ssh`/`scp` 显式补 `-p 2222` / `-P 2222`

## 5. 使用原则

- 线上排障以 ECS 实机 `systemctl cat` 与 `/etc/nginx/conf.d/ipright.conf` 为准
- `deploy/` 下文件是模板、文档和参考基线，不应假设与线上实时完全一致
- 修改部署模板后，应同步检查 `deploy/docs/DEPLOYMENT_SOP_INDEX.md` 和 `deploy/docs/IPRIGHT_ECS_DEPLOY_PRODUCTION_README.md`
- 真实任务复跑与 build 追踪应统一按 `deploy/docs/DEPLOYMENT_SOP_INDEX.md` 的口径执行
