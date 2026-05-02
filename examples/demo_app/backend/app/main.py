"""Main backend application with full CRUD API routes."""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from datetime import datetime

app = FastAPI(title="智慧园区管理平台 API")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "V1.0", "service": "智慧园区管理平台"}


@app.post("/api/login")
def login(username: str = "", password: str = ""):
    if username == "admin" and password == "admin123":
        return {"success": True, "token": "demo-token-xxx", "role": "admin", "expires_at": "2026-12-31"}
    return {"success": False, "message": "用户名或密码错误"}


@app.get("/api/dashboard/stats")
def dashboard_stats():
    return {
        "park_count": 12, "device_count": 1248, "order_count": 36,
        "online_users": 89, "alert_count": 8, "report_count": 156,
    }


@app.get("/api/users")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    status: Optional[str] = None,
):
    all_users = [
        {"id": 1, "name": "陈志远", "role": "管理员", "email": "chen.zhiyuan@park.com", "phone": "13800000001", "department": "管理部", "status": "正常", "created_at": "2025-01-15"},
        {"id": 2, "name": "林晓彤", "role": "运维人员", "email": "lin.xiaotong@park.com", "phone": "13800000002", "department": "工程部", "status": "正常", "created_at": "2025-03-20"},
        {"id": 3, "name": "周明轩", "role": "保安队长", "email": "zhou.mingxuan@park.com", "phone": "13800000003", "department": "安保部", "status": "正常", "created_at": "2025-06-10"},
        {"id": 4, "name": "许静怡", "role": "财务", "email": "xu.jingyi@park.com", "phone": "13800000004", "department": "财务部", "status": "正常", "created_at": "2025-08-01"},
        {"id": 5, "name": "高文博", "role": "操作员", "email": "gao.wenbo@park.com", "phone": "13800000005", "department": "运营部", "status": "停用", "created_at": "2025-11-15"},
        {"id": 6, "name": "何雨桐", "role": "巡检员", "email": "he.yutong@park.com", "phone": "13800000006", "department": "巡检部", "status": "正常", "created_at": "2026-01-10"},
    ]
    filtered = all_users
    if keyword:
        filtered = [u for u in filtered if keyword in u["name"] or keyword in u["email"]]
    if status:
        filtered = [u for u in filtered if u["status"] == status]
    start = (page - 1) * page_size
    return {"total": len(filtered), "page": page, "page_size": page_size, "items": filtered[start:start + page_size]}


@app.get("/api/users/{user_id}")
def get_user(user_id: int):
    for u in _list_all_users():
        if u["id"] == user_id:
            return u
    raise HTTPException(status_code=404, detail="用户不存在")


@app.post("/api/users")
def create_user(name: str, role: str, email: str, phone: str = "", department: str = ""):
    new_user = {"id": 100, "name": name, "role": role, "email": email, "phone": phone, "department": department, "status": "正常", "created_at": datetime.now().isoformat()}
    return {"success": True, "user": new_user}


@app.put("/api/users/{user_id}")
def update_user(user_id: int, name: Optional[str] = None, role: Optional[str] = None, email: Optional[str] = None, status: Optional[str] = None):
    return {"success": True, "message": f"用户 {user_id} 已更新"}


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int):
    return {"success": True, "message": f"用户 {user_id} 已删除"}


def _list_all_users():
    return [
        {"id": 1, "name": "陈志远", "role": "管理员", "email": "chen.zhiyuan@park.com", "phone": "13800000001", "department": "管理部", "status": "正常", "created_at": "2025-01-15"},
        {"id": 2, "name": "林晓彤", "role": "运维人员", "email": "lin.xiaotong@park.com", "phone": "13800000002", "department": "工程部", "status": "正常", "created_at": "2025-03-20"},
    ]


@app.get("/api/devices")
def list_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    device_type: Optional[str] = None,
    status: Optional[str] = None,
    location: Optional[str] = None,
):
    all_devices = [
        {"id": "DEV-001", "name": "园区大门摄像头", "type": "监控设备", "location": "A区入口", "status": "在线", "ip": "192.168.1.101", "last_check": "2026-04-30 14:30"},
        {"id": "DEV-002", "name": "停车场道闸", "type": "通行设备", "location": "B1层", "status": "在线", "ip": "192.168.1.102", "last_check": "2026-04-30 14:31"},
        {"id": "DEV-003", "name": "中央空调主机", "type": "暖通设备", "location": "机房1", "status": "维护中", "ip": "192.168.1.103", "last_check": "2026-04-30 12:00"},
        {"id": "DEV-004", "name": "消防水泵", "type": "消防设备", "location": "泵房", "status": "在线", "ip": "192.168.1.104", "last_check": "2026-04-30 14:28"},
        {"id": "DEV-005", "name": "电梯1号", "type": "通行设备", "location": "1号楼", "status": "离线", "ip": "192.168.1.105", "last_check": "2026-04-29 08:00"},
        {"id": "DEV-006", "name": "配电柜A区", "type": "电力设备", "location": "配电房A", "status": "在线", "ip": "192.168.1.106", "last_check": "2026-04-30 14:32"},
        {"id": "DEV-007", "name": "供水泵", "type": "给排水设备", "location": "水泵房", "status": "在线", "ip": "192.168.1.107", "last_check": "2026-04-30 14:29"},
        {"id": "DEV-008", "name": "门禁控制器", "type": "安防设备", "location": "各出入口", "status": "在线", "ip": "192.168.1.108", "last_check": "2026-04-30 14:33"},
    ]
    filtered = all_devices
    if device_type:
        filtered = [d for d in filtered if d["type"] == device_type]
    if status:
        filtered = [d for d in filtered if d["status"] == status]
    if location:
        filtered = [d for d in filtered if location in d["location"]]
    start = (page - 1) * page_size
    return {"total": len(filtered), "page": page, "page_size": page_size, "items": filtered[start:start + page_size]}


