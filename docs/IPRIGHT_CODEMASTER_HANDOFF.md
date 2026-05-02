# IPRight 交付给 CodeMaster 的开发交接包

## 1. 当前阶段说明

当前 `IPRight` 只进行设计文档输出，不进入代码开发。  
后续将由 `CodeMaster` 按本交接包进行全自动无人值守开发。<mccoremem id="01KQFYYKYCTWYQA533H3R1QC7A" />

## 2. 开发目标

让 `CodeMaster` 在独立工作区内无人值守完成：

1. 平台前端
2. 平台后端
3. 任务编排
4. Agent 自动运行与截图
5. 说明书 Word 生成
6. 源码 Word 生成
7. 下载交付

补充硬标准：

- 每份说明书必须包含引言、开发设计 / 系统设计、软件使用说明三大主体模块
- 每份说明书必须插入真实生成的系统架构图
- 每份源码文档必须以“真实业务代码总量大于 60 页”为目标

## 3. 必读文档顺序

建议 `CodeMaster` 启动开发前按以下顺序深读：

1. `README.md`
2. `IPRIGHT_PRODUCT_BLUEPRINT.md`
3. `IPRIGHT_PRD.md`
4. `IPRIGHT_TECH_ARCHITECTURE.md`
5. `IPRIGHT_APP_CONTRACT.md`
6. `IPRIGHT_DOCUMENT_PIPELINE_DESIGN.md`
7. `IPRIGHT_API_AND_DATA_SCHEMA.md`
8. `IPRIGHT_WORKFLOW_STATE_MACHINE.md`
9. `IPRIGHT_PROMPT_AND_AGENT_CONTRACTS.md`
10. `IPRIGHT_DELIVERY_PLAN.md`

## 4. 开发优先级

## P0

- 任务系统
- 阶段状态机
- 工件存储
- 导出下载链

## P1

- PRD 与开发任务书生成
- 标准应用契约
- 运行与健康检查

## P2

- Playwright 截图链
- 说明书 Word 编排
- 源码 Word 编排
- 架构图生成与插图编排
- 代码体量扩展，确保源码文档达到 60 页以上标准

## P3

- 管理台
- 重试能力
- 监控与审计

## 5. 第一版目录建议

```text
IPRight/
  frontend/
  backend/
  workers/
  docs/
  templates/
  examples/
  scripts/
```

### 说明

- `frontend/`：任务创建、任务详情、下载页
- `backend/`：API 与任务调度
- `workers/`：AI、运行、截图、导出 Worker
- `templates/`：Word 模板与说明书模板
- `examples/`：标准生成应用示例

## 6. 首个实现闭环

建议 `CodeMaster` 先只打通一条最小闭环：

1. 创建任务
2. 生成后台管理型 PRD
3. 生成标准 Demo 应用
4. 启动应用
5. 抓取 4-6 张关键页面截图
6. 输出一份包含引言 / 系统设计 / 使用说明 / 图示的说明书 Word
7. 输出一份达到 60 页以上目标的源码 Word
8. 前端下载

不要首轮就支持太多应用类型。

## 7. 强约束

### 不可跳过

- App Contract
- Run Manifest
- Capture Manifest
- Code Index Manifest
- Manual Outline / Diagram Spec
- 状态机
- 工件落盘

### 不建议先做

- 多租户复杂权限
- 多语言支持
- 任意技术栈兼容
- 移动端截图

## 8. 建议的技术冻结项

首版建议固定：

- 前端：`React + Vite + TypeScript`
- 后端：`FastAPI`
- 数据库：`PostgreSQL`
- 队列：`Redis + Celery`
- 截图：`Playwright`
- Word：`python-docx`
- 存储：`MinIO`
- 沙箱：`Docker`

## 9. 首版验收门槛

交给 `CodeMaster` 的首版验收标准：

- 能创建任务
- 能显示状态时间线
- 能成功输出 PRD
- 能生成符合契约的标准应用
- 能自动运行并截图
- 能生成包含引言 / 系统设计 / 使用说明 / 系统架构图的说明书 Word
- 能生成达到 60 页以上目标的源码 Word
- 能下载两份文档

## 10. 质量红线

以下任一情况视为未完成：

- 说明书与页面不一致
- 截图不是来自真实运行页面
- 说明书缺少引言 / 系统设计 / 使用说明主体模块
- 说明书缺少真实系统架构图
- 源码文档混入第三方依赖
- 源码真实业务代码总量不足 60 页
- 两份文档不是同一构建版本
- 导出链只能本地看、不能前端下载

## 11. 风险提醒

最容易失败的点不是模型写 PRD，而是：

- 生成应用启动不稳定
- 截图场景覆盖不全
- 文档模板与图片混排破版
- 源码分页无法满足每页行数
- 产品功能体量不足，导致源码总页数达不到 60 页以上

因此 `CodeMaster` 实现时必须把“运行、截图、分页”当成第一类核心模块，而不是配套模块。

## 12. 开发后再补的内容

等后续真正进入开发阶段，再补：

- 实际仓库结构
- 数据库迁移脚本
- 测试用例
- 开发环境部署文档
- CI/CD 设计

本轮不进入这些实现内容。
