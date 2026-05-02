# 智慧园区管理平台 V1.0

## 快速运行

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