@app.get("/api/reports")
def list_reports(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    reports = [
        {"id": "RPT-001", "name": "月度库存报表", "type": "库存", "creator": "系统", "date": "2026-04-01", "status": "已完成"},
        {"id": "RPT-002", "name": "设备巡检周报", "type": "巡检", "creator": "张工", "date": "2026-04-25", "status": "已完成"},
        {"id": "RPT-003", "name": "工单处理日报", "type": "工单", "creator": "李管理", "date": "2026-04-30", "status": "处理中"},
        {"id": "RPT-004", "name": "园区能耗分析", "type": "能耗", "creator": "系统", "date": "2026-04-28", "status": "已完成"},
        {"id": "RPT-005", "name": "安全巡检月报", "type": "安全", "creator": "王队长", "date": "2026-04-29", "status": "已完成"},
        {"id": "RPT-006", "name": "设备维修统计", "type": "维修", "creator": "系统", "date": "2026-04-30", "status": "处理中"},
    ]
    start = (page - 1) * page_size
    return {"total": len(reports), "items": reports[start:start + page_size]}


@app.get("/api/alerts")
def list_alerts(page: int = Query(1, ge=1), level: Optional[str] = None):
    alerts = [
        {"id": "ALT-001", "device": "中央空调主机", "type": "温度异常", "level": "严重", "time": "2026-04-30 14:35", "status": "未处理"},
        {"id": "ALT-002", "device": "电梯1号", "type": "运行故障", "level": "严重", "time": "2026-04-30 12:10", "status": "处理中"},
        {"id": "ALT-003", "device": "消防水泵", "type": "压力偏低", "level": "警告", "time": "2026-04-30 10:22", "status": "已处理"},
        {"id": "ALT-004", "device": "园区大门摄像头", "type": "信号丢失", "level": "严重", "time": "2026-04-29 23:45", "status": "已处理"},
        {"id": "ALT-005", "device": "停车场道闸", "type": "通信超时", "level": "警告", "time": "2026-04-29 18:30", "status": "已处理"},
        {"id": "ALT-006", "device": "配电柜A区", "type": "电流过载", "level": "严重", "time": "2026-04-29 15:00", "status": "处理中"},
        {"id": "ALT-007", "device": "供水泵", "type": "流量异常", "level": "提示", "time": "2026-04-29 09:15", "status": "已处理"},
        {"id": "ALT-008", "device": "门禁系统", "type": "非法闯入", "level": "严重", "time": "2026-04-28 22:00", "status": "已处理"},
    ]
    filtered = alerts
    if level:
        filtered = [a for a in filtered if a["level"] == level]
    return {"total": len(filtered), "items": filtered}


@app.get("/api/settings")
def get_settings():
    return {
        "system_name": "智慧园区管理平台", "version": "V1.0",
        "alerts_enabled": True, "backup_enabled": True,
        "log_retention_days": 90, "session_timeout_minutes": 30,
        "max_login_attempts": 5, "password_min_length": 8,
    }


@app.put("/api/settings")
def update_settings(system_name: Optional[str] = None, alerts_enabled: Optional[bool] = None, backup_enabled: Optional[bool] = None, log_retention_days: Optional[int] = None, session_timeout_minutes: Optional[int] = None, max_login_attempts: Optional[int] = None, password_min_length: Optional[int] = None):
    updated = {}
    if system_name is not None: updated["system_name"] = system_name
    if alerts_enabled is not None: updated["alerts_enabled"] = alerts_enabled
    if backup_enabled is not None: updated["backup_enabled"] = backup_enabled
    if log_retention_days is not None: updated["log_retention_days"] = log_retention_days
    if session_timeout_minutes is not None: updated["session_timeout_minutes"] = session_timeout_minutes
    if max_login_attempts is not None: updated["max_login_attempts"] = max_login_attempts
    if password_min_length is not None: updated["password_min_length"] = password_min_length
    return {"success": True, "updated_fields": list(updated.keys())}
