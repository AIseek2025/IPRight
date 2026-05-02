# IPRight 生成应用契约

## 1. 为什么必须有契约

`IPRight` 的后半段能力依赖“自动运行 + 自动截图 + 自动写说明书 + 自动导出源码”。  
如果生成应用没有统一约束，平台后半段会失稳。

因此所有由 `IPRight` 生成的软件，都必须满足本契约。

## 2. 契约目标

让每个生成应用都具备以下能力：

- 可安装
- 可启动
- 可健康检查
- 可登录
- 可截图
- 可导出源码索引
- 可生成完整说明书设计元数据
- 可支撑 60 页以上真实源码文档

## 3. 必备目录结构

```text
app/
  frontend/
  backend/
  manifests/
    app_manifest.json
    run_manifest.json
    capture_manifest.json
    code_index_manifest.json
  README_RUN.md
```

## 4. app_manifest.json

### 作用

定义产品基础信息和运行上下文。

### 必填字段

- `product_name`
- `version`
- `app_type`
- `frontend_framework`
- `backend_framework`
- `entry_routes`
- `demo_accounts`
- `domain_background`
- `development_purpose`
- `applicable_domain`
- `target_users`
- `core_features`
- `technical_highlights`

## 5. run_manifest.json

### 作用

告诉平台如何安装、如何启动、如何检测服务就绪。

### 必填字段

- `install_commands`
- `start_commands`
- `working_directories`
- `ports`
- `health_checks`

### 要求

- 所有命令必须可在 Linux 容器中执行
- 不允许依赖交互式输入
- 不允许使用随机端口

## 6. capture_manifest.json

### 作用

告诉平台哪些页面要截图、截图前需要做什么动作。

### 每个场景必须包含

- `id`
- `title`
- `route`
- `requires_auth`
- `actions`
- `capture_type`
- `priority`

### actions 支持的标准动作

- `login_as_admin`
- `click_menu:{name}`
- `click_button:{name}`
- `fill_input:{name}:{value}`
- `wait_for_text:{text}`

### 约束

- 不允许只给模糊页面名而不给 route
- 不允许截图场景没有标题
- 关键业务页面不能少于登录页、首页、列表页、详情/表单页、设置页这几类

## 6.1 文档设计元数据

### 作用

告诉平台如何生成“引言”“系统设计”“软件使用说明”以及图示。

### 建议工件

- `manual_outline.json`
- `diagram_spec.json`

### manual_outline.json 至少应包含

- `introduction.background`
- `introduction.purpose`
- `introduction.applicable_domain`
- `system_design.tech_stack`
- `system_design.runtime_environment`
- `system_design.core_modules`
- `usage_guides`

### diagram_spec.json 至少应包含

- `architecture.nodes`
- `architecture.edges`

### 约束

- 系统架构图必须可由结构化元数据生成
- 不允许只在说明书中写“见系统架构图”但没有真实图示

## 7. code_index_manifest.json

### 作用

告诉平台哪些源码文件可用于软著文档。

### 必填字段

- `include_globs`
- `exclude_globs`
- `preferred_order`
- `line_density_target`

### 约束

- 必须排除第三方依赖与构建产物
- 必须优先保留业务核心文件
- 必须优先覆盖前端页面、后端接口、服务层、数据模型、任务编排等高价值代码
- 必须支持平台评估总代码页数是否大于 60 页

## 8. 应用运行要求

### 前端

- 首页可访问
- 若需要登录，必须提供 demo 账号
- 禁止首屏无限 loading

### 后端

- 必须有健康检查接口
- 建议返回 `status/version`

### 数据

- 必须提供基础演示数据
- 不允许截图时页面为空白
- 页面与数据量应足以支撑详细使用说明和真实截图编排

## 9. 页面设计要求

为了适配说明书生成，生成应用的页面需尽量包含：

- 清晰页面标题
- 主要按钮文字
- 表单字段标签
- 列表表头
- 操作成功反馈
- 面包屑 / 导航提示 / 页面摘要等说明性信息

否则截图后很难生成高质量操作说明。

## 10. 截图友好要求

- 页面首屏应避免过长空白
- 关键区域在 1440x900 视窗内可见
- 弹窗和抽屉允许通过标准动作打开
- 页面不应依赖复杂手势
- 页面布局应支持截图后插入“截图 + 图注 + 操作步骤 + 说明文字”排版

## 10.1 代码体量要求

- 生成应用必须以“总代码页数大于 60 页”为目标进行功能设计
- 至少应具备足够多的真实页面、接口、服务层和数据模型，不能只交付极简骨架
- 若总代码页数不足 60，默认视为产品功能体量不足，不能判定为软著交付完成

## 11. 失败标准

任一项不满足，即视为不符合 `IPRight App Contract`：

- 无法启动
- 无健康检查
- 无 demo 账号
- 无 capture manifest
- 无 code index manifest
- 无引言 / 系统设计 / 使用说明所需元数据
- 无图示元数据，无法生成系统架构图
- 页面路由不可达

## 12. 结论

`IPRight` 不是让代码模型自由生成一个“看起来像软件”的产物，而是让它生成一个“可被平台后处理”的软件。  
本契约就是后处理稳定性的前提。
