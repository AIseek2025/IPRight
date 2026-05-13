# IPRight 仓库保留、淘汰与整顿方案

## 1. 文档目的

本文档从“总设计师”视角，对当前 `IPRight` 仓库做长期治理规划，回答三个问题：

1. 哪些模块应长期保留
2. 哪些目录或实现应合并
3. 哪些模块、文档或旁路实现应逐步淘汰

本文档描述的是仓库整顿方案，不等同于一次性代码改造实施记录。

## 2. 当前总体判断

当前仓库的大方向是正确的：

- `backend/` 负责平台 API、数据模型、公共服务
- `workers/` 负责异步任务编排与各阶段执行
- `frontend/` 负责平台运营控制台
- `examples/demo_app/` 当前实际承担“生成应用种子模板”职责

问题不在主干架构，而在以下三个层面：

1. 阶段执行逻辑过度集中
2. 模板源与旁路脚本重复
3. 文档体系冗余且层级混杂

## 3. 长期保留项

### 3.1 平台主干

以下目录应长期保留：

- `backend/`
- `workers/`
- `frontend/`
- `deploy/`
- `scripts/` 中真正服务生产部署、验证、复跑的脚本

理由：

- 这是平台自身的主产品边界
- 它们共同构成任务创建、任务编排、任务执行、产物生成和下载闭环

### 3.2 共享服务层

以下能力应长期保留，并继续沉淀为稳定服务层：

- `backend/app/services/runtime`
- `backend/app/services/capture`
- `backend/app/services/document`
- `backend/app/services/llm`

理由：

- 这些模块不是临时逻辑，而是平台“运行、截图、文档、模型接入”的核心基础设施
- 后续应强化服务边界，而不是把更多逻辑堆回 stage handler

### 3.3 生成应用种子

`examples/demo_app/` 当前不应删除。

理由：

- 当前 Worker 的 `build` 阶段直接复制该目录作为生成应用起点
- 多个脚本与验证链路都依赖它
- 它在语义上更接近“模板种子”而非普通 example

长期建议：

- 后续将其重命名为更准确的目录，如：
  - `templates/demo_app_seed`
  - `seed_apps/demo_app`

### 3.4 共享静态资产

`assets/` 应保留。

当前最关键的共享资源是：

- `assets/fonts/IPRightCJK.ttf`

理由：

- 这是生成应用中文界面和截图稳定性的基础资产
- 不应散落到各前端目录中各自维护

## 4. 应合并的部分

### 4.1 状态映射

当前状态机映射存在重复定义。

建议：

- 统一只保留 `backend/app/core/state_machine.py`
- Worker 不再维护单独的 `_status_to_stage` 映射

目标：

- 消除状态推进逻辑的双份维护
- 避免阶段命名和状态命名未来发生漂移

### 4.2 Stage 文件组织

当前 `workers/stages/handlers.py` 承担过多职责。

建议拆分为：

- `workers/stages/plan.py`
- `workers/stages/build.py`
- `workers/stages/verify.py`
- `workers/stages/capture.py`
- `workers/stages/compose.py`
- `workers/stages/publish.py`

保留：

- `register_stage()` 的统一注册入口

目标：

- 降低单文件复杂度
- 便于按阶段单独测试、单独演进、单独排障

### 4.3 模板源

当前生成链路存在双模板源：

- 一套来自 `examples/demo_app`
- 一套来自 `workers/stages/handlers.py` 中的大段内嵌模板函数

建议：

- 只保留一种模板源
- 优先建议保留 `examples/demo_app` 为唯一可见模板基线

目标：

- 避免修改模板时需要双处同步
- 避免“复制种子应用”与“覆盖内嵌模板”并行造成逻辑重叠

### 4.4 启动与部署文档

以下文档主题明显重叠：

- `GETTING_STARTED.md`
- `DOCKER_RUNBOOK.md`
- `IPRIGHT_ECS_DEPLOY_PRODUCTION_README.md`
- `IPRIGHT_DEPLOYMENT_REFERENCE_MANUAL.md`

建议：

- 合并本地启动与 Docker 启动文档
- 合并正式部署、运维排障、复跑手册

目标：

- 让文档树回到“每类主题一份主文档”的稳定状态

## 5. 应淘汰的部分

### 5.1 空壳目录

`workers/tasks/` 当前没有明确职责，应淘汰。

原则：

- 没有真实任务实现的空包，不应长期保留制造“结构存在感”

### 5.2 平行流水线脚本

部分脚本在功能上重复实现正式链路，应逐步退场或降级为开发辅助：

- `scripts/e2e_pipeline.py`

建议：

- 若保留，则明确标记为“开发辅助脚本”
- 更理想的方向是改为调用正式编排链路，而不是维护一套平行实现

### 5.3 外项目遗留文档

以下文档不属于 `IPRight`：

- `docs/AIAds_ECS_DEPLOY_PRODUCTION_README.md`

建议：

- 直接淘汰

理由：

- 会污染项目文档边界
- 会误导后续维护者

### 5.4 二进制样本文档

长期不建议继续在仓库中保留：

- `pdf`
- `doc`
- `docx`

理由：

- 仓库核心应保留源码与 Markdown 设计资料
- 二进制文档体积大、不可 diff、不可稳定审阅

## 6. 应归档的部分

以下文档更适合迁入 `docs/archive/`：

- `STATUS_REPORT.md`
- `WORK_SUMMARY_PHASE*.md`
- `IPRIGHT_FINAL_REPORT.md`
- `IPRIGHT_ACCEPTANCE_REPORT.md`
- `IPRIGHT_UPDATE_SUMMARY_*.md`
- `IPRIGHT_RECENT_REPAIR_SUMMARY_*.md`
- `IPRIGHT_REDEPLOY_AND_RERUN_*.md`
- `IPRIGHT_CODE_AUDIT_REPORT_*.md`

原因：

- 它们有历史价值
- 但不应继续占据主文档入口

## 7. 推荐目标目录形态

建议长期演化为：

```text
backend/
frontend/
workers/
assets/
deploy/
scripts/
docs/
  archive/
  README.md
templates/ 或 seed_apps/
```

其中：

- `examples/demo_app/` 最终迁入 `templates/` 或 `seed_apps/`
- `docs/` 只保留主文档、手册与归档
- `workers/stages/` 按阶段拆分，不再保留超级 `handlers.py`

## 8. 建议实施顺序

### P1

- 拆分 `workers/stages/handlers.py`
- 统一状态机映射来源
- 统一模板源

### P2

- 精简 `scripts/` 中的平行流水线脚本
- 清理空壳目录
- 淘汰外项目遗留文档

### P3

- 建立 `docs/archive/`
- 把历史报告、阶段总结、修复记录归档
- 重命名 `examples/demo_app` 为模板语义目录

## 9. 最终结论

`IPRight` 当前真正应该长期保留的是：

- 平台主干
- 异步编排骨架
- 共享服务层
- 生成应用种子模板
- 共享字体与必要资产
- 核心 Markdown 文档

真正需要整顿的重点是：

- 超级 stage 文件
- 双模板源
- 平行验证脚本
- 冗余文档层次

因此后续治理方向不是“大拆大重写”，而是：

- 保主干
- 并重复
- 清空壳
- 归历史
