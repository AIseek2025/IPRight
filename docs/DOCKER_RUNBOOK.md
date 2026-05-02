# IPRight Docker 全链路运行手册

## 前提

- Docker Desktop 或 Docker Engine 已安装
- `docker compose` 命令可用
- 端口 5432, 6379, 8000, 3000 未占用
- 若 8000 已被其他进程占用，可改用 `8010` 作为本机 Docker 验证端口

## 一键启动全链路

```bash
# 1. 启动基础设施 (PostgreSQL + Redis + MinIO)
docker compose up -d postgres redis minio

# 2. 等待服务就绪
sleep 5

# 3. 数据库迁移
cd backend
python3 -m pip install alembic asyncpg
python3 - <<'PY'
from alembic.config import main
main(argv=["upgrade", "head"])
PY
cd ..

# 4. 启动后端 API (PostgreSQL 模式)
cd backend && \
IPRIGHT_DB_TYPE=postgresql \
IPRIGHT_DATABASE_URL=postgresql+asyncpg://ipright:ipright@127.0.0.1:5432/ipright \
IPRIGHT_DATABASE_SYNC_URL=postgresql://ipright:ipright@127.0.0.1:5432/ipright \
IPRIGHT_REDIS_URL=redis://127.0.0.1:6379/0 \
IPRIGHT_CELERY_BROKER_URL=redis://127.0.0.1:6379/1 \
IPRIGHT_CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2 \
uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload &

# 5. 启动前端
cd frontend && npm run dev -- --host 0.0.0.0 --port 3000 &

# 6. 验证
curl http://127.0.0.1:8010/health
curl http://localhost:3000/
```

## 纯 Docker Compose 启动

```bash
# 启动全部服务 (backend + frontend + worker + postgres + redis + minio)
docker compose up -d

# 查看日志
docker compose logs -f backend

# 停止
docker compose down
```

## API 验证

```bash
# 创建任务
curl -X POST http://127.0.0.1:8010/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"keyword":"智慧园区管理平台"}'

# 查看任务 (替换 TASK_ID)
curl http://127.0.0.1:8010/api/v1/tasks/TASK_ID

# 查看 Swagger 文档
open http://127.0.0.1:8010/docs
```

## 全链路 E2E 验证

```bash
# 确保 demo app 后端在 8001 端口
cd examples/demo_app
pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8001 &

# 确保 demo app 前端在 3001 端口
cd frontend
npm install && npx vite --host 0.0.0.0 --port 3001 &

# 运行完整 E2E 验证
cd ../..
python3 scripts/demo_runner.py

# 输出物位置
ls tmp/demo_output/exports/*.docx
ls tmp/demo_output/screenshots/*.png
```

## 环境变量

```bash
./scripts/docker_verify.sh

# 如 8000 或默认端口被占用，可显式指定验证端口
IPRIGHT_DOCKER_VERIFY_PORT=8010 ./scripts/docker_verify.sh
```

## 环境变量

```bash
# 复制并编辑环境变量
cp backend/.env.example backend/.env

# 关键变量
IPRIGHT_DATABASE_URL=postgresql+asyncpg://ipright:ipright@localhost:5432/ipright
IPRIGHT_DB_TYPE=postgresql
DEEPSEEK_API_KEY=sk-xxxxx  # 启用 DeepSeek LLM
```
