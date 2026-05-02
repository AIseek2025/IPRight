# IPRight 技术架构设计

## 1. 技术选型

## 1.1 平台开发语言

- 后端：`Python 3.11`
- 前端：`TypeScript`
- 文档模板与脚本：`Python`

## 1.2 平台技术栈

### 前端

- `Next.js` 或 `React + Vite`
- `TypeScript`
- `Ant Design` 或 `Shadcn UI`

说明：

- 平台前端本身主要承担任务创建、状态展示、下载交付，不需要复杂 SSR 也可以落地。
- 若强调后台管理效率，可优先 `React + Vite + Ant Design`。

### 后端

- `FastAPI`
- `Pydantic`
- `SQLAlchemy`
- `PostgreSQL`
- `Redis`

### 任务编排

- MVP：`Celery + Redis`
- 进阶：`Temporal`

### AI 编排

- LLM 编排层：`LangGraph`
- 工具执行层：`Python tool runners`
- 浏览器执行层：`Playwright`

### 文档生成

- `python-docx`
- `docxtpl`
- 可选：`LibreOffice headless` 用于转 PDF

### 运行沙箱

- `Docker`
- `docker compose`
- 可选：`Firecracker / gVisor`

### 对象存储

- `MinIO`

### 可观测性

- `OpenTelemetry`
- `Prometheus + Grafana`
- `Loki`

## 2. 系统分层

建议将系统拆成六层：

1. 平台交互层
2. 任务编排层
3. AI 生产层
4. 运行验证层
5. 文档生成层
6. 交付存储层

## 3. 核心服务

## 3.1 API Gateway

### 职责

- 接收任务创建请求
- 返回任务状态
- 提供文档下载链接
- 提供后台管理接口

## 3.2 Task Orchestrator

### 职责

- 驱动全流程状态机
- 串联各个 Agent
- 负责失败重试和断点恢复

### 编排阶段

1. `plan`
2. `build`
3. `verify_run`
4. `capture`
5. `compose_manual`
6. `compose_code_book`
7. `publish`

## 3.3 Planning Service

### 输入

- 关键词
- 软件名称
- 版本号
- 行业偏好

### 输出

- `product_prd.md`
- `development_work_order.md`
- `app_scope.json`

## 3.4 Build Service

### 职责

- 调用编程大模型
- 生成标准脚手架项目
- 输出运行契约和截图契约

### 输出目录建议

```text
/tasks/{task_id}/workspace/
  prd/
  app/
    frontend/
    backend/
    manifests/
  artifacts/
  exports/
```

## 3.5 Sandbox Runtime Service

### 职责

- 构建生成软件的运行容器
- 执行依赖安装
- 启动应用
- 健康检查
- 记录运行端口与访问地址

### 输出

- `runtime_status.json`
- `service_endpoints.json`
- `health_report.json`

## 3.6 Capture Service

### 职责

- 登录应用
- 遍历页面
- 执行动作
- 截图
- 落地截图元数据

### 输出

- `screenshots/*.png`
- `screenshot_manifest.json`
- `capture_log.json`

## 3.7 Manual Composer Service

### 职责

- 读取截图清单
- 生成说明书章节
- 插图、图注、步骤说明
- 输出 Word

## 3.8 Code Book Service

### 职责

- 读取代码索引
- 合并源码
- 执行分页
- 输出 Word

## 3.9 Delivery Service

### 职责

- 把 Word 产物上传对象存储
- 回写下载链接
- 让平台前端展示可下载状态

## 4. 核心契约设计

`IPRight` 成败的关键在契约，不在 prompt 数量。

## 4.1 App Manifest

```json
{
  "product_name": "智慧园区管理平台",
  "version": "V1.0",
  "app_type": "admin_web",
  "frontend_framework": "react_vite",
  "backend_framework": "fastapi",
  "entry_routes": ["/login", "/dashboard"],
  "demo_accounts": [
    {
      "role": "admin",
      "username": "admin",
      "password": "admin123"
    }
  ]
}
```

## 4.2 Run Manifest

```json
{
  "install_commands": [
    "npm install",
    "pip install -r requirements.txt"
  ],
  "start_commands": [
    "npm run dev -- --host 0.0.0.0 --port 3000",
    "uvicorn app.main:app --host 0.0.0.0 --port 8000"
  ],
  "health_checks": [
    "http://127.0.0.1:3000/",
    "http://127.0.0.1:8000/health"
  ]
}
```

## 4.3 Capture Manifest

```json
{
  "scenarios": [
    {
      "id": "login-page",
      "route": "/login",
      "title": "登录页",
      "actions": []
    },
    {
      "id": "dashboard",
      "route": "/dashboard",
      "title": "系统首页",
      "actions": ["login_as_admin"]
    }
  ]
}
```

## 4.4 Code Index Manifest

```json
{
  "include_globs": [
    "frontend/src/**/*",
    "backend/app/**/*"
  ],
  "exclude_globs": [
    "**/node_modules/**",
    "**/dist/**",
    "**/.next/**",
    "**/*.min.js"
  ],
  "preferred_order": [
    "frontend/src/main.tsx",
    "frontend/src/App.tsx",
    "frontend/src/pages/**",
    "backend/app/main.py"
  ]
}
```

## 5. 数据模型

## 5.1 Task

- `id`
- `keyword`
- `product_name`
- `version`
- `status`
- `current_stage`
- `created_at`
- `updated_at`
- `failed_reason`

## 5.2 Task Artifact

- `id`
- `task_id`
- `artifact_type`
- `file_path`
- `storage_key`
- `build_id`
- `metadata_json`

## 5.3 Screenshot Asset

- `id`
- `task_id`
- `scenario_id`
- `page_title`
- `route`
- `image_path`
- `elements_json`
- `caption`

## 5.4 Export Record

- `id`
- `task_id`
- `export_type`
- `file_name`
- `download_url`
- `checksum`
- `version`

## 6. 文档生成的版式架构

## 6.1 说明书版式

- 页眉：软件名称 + 版本号 + 文档名称
- 页码：右上角
- 目录：自动生成
- 章节：按一级、二级标题生成
- 截图：居中 + 图注 + 说明步骤

## 6.2 源码文档版式

- 页眉：软件名称 + 版本号 + `源代码`
- 页码：右上角
- 正文：等宽字体
- 每页固定行数
- 文件切换处标注路径

## 7. 安全架构

## 7.1 沙箱隔离

- 生成应用必须与平台主服务隔离
- 限制网络访问
- 限制可执行命令
- 控制 CPU / 内存 / 磁盘配额

## 7.2 文件安全

- 导出文件只允许授权用户下载
- 下载链接带签名与过期时间
- 文档写入后生成校验值

## 7.3 Prompt 与代码安全

- 模型输出必须过静态检查
- 不允许执行危险 shell 指令
- 对生成项目做依赖风险扫描

## 8. 可观测性设计

每个阶段都必须记录：

- 开始时间
- 结束时间
- 执行耗时
- 模型名称
- 输入摘要
- 输出摘要
- 失败原因
- 关键工件路径

建议输出：

- `pipeline_trace.json`
- `stage_logs/*.json`

## 9. 为什么不建议“一上来支持任意技术栈”

因为自动运行、自动截图、自动写说明书，对运行契约一致性要求极高。  
任意技术栈会直接带来：

- 启动命令不确定
- 登录路径不确定
- 健康检查不确定
- 页面结构不确定
- 截图覆盖率不可控

因此 `IPRight` 应先将“应用生成能力”产品化为标准脚手架，再逐步扩栈。
