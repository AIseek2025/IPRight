"""Data models and types for the demo application."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class User:
    id: int
    name: str
    role: str
    email: str
    phone: str = ""
    department: str = ""
    status: str = "正常"
    created_at: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == "正常"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "role": self.role,
            "email": self.email, "phone": self.phone,
            "department": self.department, "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Device:
    id: str
    name: str
    type: str
    location: str
    status: str = "在线"
    ip: str = ""
    last_check: str = ""
    install_date: str = ""
    warranty_expiry: str = ""

    def is_online(self) -> bool:
        return self.status == "在线"

    def needs_maintenance(self) -> bool:
        return self.status in ("维护中", "离线")

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "location": self.location, "status": self.status,
            "ip": self.ip, "last_check": self.last_check,
        }


@dataclass
class Alert:
    id: str
    device: str
    type: str
    level: str
    time: str
    status: str = "未处理"
    description: str = ""
    handler: str = ""

    def is_critical(self) -> bool:
        return self.level == "严重"

    def is_resolved(self) -> bool:
        return self.status == "已处理"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "device": self.device, "type": self.type,
            "level": self.level, "time": self.time, "status": self.status,
        }


@dataclass
class Report:
    id: str
    name: str
    type: str
    creator: str
    date: str
    status: str = "处理中"
    file_format: str = "PDF"
    file_size: int = 0

    def is_ready(self) -> bool:
        return self.status == "已完成"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "creator": self.creator, "date": self.date, "status": self.status,
        }


@dataclass
class AppSettings:
    system_name: str = ""
    version: str = ""
    alerts_enabled: bool = True
    backup_enabled: bool = True
    log_retention_days: int = 90
    session_timeout_minutes: int = 30
    max_login_attempts: int = 5
    password_min_length: int = 8

    def validate(self) -> list[str]:
        errors = []
        if self.log_retention_days < 1:
            errors.append("日志保留天数必须大于0")
        if self.session_timeout_minutes < 1:
            errors.append("会话超时时间必须大于0分钟")
        if self.max_login_attempts < 1:
            errors.append("最大登录尝试次数必须大于0")
        if self.password_min_length < 6:
            errors.append("密码最小长度至少为6")
        return errors

    def to_dict(self) -> dict:
        return {
            "system_name": self.system_name, "version": self.version,
            "alerts_enabled": self.alerts_enabled, "backup_enabled": self.backup_enabled,
            "log_retention_days": self.log_retention_days,
            "session_timeout_minutes": self.session_timeout_minutes,
            "max_login_attempts": self.max_login_attempts,
            "password_min_length": self.password_min_length,
        }
