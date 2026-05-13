# Demo App Seed

`examples/demo_app/` 是 `IPRight` 当前生成链路使用的种子模板，不是独立维护的业务示例项目。

## 目录职责

- `frontend/` 提供静态前端骨架与基础依赖声明
- `backend/` 提供静态后端骨架与运行入口
- `manifests/` 提供运行、截图、源码导出所需的基线 manifest
- Worker 在 `build` 阶段复制该目录后，再由动态代码生成逻辑写入任务专属页面、配置与业务文件

## 使用边界

- 这里的内容应视为“可复制的种子基线”，而不是最终交付应用
- 若要调整生成应用默认骨架，应优先修改这里，而不是新增平行模板源
- 任务专属标题、模块、页面内容以后续 `build` 阶段生成结果为准

## 本地调试

### 前端
```bash
cd frontend
npm install
npm run dev
```
访问 http://localhost:3000

### 后端
```bash
cd backend
pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
访问 http://localhost:8000/health

### Demo 账号
- 用户名: admin
- 密码: admin123
