# IPRight Prompt 与 Agent 契约设计

## 1. 设计目标

本文件定义 `IPRight` 中 LLM 与 Agent 的职责边界、输入输出格式和协作契约。  
目标不是堆更多 prompt，而是保证各阶段输出可被后续阶段稳定消费。

## 2. 角色划分

建议将整条链拆成以下角色：

1. `Product Planner`
2. `Development Planner`
3. `App Builder`
4. `Runtime Verifier`
5. `Capture Agent`
6. `Manual Writer`
7. `Code Book Composer`
8. `Publish Agent`

## 3. Product Planner 契约

## 3.1 职责

- 根据关键词生成产品定义
- 收敛软件名称、版本号、页面结构、功能边界

## 3.2 输入

```json
{
  "keyword": "智慧园区管理平台",
  "product_name": "智慧园区管理平台",
  "version": "V1.0",
  "industry": "园区"
}
```

## 3.3 输出

- `product_prd.md`
- `product_summary.json`

## 3.4 输出约束

`product_summary.json` 建议至少包含：

```json
{
  "app_type": "admin_web",
  "user_roles": ["admin"],
  "core_modules": ["首页", "用户管理", "设备管理", "报表统计", "系统设置"],
  "required_pages": ["/login", "/dashboard", "/users", "/devices", "/settings"]
}
```

## 4. Development Planner 契约

## 4.1 职责

- 将 PRD 转成可编码任务书
- 给出技术栈与 Manifest 要求

## 4.2 输出

- `development_work_order.md`
- `route_plan.json`
- `data_model.json`
- `delivery_contract.json`

## 4.3 关键约束

- 必须明确页面清单
- 必须明确演示账号
- 必须明确运行方式
- 必须明确截图场景

## 5. App Builder 契约

## 5.1 职责

- 按任务书生成实际应用
- 产出标准目录与标准 Manifest

## 5.2 输入

- `product_prd.md`
- `development_work_order.md`
- `delivery_contract.json`

## 5.3 输出

- 应用代码目录
- `app_manifest.json`
- `run_manifest.json`
- `capture_manifest.json`
- `code_index_manifest.json`

## 5.4 Prompt 关键要求

要在 prompt 中明确：

- 只生成后台管理型 Web 应用
- 必须提供 demo 账号
- 必须有健康检查接口
- 必须有固定路由
- 必须提供截图场景清单
- 必须提供源码索引

## 6. Runtime Verifier 契约

## 6.1 职责

- 按 `run_manifest` 安装依赖并启动
- 执行健康检查
- 记录运行结果

## 6.2 输入

- 应用目录
- `run_manifest.json`

## 6.3 输出

- `runtime_status.json`
- `health_report.json`
- `launch_log.txt`

## 6.4 通过标准

- 前端入口可访问
- 后端健康检查通过
- 登录页存在

## 7. Capture Agent 契约

## 7.1 职责

- 根据 `capture_manifest` 自动遍历场景
- 登录、点击、等待页面稳定
- 完成截图并输出页面元数据

## 7.2 输入

- 应用访问地址
- demo 账号
- `capture_manifest.json`

## 7.3 输出

- 截图图片
- `screenshot_manifest.json`

## 7.4 标准动作抽象

建议将 Playwright 动作抽象成统一 DSL：

```json
{
  "action": "click_menu",
  "target": "用户管理"
}
```

或：

```json
{
  "action": "fill_input",
  "target": "用户名",
  "value": "admin"
}
```

## 8. Manual Writer 契约

## 8.1 职责

- 基于真实截图和页面元数据生成说明书内容

## 8.2 输入

- `product_prd.md`
- `screenshot_manifest.json`
- 截图图片路径

## 8.3 输出

- `manual_outline.json`
- `manual_sections.json`
- `software_manual.docx`

## 8.4 Prompt 关键要求

- 必须引用真实页面标题
- 必须引用真实按钮、字段、菜单文字
- 不得虚构页面
- 每张图都要有图注和操作说明

## 9. Code Book Composer 契约

## 9.1 职责

- 按源码索引整理源码
- 分页并组装 Word

## 9.2 输入

- 应用目录
- `code_index_manifest.json`

## 9.3 输出

- `normalized_code_stream.txt`
- `source_code_render.json`
- `source_code_book.docx`

## 10. Publish Agent 契约

## 10.1 职责

- 上传导出文档
- 创建下载记录
- 回写任务完成状态

## 10.2 输出

- `exports` 记录
- 下载 URL

## 11. Prompt 输出格式要求

所有 LLM 阶段都必须输出：

- 一个主文档
- 一个结构化 JSON 摘要

不要只输出 Markdown 文本。

## 12. 示例 Prompt 片段

## 12.1 Product Planner Prompt 片段

```text
你要把用户给出的产品关键词收敛成一个适合软著材料自动化生产的平台需求定义。
限制该产品为后台管理型 Web 应用。
必须输出：
1. 产品 PRD Markdown
2. product_summary.json
其中必须包含页面清单、核心模块、目标用户、版本号建议。
```

## 12.2 App Builder Prompt 片段

```text
你要生成一个可被 IPRight 自动运行、自动截图、自动生成说明书的标准应用。
必须输出 app_manifest、run_manifest、capture_manifest、code_index_manifest。
如果你做不到这些契约，视为任务失败。
```

## 12.3 Manual Writer Prompt 片段

```text
你将基于真实截图元数据为软件说明书生成页面说明。
不得虚构页面，不得输出截图中不存在的按钮或字段。
每张截图都要输出：
- 图注
- 页面用途说明
- 操作步骤
```

## 13. Agent 与 LLM 的边界

### 适合交给 LLM 的

- PRD 编写
- 开发任务书
- 图注与说明文字
- 说明书章节编排

### 适合交给 Agent / 工具的

- 启动应用
- 健康检查
- 页面点击
- 截图
- 源码扫描
- Word 文件写入

## 14. 失败判断

若某一角色输出缺少结构化 JSON，则视为不符合契约。

若某一角色只给自然语言但后续阶段无法消费，也视为失败。

## 15. 给 CodeMaster 的建议

后续无人值守开发时，不要把所有阶段都混在一个大 prompt 内。  
应先实现：

1. 角色分层
2. 输出结构化
3. 阶段化保存工件
4. 阶段化重试

这样 `IPRight` 才能稳定运行，而不是“一次性大模型长链调用碰运气”。
