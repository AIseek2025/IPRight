#!/bin/bash
# IPRight 一键启动脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== IPRight 启动脚本 ==="
echo "项目根目录: $PROJECT_ROOT"

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "[错误] 未检测到 Docker，请先安装 Docker。"
    exit 1
fi

# 1. 启动基础设施
echo ""
echo "[1/5] 启动基础设施 (Postgres, Redis, MinIO)..."
cd "$PROJECT_ROOT"
docker compose up -d postgres redis minio 2>/dev/null || true
sleep 3
echo "[1/5] 基础设施已启动"

# 2. 安装前端依赖
echo ""
echo "[2/5] 安装前端依赖..."
cd "$PROJECT_ROOT/frontend"
npm install 2>/dev/null || true
echo "[2/5] 前端依赖安装完成"

# 3. 安装后端依赖
echo ""
echo "[3/5] 安装后端依赖..."
cd "$PROJECT_ROOT/backend"
pip install -e ".[dev]" 2>/dev/null || pip install fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg alembic pydantic pydantic-settings python-dotenv celery[redis] redis python-docx httpx minio python-multipart 2>/dev/null || true
echo "[3/5] 后端依赖安装完成"

# 4. 运行数据库迁移
echo ""
echo "[4/5] 运行数据库迁移..."
cd "$PROJECT_ROOT/backend"
alembic upgrade head 2>/dev/null || echo "[警告] 数据库迁移可能尚未执行，请先启动 postgres 并配置 .env"
echo "[4/5] 迁移完成"

# 5. 启动服务
echo ""
echo "[5/5] 启动服务..."

# 启动后端
cd "$PROJECT_ROOT/backend"
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "  后端已启动 (PID: $BACKEND_PID) -> http://localhost:8000"

# 启动 Worker
celery -A workers.celery_app worker --loglevel=info --concurrency=2 &
WORKER_PID=$!
echo "  Worker 已启动 (PID: $WORKER_PID)"

# 启动前端
cd "$PROJECT_ROOT/frontend"
npm run dev -- --host 0.0.0.0 --port 3000 &
FRONTEND_PID=$!
echo "  前端已启动 (PID: $FRONTEND_PID) -> http://localhost:3000"

echo ""
echo "=== IPRight 启动完成 ==="
echo "  前端:     http://localhost:3000"
echo "  后端 API: http://localhost:8000"
echo "  API 文档: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止所有服务"

trap "kill $BACKEND_PID $WORKER_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
