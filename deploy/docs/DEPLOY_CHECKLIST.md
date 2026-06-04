# IPRight 上线检查清单

本清单用于在 `IPRight` 每次 ECS 发布前后做固定检查，避免遗漏 `safe.directory`、`current` 拓扑、重试接口 body、真实任务复跑等已踩过的坑。

## 1. 发布前

- [ ] 本地工作树干净，关键改动已提交
- [ ] 目标 commit 已存在于远端 `origin/main`
- [ ] 已确认本次变更涉及的测试至少完成定向回归
- [ ] 已确认 ECS 有 `python3.11`、`node`、`npm`、`nginx`、`systemd`、`docker`、`rsync`
- [ ] 已确认 `/opt/ipright/backend/.env.production` 存在且内容最新
- [ ] 已确认 `/opt/ipright/shared/tmp` 存在且权限可用于 `TMPDIR`
- [ ] 已确认 `/opt/ipright/shared/ms-playwright` 可写且浏览器已安装

## 2. 发布时

- [ ] 在 ECS 上以 `/opt/ipright` 作为 Git 工作目录
- [ ] 如首次或 root 下操作 Git，已执行 `git config --global --add safe.directory /opt/ipright`
- [ ] 如走 `current` release 拓扑，已确认 systemd 的 `WorkingDirectory/ExecStart/PYTHONPATH` 指向 `/opt/ipright/current`
- [ ] 已执行 `bash scripts/ipright-ecs-full-deploy.sh` 或 `scripts/ipright-release.sh`
- [ ] 前端构建成功，`npm ci` / `npm run build` 无错误
- [ ] `alembic upgrade head` 成功
- [ ] 静态资源已发布到 `/var/www/ipright/releases/<timestamp>` 并更新 `/var/www/ipright/current`

## 3. 发布后基础验收

- [ ] `curl -fsSL http://127.0.0.1:18000/health` 返回 `200`
- [ ] `systemctl is-active ipright-api ipright-worker nginx` 全部为 `active`
- [ ] `sudo nginx -t` 通过
- [ ] `sudo ss -ltnp | grep -E ':(80|443|18000)\\b'` 符合预期
- [ ] `curl -I https://ipright.tech/` 成功
- [ ] `curl -I https://ipright.tech/health` 成功

## 4. 真实任务验收

- [ ] 使用 `-d '{}'` 方式调用 retry 接口
- [ ] `admin/builds?task_id=...` 能看到新的 build_no 递增
- [ ] build 能进入 `plan` 与 `build`，不再卡在 `queued`
- [ ] 若失败，已记录最新失败文件或阶段，不使用历史 build 误判
- [ ] 若出现 `BUILD_ALREADY_RUNNING`，已确认当前确有运行中的 build

## 5. 复跑排障补记

- [ ] 已保存本次 build_id
- [ ] 已保存关键 worker 日志
- [ ] 已保存 `app_codegen_report.json` 或 runtime 相关日志
- [ ] 已将本次结论同步到部署报告或事故报告
