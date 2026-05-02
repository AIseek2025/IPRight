# IPRight 快速启动指南

## 环境要求

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL 16 (或使用 Docker)

## 快速启动

### 1. 启动基础设施

```bash
make infra-up
```

或手动启动：

```bash
docker compose up -d postgres redis minio
```

### 2. 初始化数据库

```bash
cd backend
cp .env.example .env
alembic upgrade head
```

### 3. 启动后端 API

```bash
make backend-run
# 或直接:
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000/docs 查看 API 文档。

### 4. 启动 Celery Worker

```bash
make worker-run
# 或直接:
cd backend && celery -A workers.celery_app worker --loglevel=info --concurrency=2
```

### 5. 启动前端

```bash
make frontend-run
# 或直接:
cd frontend && npm install && npm run dev
```

访问 http://localhost:3000 查看平台界面。

### 6. 一键启动全部服务

```bash
make dev
```

## 项目结构

```
IPRight/
  frontend/          React + Vite + TypeScript 前端
  backend/           FastAPI 后端
    app/api/         API 路由
    app/models/      数据模型
    app/schemas/     Pydantic 模型
    app/services/    核心业务服务
    app/core/        配置与状态机
    alembic/         数据库迁移
    tests/           后端测试
  workers/           Celery Worker 与任务编排
    orchestrator/    任务编排器
    stages/          阶段处理器
  templates/         Word 文档模板
  docs/              产品设计文档
  docker-compose.yml Docker 服务编排
  Makefile           常用命令
```

## 主要 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/tasks | 创建任务 |
| GET | /api/v1/tasks | 任务列表 |
| GET | /api/v1/tasks/{id} | 任务详情 |
| GET | /api/v1/tasks/{id}/dashboard | 任务聚合面板 |
| GET | /api/v1/tasks/{id}/timeline | 任务时间线 |
| GET | /api/v1/tasks/{id}/artifacts | 任务工件列表 |
| GET | /api/v1/tasks/{id}/exports | 可下载文件 |
| GET | /api/v1/exports/{id}/download | 下载导出文件 |
| POST | /api/v1/tasks/{id}/retry | 重试任务 |
| POST | /api/v1/tasks/{id}/cancel | 取消任务 |
| GET | /health | 后端健康检查 |

## 运行测试

```bash
cd backend && python -m pytest tests/ -v
```
