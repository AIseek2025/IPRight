# IPRight API 与数据模型设计

## 1. 设计目标

本文件用于定义 `IPRight` 的：

- 后端 API 契约
- 核心数据库表结构
- 任务工件关系
- 下载与导出对象模型

目标是让后续 `CodeMaster` 可以直接依据本文件进入无人值守开发。<mccoremem id="01KQFYYKYCTWYQA533H3R1QC7A" />

## 2. API 设计原则

- API 分为用户面、任务面、运维面三类
- 所有长任务接口都采用“提交后异步执行”
- 所有导出物都不直接走本地路径，统一通过导出记录与下载 URL 暴露
- 所有关键实体都必须带 `task_id` 或 `build_id`

## 3. 核心实体

### 3.1 Task

代表一个由关键词触发的完整软著材料生产任务。

### 3.2 Build

代表某个任务的一次构建执行，用于支持失败重跑和多次版本生成。

### 3.3 Artifact

代表任务生命周期中的中间工件和最终导出物，如：

- PRD
- 开发任务书
- 截图清单
- 截图文件
- 说明书 Word
- 源码 Word

### 3.4 Export

代表对用户可见的下载产物记录。

## 4. API 分组

## 4.1 用户面 API

### `POST /api/v1/tasks`

创建任务。

#### 请求体

```json
{
  "keyword": "智慧园区管理平台",
  "product_name": "智慧园区管理平台",
  "version": "V1.0",
  "industry": "园区",
  "notes": "优先生成后台管理型产品"
}
```

#### 响应体

```json
{
  "task_id": "task_001",
  "status": "queued"
}
```

### `GET /api/v1/tasks`

分页查询任务列表。

#### 查询参数

- `page`
- `page_size`
- `status`
- `keyword`

### `GET /api/v1/tasks/{task_id}`

获取任务详情。

#### 响应字段建议

- 任务基础信息
- 当前阶段
- 最近失败原因
- 当前活跃 build
- 导出状态

### `GET /api/v1/tasks/{task_id}/timeline`

获取任务时间线。

### `GET /api/v1/tasks/{task_id}/artifacts`

获取工件列表。

### `GET /api/v1/tasks/{task_id}/exports`

获取可下载导出文件列表。

### `POST /api/v1/tasks/{task_id}/retry`

重试任务，可指定从某个阶段开始。

#### 请求体

```json
{
  "from_stage": "capturing"
}
```

### `POST /api/v1/tasks/{task_id}/cancel`

取消任务。

## 4.2 运维面 API

### `GET /api/v1/admin/tasks`

查看更完整的任务列表，包含失败原因和资源占用。

### `GET /api/v1/admin/builds/{build_id}`

查看某次构建详情。

### `GET /api/v1/admin/builds/{build_id}/logs`

查看构建日志。

### `POST /api/v1/admin/builds/{build_id}/rerun-stage`

指定阶段重跑。

### `GET /api/v1/admin/system/queues`

查看任务队列与并发情况。

### `GET /api/v1/admin/system/workers`

查看 worker 健康状态。

## 4.3 下载 API

### `GET /api/v1/exports/{export_id}/download`

返回签名下载链接或流式下载。

### `GET /api/v1/exports/{export_id}`

获取单个导出记录信息。

## 5. 数据库表设计

以下以 PostgreSQL 为默认设计。

## 5.1 `tasks`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | uuid | 主键 |
| `keyword` | text | 用户输入关键词 |
| `product_name` | text | 软件名称 |
| `version` | varchar(32) | 版本号 |
| `industry` | varchar(64) | 行业分类 |
| `notes` | text | 用户补充说明 |
| `status` | varchar(32) | 任务状态 |
| `current_stage` | varchar(32) | 当前阶段 |
| `active_build_id` | uuid | 当前活跃构建 |
| `created_by` | uuid/null | 创建用户 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

## 5.2 `task_builds`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | uuid | 主键 |
| `task_id` | uuid | 所属任务 |
| `build_no` | int | 第几次构建 |
| `status` | varchar(32) | 构建状态 |
| `current_stage` | varchar(32) | 当前阶段 |
| `trigger_type` | varchar(32) | 创建 / 重试 / 局部重跑 |
| `runtime_workspace` | text | 构建工作目录 |
| `failure_reason` | text | 失败原因 |
| `started_at` | timestamptz | 开始时间 |
| `finished_at` | timestamptz/null | 完成时间 |
| `created_at` | timestamptz | 创建时间 |

