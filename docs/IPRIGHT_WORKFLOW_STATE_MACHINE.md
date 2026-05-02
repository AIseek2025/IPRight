# IPRight 工作流状态机设计

## 1. 设计目标

本文件定义 `IPRight` 从任务创建到最终导出的完整状态机，用于：

- 指导后续 `CodeMaster` 实现任务编排
- 明确阶段边界
- 明确可重试点
- 明确失败收口方式

## 2. 顶层状态

建议顶层任务状态如下：

1. `queued`
2. `planning`
3. `coding`
4. `building`
5. `running`
6. `capturing`
7. `writing_manual`
8. `writing_code_book`
9. `publishing`
10. `completed`
11. `failed`
12. `cancelled`
13. `needs_review`

## 3. 状态定义

## 3.1 `queued`

任务已创建，等待编排器消费。

### 进入条件

- 用户提交任务成功

### 退出条件

- 编排器开始规划

## 3.2 `planning`

生成 PRD、开发任务书和产品范围定义。

### 成功产出

- `product_prd.md`
- `development_work_order.md`
- `route_plan.json`

### 失败条件

- 规划结果缺少核心字段
- PRD 不满足后台管理型产品约束

## 3.3 `coding`

调用编程模型生成应用代码与 Manifest。

### 成功产出

- 生成应用目录
- 4 个 Manifest

### 失败条件

- 缺少运行契约
- 缺少截图契约
- 缺少源码索引契约

## 3.4 `building`

安装依赖、构建项目、做静态检查。

### 成功产出

- 构建日志
- 静态检查结果

### 失败条件

- 依赖安装失败
- 构建失败
- 静态检查失败

## 3.5 `running`

启动应用并完成健康检查。

### 成功产出

- `runtime_status.json`
- `health_report.json`

### 失败条件

- 端口未启动
- 健康检查失败
- 登录入口不可达

## 3.6 `capturing`

登录并按场景进行自动截图。

### 成功产出

- `screenshots/*.png`
- `screenshot_manifest.json`

### 失败条件

- 关键页面不可达
- 截图覆盖不足

## 3.7 `writing_manual`

根据截图清单生成说明书 Word。

### 成功产出

- `software_manual.docx`

### 失败条件

- 图文编排失败
- 内容校验失败

## 3.8 `writing_code_book`

根据源码索引生成源码 Word。

### 成功产出

- `source_code_book.docx`

### 失败条件

- 源码流构造失败
- 分页失败

## 3.9 `publishing`

上传对象存储并回写下载记录。

### 成功产出

- `exports` 记录
- 下载 URL

### 失败条件

- 上传失败
- 导出记录写入失败

## 3.10 `completed`

任务已完成，用户可下载两份 Word。

## 3.11 `failed`

任务失败，且当前无法自动恢复。

## 3.12 `needs_review`

任务部分完成，但存在需要人工确认的异常。

适用场景：

- 软件已生成，但截图覆盖不完整
- 两份 Word 只成功一份
- 说明书质量低但结构完整

## 4. 阶段转移图

```text
queued
 -> planning
 -> coding
 -> building
 -> running
 -> capturing
 -> writing_manual
 -> writing_code_book
 -> publishing
 -> completed
```

任何阶段失败后：

- 可重试：回退到该阶段
- 不可自动恢复：进入 `failed`
- 产物存在但需人工判断：进入 `needs_review`

## 5. 子状态与阶段结果

每个阶段建议维护子状态：

- `queued`
- `running`
- `succeeded`
- `failed`
- `skipped`
- `cancelled`

## 6. 重试设计

## 6.1 可独立重试的阶段

- `planning`
- `coding`
- `building`
- `running`
- `capturing`
- `writing_manual`
- `writing_code_book`
- `publishing`

## 6.2 重试策略

### 规划阶段

- 最多自动重试 1 次

### 开发与构建阶段

- 最多自动重试 1 次
- 第二次失败后进入 `needs_review`

### 截图与文档阶段

- 支持多次重跑
- 不应重新触发整个开发阶段

## 6.3 重试原则

- 文档问题，不回退到代码生成
- 截图问题，不回退到 PRD 阶段
- 发布问题，不重做说明书和源码文档

## 7. Cancel 语义

当用户触发取消：

- 若任务在 `queued/planning/coding/building`，可立即取消
- 若任务在 `running/capturing`，需要先停掉运行环境再取消
- 若任务在 `writing_manual/writing_code_book`，允许本阶段结束后停止后续阶段

## 8. 失败分类建议

建议统一失败类别：

- `planning_contract_error`
- `coding_contract_error`
- `dependency_install_failed`
- `build_failed`
- `runtime_boot_failed`
- `health_check_failed`
- `login_failed`
- `capture_failed`
- `manual_render_failed`
- `code_book_render_failed`
- `publish_failed`

## 9. 阶段完成判定

## 9.1 说明书完成判定

至少满足：

- Word 文件存在
- 文件大小非零
- 截图数大于等于最小覆盖阈值
- 文档章节完整

## 9.2 源码文档完成判定

至少满足：

- Word 文件存在
- 文件大小非零
- 源码索引存在
- 分页结果合法

## 9.3 任务整体完成判定

必须同时满足：

- 说明书 Word 已生成
- 源码 Word 已生成
- 下载记录已写入

## 10. 事件流建议

建议在每次状态变化时发出事件：

- `task_created`
- `planning_started`
- `planning_succeeded`
- `coding_failed`
- `runtime_ready`
- `capture_completed`
- `manual_export_ready`
- `task_completed`

这些事件可用于：

- 前端时间线
- 通知
- 审计记录

## 11. 前端显示建议

### 用户态

- 只展示简化状态
- 显示当前阶段和百分比

### 管理态

- 展示完整阶段状态
- 展示失败类别
- 展示重试入口

## 12. 给 CodeMaster 的实现建议

实现顺序建议：

1. 先做阶段枚举和状态迁移表
2. 再做阶段执行器接口
3. 再做重试策略
4. 最后接前端状态展示

避免一开始把任务编排写成大而散的单函数。
