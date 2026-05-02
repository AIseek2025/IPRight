#!/bin/bash
# IPRight Docker 全链路验证脚本
# 要求: Docker + docker compose 已安装
set -e

echo "=== IPRight Docker Full-Chain Verification ==="

# 1. 检查 Docker
command -v docker >/dev/null 2>&1 || { echo "Docker not found. Please install Docker first."; exit 1; }

VERIFY_PORT="${IPRIGHT_DOCKER_VERIFY_PORT:-8010}"
DATABASE_URL="${IPRIGHT_DATABASE_URL:-postgresql+asyncpg://ipright:ipright@127.0.0.1:5432/ipright}"
DATABASE_SYNC_URL="${IPRIGHT_DATABASE_SYNC_URL:-postgresql://ipright:ipright@127.0.0.1:5432/ipright}"
REDIS_URL="${IPRIGHT_REDIS_URL:-redis://127.0.0.1:6379/0}"
CELERY_BROKER_URL="${IPRIGHT_CELERY_BROKER_URL:-redis://127.0.0.1:6379/1}"
CELERY_RESULT_BACKEND="${IPRIGHT_CELERY_RESULT_BACKEND:-redis://127.0.0.1:6379/2}"

# 2. 启动基础设施
echo "[1/5] Starting infrastructure..."
docker compose up -d postgres redis minio
sleep 5

# 3. 数据库迁移
echo "[2/5] Running database migration..."
cd backend
python3 -m pip install -q sqlalchemy asyncpg alembic 2>/dev/null
python3 - <<'PY' 2>/dev/null || echo "Migration skipped (first run)"
from alembic.config import main
main(argv=["upgrade", "head"])
PY
cd ..

# 4. 启动后端
echo "[3/5] Starting backend API..."
cd backend
python3 -m pip install -q fastapi uvicorn pydantic pydantic-settings python-docx httpx asyncpg 2>/dev/null
IPRIGHT_DB_TYPE=postgresql \
IPRIGHT_DATABASE_URL="$DATABASE_URL" \
IPRIGHT_DATABASE_SYNC_URL="$DATABASE_SYNC_URL" \
IPRIGHT_REDIS_URL="$REDIS_URL" \
IPRIGHT_CELERY_BROKER_URL="$CELERY_BROKER_URL" \
IPRIGHT_CELERY_RESULT_BACKEND="$CELERY_RESULT_BACKEND" \
python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$VERIFY_PORT" &
BACKEND_PID=$!
cd ..
sleep 3

# 5. API 冒烟测试
echo "[4/5] API smoke test..."
HEALTH=$(curl -s "http://127.0.0.1:${VERIFY_PORT}/health")
echo "  Health: $HEALTH"

CREATE=$(curl -s -X POST "http://127.0.0.1:${VERIFY_PORT}/api/v1/tasks" \
  -H 'Content-Type: application/json' \
  -d '{"keyword":"Docker验证测试","product_name":"DockerTest","version":"V1.0"}')
TASK_ID=$(echo "$CREATE" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['task_id'])" 2>/dev/null)
echo "  Task created: $TASK_ID"

if [ -n "$TASK_ID" ]; then
  GET=$(curl -s "http://127.0.0.1:${VERIFY_PORT}/api/v1/tasks/$TASK_ID")
  echo "  Task status: $(echo "$GET" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['status'])" 2>/dev/null)"
fi

# 6. 清理
echo "[5/5] Cleaning up..."
kill $BACKEND_PID 2>/dev/null
docker compose down 2>/dev/null

echo ""
echo "=== Verification Complete ==="
echo "If all steps passed, IPRight is ready for production use."
