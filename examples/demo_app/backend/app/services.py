"""Business logic services for the demo application."""

from datetime import datetime, timedelta
from typing import Optional
from app.models import User, Device, Alert, Report, AppSettings


class UserService:
    """User management service with CRUD operations and validation."""

    def validate_email(self, email: str) -> bool:
        return "@" in email and "." in email.split("@")[-1]

    def validate_phone(self, phone: str) -> bool:
        return len(phone) == 11 and phone.startswith("1")

    def can_create_user(self, current_role: str, target_role: str) -> bool:
        role_hierarchy = {"管理员": 3, "运维人员": 2, "操作员": 1, "保安队长": 1}
        return role_hierarchy.get(current_role, 0) > role_hierarchy.get(target_role, 0)

    def calculate_account_age(self, user: User) -> int:
        if not user.created_at:
            return 0
        try:
            created = datetime.fromisoformat(user.created_at)
            return (datetime.now() - created).days
        except ValueError:
            return 0

    def generate_welcome_message(self, user: User) -> str:
        return f"欢迎 {user.name} ({user.role}) 加入 {user.department}!"


class DeviceService:
    """Device management and monitoring service."""

    DEVICE_STATUS_ORDER = {"在线": 0, "维护中": 1, "离线": 2}

    def sort_by_status(self, devices: list[Device]) -> list[Device]:
        return sorted(devices, key=lambda d: self.DEVICE_STATUS_ORDER.get(d.status, 99))

    def get_online_count(self, devices: list[Device]) -> int:
        return sum(1 for d in devices if d.is_online())

    def get_offline_count(self, devices: list[Device]) -> int:
        return sum(1 for d in devices if d.status == "离线")

    def get_maintenance_count(self, devices: list[Device]) -> int:
        return sum(1 for d in devices if d.status == "维护中")

    def device_type_distribution(self, devices: list[Device]) -> dict:
        dist: dict = {}
        for d in devices:
            dist[d.type] = dist.get(d.type, 0) + 1
        return dist

    def find_devices_needing_attention(self, devices: list[Device]) -> list[Device]:
        return [d for d in devices if d.needs_maintenance()]

    def calculate_uptime_percentage(self, devices: list[Device]) -> float:
        if not devices:
            return 100.0
        online = self.get_online_count(devices)
        return round((online / len(devices)) * 100, 2)


class AlertService:
    """Alert processing and management service."""

    ALERT_LEVEL_WEIGHTS = {"严重": 3, "警告": 2, "提示": 1}

    def get_unresolved_count(self, alerts: list[Alert]) -> int:
        return sum(1 for a in alerts if not a.is_resolved())

    def get_critical_count(self, alerts: list[Alert]) -> int:
        return sum(1 for a in alerts if a.is_critical() and not a.is_resolved())

    def sort_by_severity(self, alerts: list[Alert]) -> list[Alert]:
        return sorted(alerts, key=lambda a: self.ALERT_LEVEL_WEIGHTS.get(a.level, 0), reverse=True)

    def resolve_alert(self, alert: Alert, handler: str) -> Alert:
        alert.status = "已处理"
        alert.handler = handler
        return alert

    def acknowledge_alert(self, alert: Alert, handler: str) -> Alert:
        alert.status = "处理中"
        alert.handler = handler
        return alert

    def create_alert(self, device: str, alert_type: str, level: str, description: str = "") -> Alert:
        import uuid
        return Alert(
            id=f"ALT-{uuid.uuid4().hex[:6].upper()}",
            device=device, type=alert_type, level=level,
            time=datetime.now().isoformat(), description=description,
        )

    def get_alerts_summary(self, alerts: list[Alert]) -> dict:
        return {
            "total": len(alerts),
            "unresolved": self.get_unresolved_count(alerts),
            "critical": self.get_critical_count(alerts),
            "resolved": sum(1 for a in alerts if a.is_resolved()),
            "in_progress": sum(1 for a in alerts if a.status == "处理中"),
        }


class ReportService:
    """Report generation and management service."""

    REPORT_TYPES = ["库存", "巡检", "工单", "能耗", "安全", "维修", "财务", "人力"]

    def generate_report_name(self, report_type: str, date: datetime) -> str:
        month_names = ["", "一月", "二月", "三月", "四月", "五月", "六月",
                       "七月", "八月", "九月", "十月", "十一月", "十二月"]
        return f"{date.year}年{month_names[date.month]}{report_type}报表"

    def filter_by_type(self, reports: list[Report], report_type: str) -> list[Report]:
        return [r for r in reports if r.type == report_type]

    def filter_by_date_range(self, reports: list[Report], start: str, end: str) -> list[Report]:
        return [r for r in reports if start <= r.date <= end]

    def get_pending_reports(self, reports: list[Report]) -> list[Report]:
        return [r for r in reports if r.status == "处理中"]

    def get_completed_count(self, reports: list[Report]) -> int:
        return sum(1 for r in reports if r.status == "已完成")

    def calculate_completion_rate(self, reports: list[Report]) -> float:
        if not reports:
            return 100.0
        return round((self.get_completed_count(reports) / len(reports)) * 100, 1)


class SettingsService:
    """Application settings management and validation."""

    def validate_settings(self, settings: AppSettings) -> list[str]:
        return settings.validate()

    def get_default_settings(self) -> AppSettings:
        return AppSettings(
            system_name="智慧园区管理平台",
            version="V1.0",
            alerts_enabled=True,
            backup_enabled=True,
            log_retention_days=90,
            session_timeout_minutes=30,
            max_login_attempts=5,
            password_min_length=8,
        )

    def merge_settings(self, current: AppSettings, updates: dict) -> AppSettings:
        for key, value in updates.items():
            if hasattr(current, key) and value is not None:
                setattr(current, key, value)
        return current
