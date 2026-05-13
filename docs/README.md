# IPRight 产品设计文档索引

本文档集用于定义 `IPRight` 的完整产品设计方案。`IPRight` 的目标不是只做“AI 生成代码”，而是完成一条可交付的软著材料自动化产线：从关键词输入，到 PRD、开发、运行、截图、说明书 Word、源代码 Word，再到平台前端下载。

## 文档清单

1. `IPRIGHT_PRODUCT_BLUEPRINT.md`
   - 项目总纲
   - 产品目标
   - 用户角色
   - 核心价值
   - 关键设计原则

2. `IPRIGHT_PRD.md`
   - 平台 PRD
   - 用户旅程
   - 功能模块
   - 页面设计
   - 任务状态流
   - 运营与权限约束

3. `IPRIGHT_TECH_ARCHITECTURE.md`
   - 技术选型
   - 系统分层
   - 核心服务
   - 数据模型
   - 异步任务与存储设计
   - 安全与可观测性

4. `IPRIGHT_DOCUMENT_PIPELINE_DESIGN.md`
   - 两份 Word 文档的生成方案
   - 自动运行与自动截图方案
   - 页面截图插入说明书的编排逻辑
   - 60 页以上源码储备与源码文档导出算法
   - 软著格式规范映射

5. `IPRIGHT_DOCUMENT_GENERATION_RULES.md`
   - 软件说明书 / 操作手册长期制作规范
   - 源代码文档长期制作规范
   - 禁止项、截图标准、架构图标准、双源码文档输出标准

5. `IPRIGHT_APP_CONTRACT.md`
   - 生成应用必须遵守的运行、截图、源码导出契约
   - Manifest 规范
   - 页面、登录、演示数据要求

6. `IPRIGHT_DELIVERY_PLAN.md`
   - 分阶段建设路线
   - 里程碑
   - 风险与缓解策略
   - MVP 到正式版的推进顺序

7. `IPRIGHT_API_AND_DATA_SCHEMA.md`
   - API 清单
   - 数据表设计
   - 工件与导出模型

8. `IPRIGHT_WORKFLOW_STATE_MACHINE.md`
   - 任务状态机
   - 阶段转移
   - 重试与失败收口

9. `IPRIGHT_PROMPT_AND_AGENT_CONTRACTS.md`
   - LLM 与 Agent 的职责边界
   - Prompt 输出契约
   - 结构化 JSON 约束

10. `IPRIGHT_CODEMASTER_HANDOFF.md`
   - 交给 `CodeMaster` 的无人值守开发交接说明
   - 开发优先级
   - 验收门槛

11. `IPRIGHT_ACCEPTANCE_AND_TEST_PLAN.md`
   - 平台验收标准
   - 阶段测试矩阵
   - 自动化测试与人工抽检建议

12. `IPRIGHT_DEPLOYMENT_REFERENCE_MANUAL.md`
   - 生产部署、预检、Playwright 修复与任务复跑手册

13. `IPRIGHT_CLEANUP_STRATEGY_AND_RESULT.md`
   - 本地工作区与 ECS 的瘦身边界、清理策略与实际结果

14. `IPRIGHT_REPOSITORY_RETENTION_AND_REFACTOR_PLAN.md`
   - 仓库长期保留、淘汰、合并与目录整顿方案

15. `codemaster/DEEPSEEK_MODEL_ROUTING_POLICY.md`
   - `deepseek-v4-pro` 与 `deepseek-v4-flash` 的职责分工
   - `CodeMaster` 主开发链、说明书链、终审链的模型选择规则
   - 思考模式、验收边界与旧别名迁移要求

## 关键约束

- 软著说明书格式要求与源码格式要求，已从 `软件源代码文档和软件说明书操作手册撰写说明及格式规范.md` 中提炼并映射到本设计中。
- 源码文档必须满足：
  - 只输出 1 份完整源码文档 `source_code_book.docx`
  - 每页不少于 50 行
  - 页眉包含软件名称和版本号
  - 右上角连续页码
- 软件说明书必须满足：
  - 必须包含：引言、开发设计/系统设计、软件使用说明三大主体模块
  - 引言中需覆盖开发背景、开发目的、适用领域
  - 开发设计/系统设计中需覆盖开发技术说明、系统架构图、运行/适配环境、技术特性、核心功能/主要功能/功能元素
  - 软件使用说明应尽量详细，覆盖主要页面、核心流程、关键操作与结果说明
  - 每页不少于 30 行
  - 页眉包含软件名称和版本号
  - 右上角连续页码
  - 内容必须与真实软件和真实截图对应
-  - 系统架构图必须真实生成并插入文档，不能只留文字占位
- 源码文档必须满足：
-  - 生成应用的真实业务代码总量应达到 60 页以上，不能只靠最小骨架勉强凑页
-  - 平台只输出 1 份完整源码文档 `source_code_book.docx`，文档内需包含纳入代码索引的全部源代码
-  - 当前产品功能设计必须把“总代码页数 > 60”作为硬性目标，而不是可选优化

## 本方案的核心判断

为了让“自动运行产品并截图”真正稳定，平台不能允许“任意形态的生成应用直接进入截图阶段”。因此本方案引入：

- `IPRight App Contract`
- `Run Manifest`
- `Capture Manifest`
- `Code Index Manifest`

只有符合这些契约的生成产物，才能进入自动运行、截图和 Word 生成流水线。这是 `IPRight` 成功落地的核心。
