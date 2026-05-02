"""Backend routes for the demo application with full CRUD operations."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/api/v2", tags=["v2"])


@router.get("/dashboard/summary")
def dashboard_summary():
    return {
        "stats": {"parks": 12, "devices": 1248, "orders": 36, "users": 89, "alerts": 8, "reports": 156},
        "recent_activities": [
            {"action": "设备巡检", "user": "张工", "time": "2026-04-30 14:30", "result": "正常"},
            {"action": "工单处理", "user": "李管理", "time": "2026-04-30 14:15", "result": "完成"},
            {"action": "告警响应", "user": "系统", "time": "2026-04-30 14:00", "result": "已处理"},
            {"action": "报表生成", "user": "系统", "time": "2026-04-30 12:00", "result": "成功"},
            {"action": "用户登录", "user": "admin", "time": "2026-04-30 08:00", "result": "成功"},
        ],
        "system_health": {
            "cpu_usage": 35.2, "memory_usage": 62.8, "disk_usage": 45.1,
            "network_status": "正常", "database_status": "正常",
            "uptime_hours": 720, "last_backup": "2026-04-30 02:00",
        },
    }


@router.get("/devices/statistics")
def device_statistics():
    all_devices = [
        {"type": "监控设备", "status": "在线"}, {"type": "监控设备", "status": "在线"},
        {"type": "通行设备", "status": "在线"}, {"type": "通行设备", "status": "离线"},
        {"type": "暖通设备", "status": "维护中"}, {"type": "消防设备", "status": "在线"},
        {"type": "电力设备", "status": "在线"}, {"type": "安防设备", "status": "在线"},
        {"type": "给排水设备", "status": "在线"},
    ]
    type_dist = {}
    status_dist = {}
    for d in all_devices:
        type_dist[d["type"]] = type_dist.get(d["type"], 0) + 1
        status_dist[d["status"]] = status_dist.get(d["status"], 0) + 1
    return {
        "total": len(all_devices),
        "by_type": type_dist,
        "by_status": status_dist,
        "online_rate": round(status_dist.get("在线", 0) / len(all_devices) * 100, 1),
    }


@router.get("/alerts/statistics")
def alert_statistics():
    return {
        "total": 8, "unresolved": 2, "critical": 3,
        "by_level": {"严重": 4, "警告": 3, "提示": 1},
        "by_device_type": {"暖通设备": 1, "通行设备": 1, "安防设备": 2, "消防设备": 1, "电力设备": 1, "给排水设备": 1, "监控设备": 1},
        "resolution_rate": 75.0, "avg_response_time_minutes": 15.3,
    }


@router.get("/reports/generate")
def generate_report(report_type: str = Query(...), date: Optional[str] = None):
    valid_types = ["库存", "巡检", "工单", "能耗", "安全", "维修", "财务", "人力"]
    if report_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"无效的报表类型。支持: {', '.join(valid_types)}")
    report_date = date or datetime.now().strftime("%Y-%m-%d")
    return {
        "success": True,
        "report": {
            "id": f"RPT-{datetime.now().strftime('%Y%m%d%H%M')}",
            "type": report_type, "date": report_date,
            "status": "生成中", "estimated_completion": "5分钟",
        },
    }


@router.get("/search")
def global_search(
    q: str = Query(..., min_length=1),
    scope: Optional[str] = Query("all"),
    page: int = Query(1, ge=1),
):
    results = []
    if scope in ("all", "users"):
        results.append({"type": "user", "name": "陈志远", "match": "陈志远", "link": "/users/1"})
        results.append({"type": "user", "name": "林晓彤", "match": "林晓彤", "link": "/users/2"})
    if scope in ("all", "devices"):
        results.append({"type": "device", "name": "摄像头", "match": "摄像头", "link": "/devices/DEV-001"})
        results.append({"type": "device", "name": "道闸", "match": "道闸", "link": "/devices/DEV-002"})
    if scope in ("all", "reports"):
        results.append({"type": "report", "name": "月报表", "match": "报表", "link": "/reports/RPT-001"})
    return {"query": q, "scope": scope, "total": len(results), "results": results}


@router.get("/logs")
def system_logs(
    page: int = Query(1, ge=1),
    level: Optional[str] = None,
    module: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    all_logs = [
        {"id": 1, "level": "INFO", "module": "auth", "message": "admin 登录成功", "time": "2026-04-30 14:35:00"},
        {"id": 2, "level": "WARN", "module": "device", "message": "DEV-005 设备离线", "time": "2026-04-30 14:30:00"},
        {"id": 3, "level": "ERROR", "module": "alert", "message": "告警处理超时 ALT-001", "time": "2026-04-30 14:20:00"},
        {"id": 4, "level": "INFO", "module": "report", "message": "报表 RPT-001 生成完成", "time": "2026-04-30 14:10:00"},
        {"id": 5, "level": "INFO", "module": "system", "message": "系统备份完成", "time": "2026-04-30 02:00:00"},
        {"id": 6, "level": "INFO", "module": "auth", "message": "陈志远修改密码", "time": "2026-04-29 16:00:00"},
        {"id": 7, "level": "WARN", "module": "device", "message": "DEV-003 维护到期", "time": "2026-04-29 12:00:00"},
        {"id": 8, "level": "INFO", "module": "user", "message": "林晓彤更新个人信息", "time": "2026-04-29 10:00:00"},
    ]
    filtered = all_logs
    if level:
        filtered = [l for l in filtered if l["level"] == level]
    if module:
        filtered = [l for l in filtered if l["module"] == module]
    start = (page - 1) * 10
    return {"total": len(filtered), "page": page, "items": filtered[start:start + 10]}


@router.get("/backup/status")
def backup_status():
    return {
        "enabled": True, "last_backup": "2026-04-30 02:00:00",
        "next_backup": "2026-05-01 02:00:00", "backup_size_mb": 256.4,
        "retention_days": 90, "backup_count": 87,
        "recent_backups": [
            {"date": "2026-04-30", "size_mb": 256.4, "status": "成功"},
            {"date": "2026-04-29", "size_mb": 254.1, "status": "成功"},
            {"date": "2026-04-28", "size_mb": 252.8, "status": "成功"},
        ],
    }


@router.post("/backup/trigger")
def trigger_backup():
    return {"success": True, "message": "备份任务已触发", "backup_id": f"BAK-{datetime.now().strftime('%Y%m%d%H%M%S')}"}


@router.get("/notifications")
def list_notifications(unread_only: bool = False, page: int = Query(1, ge=1)):
    notifications = [
        {"id": 1, "type": "alert", "title": "设备告警", "content": "中央空调主机温度异常", "read": False, "time": "2026-04-30 14:35"},
        {"id": 2, "type": "system", "title": "系统通知", "content": "系统将在今晚 02:00 进行自动备份", "read": True, "time": "2026-04-30 08:00"},
        {"id": 3, "type": "report", "title": "报表完成", "content": "月度库存报表已生成完毕", "read": False, "time": "2026-04-30 12:00"},
        {"id": 4, "type": "maintenance", "title": "维护提醒", "content": "DEV-003 中央空调主机维护到期", "read": False, "time": "2026-04-29 12:00"},
    ]
    filtered = notifications
    if unread_only:
        filtered = [n for n in notifications if not n["read"]]
    return {"total": len(filtered), "unread": sum(1 for n in notifications if not n["read"]), "items": filtered}


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int):
    return {"success": True, "message": f"通知 {notification_id} 已标记为已读"}
