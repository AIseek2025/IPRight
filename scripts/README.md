# IPRight 脚本分层说明

`scripts/` 目录只保留对项目交付、部署、验证和开发辅助有明确价值的脚本。

## 生产部署与运维

- `ipright-ecs-full-deploy.sh`
  - ECS 全量部署脚本
- `ipright-ecs-preflight-check.sh`
  - ECS 上线前预检脚本
- `ipright-release.sh`
  - 基于 Git 提交的标准化发布脚本
- `ipright-ecs-rerun-doc-fixes.sh`
  - 文档修复后的 ECS 定向复跑脚本

## 本地开发与验证

- `start_all.sh`
  - 本地启动入口
- `run_tests.sh`
  - 本地测试入口
- `docker_verify.sh`
  - Docker 场景验证辅助
- `verify_project.py`
  - 项目级校验辅助

## 开发辅助脚本

- `demo_runner.py`
- `regenerate_latest_docs.py`
- `ecs_acceptance_pull.py`
- `export_pdf.py`
- `e2e_pipeline.py`

以上脚本可保留，但默认视为开发辅助，不应替代正式 worker 编排链路。

## 清理原则

- 与正式发布链路重复实现的脚本，应优先降级为辅助工具或逐步淘汰。
- 新增脚本前，优先复用现有部署、预检、发布入口，避免形成新的平行流水线。