## 5.3 `build_stage_runs`

记录每个阶段的执行情况。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | uuid | 主键 |
| `build_id` | uuid | 所属构建 |
| `stage_name` | varchar(32) | 阶段名 |
| `status` | varchar(32) | queued/running/succeeded/failed |
| `attempt_no` | int | 第几次尝试 |
| `started_at` | timestamptz | 开始时间 |
| `finished_at` | timestamptz/null | 完成时间 |
| `failure_reason` | text | 失败摘要 |
| `metrics_json` | jsonb | 阶段指标 |

## 5.4 `artifacts`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | uuid | 主键 |
| `task_id` | uuid | 所属任务 |
| `build_id` | uuid | 所属构建 |
| `artifact_type` | varchar(64) | 工件类型 |
| `artifact_name` | varchar(255) | 工件名称 |
| `storage_key` | text | 对象存储路径 |
| `local_path` | text | 本地路径，可选 |
| `mime_type` | varchar(128) | 文件类型 |
| `checksum` | varchar(128) | 校验值 |
| `metadata_json` | jsonb | 元数据 |
| `created_at` | timestamptz | 创建时间 |

### 典型 `artifact_type`

- `product_prd`
- `development_work_order`
- `app_manifest`
- `run_manifest`
- `capture_manifest`
- `code_index_manifest`
- `runtime_status`
- `health_report`
- `screenshot_manifest`
- `screenshot_image`
- `software_manual_docx`
- `source_code_book_docx`

## 5.5 `screenshots`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | uuid | 主键 |
| `task_id` | uuid | 所属任务 |
| `build_id` | uuid | 所属构建 |
| `scenario_id` | varchar(128) | 场景 ID |
| `page_title` | varchar(255) | 页面标题 |
| `route` | text | 页面路由 |
| `image_artifact_id` | uuid | 对应图片工件 |
| `caption` | text | 图注 |
| `steps_markdown` | text | 操作步骤 |
| `metadata_json` | jsonb | 其它页面元数据 |
| `created_at` | timestamptz | 创建时间 |

## 5.6 `exports`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | uuid | 主键 |
| `task_id` | uuid | 所属任务 |
| `build_id` | uuid | 所属构建 |
| `export_type` | varchar(64) | `manual_docx` / `source_code_docx` |
| `artifact_id` | uuid | 对应工件 |
| `file_name` | varchar(255) | 下载文件名 |
| `download_url` | text | 下载地址 |
| `status` | varchar(32) | preparing/ready/expired |
| `created_at` | timestamptz | 创建时间 |
| `expires_at` | timestamptz/null | 过期时间 |

## 5.7 `task_events`

记录任务事件流，便于时间线展示。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | uuid | 主键 |
| `task_id` | uuid | 所属任务 |
| `build_id` | uuid/null | 所属构建 |
| `event_type` | varchar(64) | 事件类型 |
| `title` | varchar(255) | 事件标题 |
| `detail` | text | 事件描述 |
| `payload_json` | jsonb | 结构化数据 |
| `created_at` | timestamptz | 事件时间 |

## 6. 对象存储目录建议

```text
ipright/
  tasks/{task_id}/
    builds/{build_id}/
      prd/
      manifests/
      runtime/
      screenshots/
      exports/
```

### 示例

```text
ipright/tasks/task_001/builds/build_003/exports/software_manual.docx
```

## 7. API 响应结构统一规范

建议统一采用：

```json
{
  "code": "OK",
  "message": "success",
  "data": {}
}
```

失败时：

```json
{
  "code": "TASK_NOT_FOUND",
  "message": "task does not exist",
  "data": null
}
```

## 8. 前端所需聚合接口建议

为了简化前端开发，建议提供聚合详情接口：

### `GET /api/v1/tasks/{task_id}/dashboard`

返回：

- 任务基础信息
- 状态时间线
- 最近 PRD 摘要
- 最近截图预览
- 导出文件状态
- 当前失败原因

## 9. 数据约束建议

- 一个 `task` 可有多个 `build`
- 一个 `build` 可有多个 `artifact`
- 两份最终导出必须绑定同一个 `build`
- 说明书导出与源码导出必须都来自同一代码版本

## 10. 开发建议

后续 `CodeMaster` 开发时，优先顺序建议为：

1. `tasks`
2. `task_builds`
3. `build_stage_runs`
4. `artifacts`
5. `exports`
6. `task_events`

先把任务系统和工件系统打牢，再接入 AI、截图和 Word 生成链。
