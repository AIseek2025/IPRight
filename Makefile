# IPRight Makefile

.PHONY: help infra-up infra-down backend-run worker-run frontend-run migrate

help:
	@echo "IPRight - 软著材料自动生成平台"
	@echo ""
	@echo "Commands:"
	@echo "  make infra-up      启动基础设施 (Postgres, Redis, MinIO)"
	@echo "  make infra-down    停止基础设施"
	@echo "  make backend-run   启动后端 API 服务"
	@echo "  make worker-run    启动 Celery Worker"
	@echo "  make frontend-run  启动前端开发服务"
	@echo "  make migrate       运行数据库迁移"
	@echo "  make test          运行测试"
	@echo "  make dev           启动全部开发服务"

infra-up:
	docker compose up -d postgres redis minio

infra-down:
	docker compose down

backend-run:
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

worker-run:
	cd backend && celery -A workers.celery_app worker --loglevel=info --concurrency=2

frontend-run:
	cd frontend && npm install && npm run dev

migrate:
	cd backend && alembic upgrade head

test:
	cd backend && python -m pytest tests/ -v

dev:
	docker compose up -d postgres redis minio
	$(MAKE) frontend-run &
	$(MAKE) backend-run &
	$(MAKE) worker-run &
	@echo "All services started"
	@echo "  Frontend: http://localhost:3000"
	@echo "  Backend:  http://localhost:8000"
	@echo "  API Docs: http://localhost:8000/docs"
