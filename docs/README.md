# IPRight 文档索引

本文档集用于维护 `IPRight` 的长期设计、部署、运维与治理资料。主文档区只保留当前仍有效、应长期维护的资料；阶段性报告、审计和修复纪要统一收敛到 `docs/archive/`。

## 主文档

1. `IPRIGHT_PRODUCT_BLUEPRINT.md`
   - 项目总纲、产品目标、核心价值、关键设计原则

2. `IPRIGHT_PRD.md`
   - 平台 PRD、用户旅程、功能模块、页面设计、任务状态流

3. `IPRIGHT_TECH_ARCHITECTURE.md`
   - 技术选型、系统分层、核心服务、数据模型、可观测性

4. `IPRIGHT_DOCUMENT_PIPELINE_DESIGN.md`
   - 说明书、源码文档、自动运行、自动截图的总设计

5. `IPRIGHT_DOCUMENT_GENERATION_RULES.md`
   - 说明书和源码文档的长期制作规范与禁止项

6. `IPRIGHT_APP_CONTRACT.md`
   - 生成应用的运行、截图、源码导出契约与 manifest 约束

7. `IPRIGHT_API_AND_DATA_SCHEMA.md`
   - API、数据表、导出与工件模型

8. `IPRIGHT_WORKFLOW_STATE_MACHINE.md`
   - 任务状态机、阶段转移、失败与重试收口

9. `IPRIGHT_PROMPT_AND_AGENT_CONTRACTS.md`
   - LLM 与 Agent 的职责边界、结构化输出契约

10. `IPRIGHT_ACCEPTANCE_AND_TEST_PLAN.md`
   - 验收标准、测试矩阵、自动化与人工抽检建议

## 运维与治理

1. `IPRIGHT_DEPLOYMENT_REFERENCE_MANUAL.md`
   - 生产部署、预检、Playwright 修复、任务复跑手册

2. `IPRIGHT_ECS_DEPLOY_PRODUCTION_README.md`
   - 现网 ECS 部署说明与环境约束

3. `IPRIGHT_CLEANUP_STRATEGY_AND_RESULT.md`
   - 本地与 ECS 瘦身边界、清理策略与实际结果

4. `IPRIGHT_REPOSITORY_RETENTION_AND_REFACTOR_PLAN.md`
   - 仓库长期保留、合并、淘汰、归档方案

5. `IPRIGHT_INDEPENDENT_DELIVERY_CHECKLIST.md`
   - 新任务独立开发、页面与文档自检清单

## 归档区

- `archive/`
  - 收纳历史阶段报告、验收结论、修复纪要、重部署记录、代码审计报告
  - 归档文档保留历史参考价值，但不再作为当前主设计或主运维入口

## 关键约束

- 说明书与源码规范已从 `软件源代码文档和软件说明书操作手册撰写说明及格式规范.md` 提炼并映射到本项目设计中。
- `source_code_book.docx` 只保留 1 份完整源码文档，页眉包含软件名称与版本号，右上角连续页码。
- 软件说明书必须覆盖引言、开发设计/系统设计、软件使用说明，并与真实软件、真实截图严格对应。
- 系统架构图必须真实生成并插入文档，不能只保留文字占位。
- 生成应用的真实业务代码总量应达到 60 页以上，不能依赖最小骨架凑页。

## 核心判断

为了让“自动运行产品并截图”长期稳定，平台不能允许任意形态的生成应用直接进入截图阶段。因此必须坚持以下契约：

- `IPRIGHT App Contract`
- `Run Manifest`
- `Capture Manifest`
- `Code Index Manifest`

只有符合这些契约的生成产物，才能进入自动运行、截图和 Word 生成流水线。
