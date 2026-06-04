# IPRight Phase 1 发布门禁与渐进式放量

本文档用于明确 `IPRight` 当前阶段发布的固定门禁，避免“代码已改但上线未真正生效”或“旧 build 结果覆盖新发布判断”。

## 1. 发布门禁

### Gate 1：代码门禁

- 目标变更已提交
- 本地关键测试通过
- 若涉及生成链或 worker，至少补充对应回归测试

### Gate 2：部署门禁

- ECS 上 `git rev-parse --short HEAD` 与目标 commit 一致
- `ipright-api` 与 `ipright-worker` 的 systemd 拓扑指向 `/opt/ipright/current`
- `bash scripts/ipright-ecs-full-deploy.sh` 无阻塞错误

### Gate 3：健康门禁

- `/health` 本机与公网均正常
- `nginx -t` 通过
- `systemctl is-active ipright-api ipright-worker nginx` 全为 `active`

### Gate 4：真实任务门禁

- retry 接口正确带 body
- 新 build_no 已递增
- 最新 build 进入运行态
- 若失败，必须以最新 build 为准，不允许用旧 build 结果回滚判断

## 2. 渐进式放量顺序

当前建议采用以下顺序：

1. 本地定向测试
2. ECS 部署与基础健康检查
3. 单个真实任务复跑
4. 观察最新 build 阶段流转
5. 若无新增失败模式，再扩大到更多任务或常规发布

## 3. 回退触发条件

满足以下任一条件，应立即停止继续放量：

- 发布后 API / Worker 无法启动
- 新 build 连续卡在 `queued`
- 最新 build 失败面比上一轮扩大
- 真实任务进入新的高危运行时错误且无快速定位线索

## 4. 本轮已知经验

- 不能把 `/opt/ipright/current` 当作 Git 判断依据
- 不能对 retry 接口发送空 body
- 不能只看服务启动成功，还必须看真实任务 build 结果
- 不能只看生成阶段通过，还必须继续看 `verify_run`
