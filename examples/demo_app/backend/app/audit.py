"""Audit trail and logging utilities for tracking system operations."""

import time
import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional


class AuditAction(Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    VIEW = "view"
    EXPORT = "export"
    IMPORT = "import"
    APPROVE = "approve"
    REJECT = "reject"
    ASSIGN = "assign"
    CONFIGURE = "configure"
    BACKUP = "backup"
    RESTORE = "restore"


class AuditSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEntry:
    id: str = ""
    timestamp: str = ""
    user_id: str = ""
    user_name: str = ""
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    severity: str = "info"
    details: str = ""
    ip_address: str = ""
    user_agent: str = ""
    session_id: str = ""
    status: str = "success"
    error_message: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.id:
            raw = f"{self.timestamp}{self.user_id}{self.action}{self.resource_type}{self.resource_id}"
            self.id = hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AuditLogger:
    """Centralized audit logging service."""

    def __init__(self, storage_path: str = "/var/log/audit.jsonl"):
        self.storage_path = storage_path
        self._buffer: list[AuditEntry] = []
        self._max_buffer_size: int = 100

    def log(
        self,
        action: AuditAction,
        resource_type: str,
        resource_id: str = "",
        user_id: str = "",
        user_name: str = "",
        details: str = "",
        severity: AuditSeverity = AuditSeverity.INFO,
        status: str = "success",
        error_message: str = "",
    ) -> AuditEntry:
        entry = AuditEntry(
            user_id=user_id,
            user_name=user_name,
            action=action.value,
            resource_type=resource_type,
            resource_id=resource_id,
            severity=severity.value,
            details=details,
            status=status,
            error_message=error_message,
        )
        self._buffer.append(entry)
        if len(self._buffer) >= self._max_buffer_size:
            self.flush()
        return entry

    def log_login(self, user_id: str, user_name: str, success: bool, error: str = "") -> AuditEntry:
        return self.log(
            action=AuditAction.LOGIN,
            resource_type="session",
            user_id=user_id,
            user_name=user_name,
            status="success" if success else "failure",
            error_message=error,
            severity=AuditSeverity.WARNING if not success else AuditSeverity.INFO,
        )

    def log_create(self, resource_type: str, resource_id: str, user_name: str, details: str = "") -> AuditEntry:
        return self.log(
            action=AuditAction.CREATE,
            resource_type=resource_type,
            resource_id=resource_id,
            user_name=user_name,
            details=details,
        )

    def log_update(self, resource_type: str, resource_id: str, user_name: str, changes: str = "") -> AuditEntry:
        return self.log(
            action=AuditAction.UPDATE,
            resource_type=resource_type,
            resource_id=resource_id,
            user_name=user_name,
            details=f"Changes: {changes}" if changes else "",
        )

    def log_delete(self, resource_type: str, resource_id: str, user_name: str, reason: str = "") -> AuditEntry:
        return self.log(
            action=AuditAction.DELETE,
            resource_type=resource_type,
            resource_id=resource_id,
            user_name=user_name,
            details=f"Reason: {reason}" if reason else "",
            severity=AuditSeverity.WARNING,
        )

    def log_export(self, resource_type: str, user_name: str, count: int = 0) -> AuditEntry:
        return self.log(
            action=AuditAction.EXPORT,
            resource_type=resource_type,
            user_name=user_name,
            details=f"Exported {count} records" if count else "",
        )

    def log_error(self, component: str, error: str, user_name: str = "") -> AuditEntry:
        return self.log(
            action=AuditAction.UPDATE,
            resource_type=component,
            user_name=user_name or "system",
            details=error,
            severity=AuditSeverity.ERROR,
            status="failure",
        )

    def query(
        self,
        user_name: str = "",
        action: str = "",
        resource_type: str = "",
        severity: str = "",
        start_time: str = "",
        end_time: str = "",
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit entries with filters."""
        entries = self._load_all()
        if user_name:
            entries = [e for e in entries if user_name.lower() in e.user_name.lower()]
        if action:
            entries = [e for e in entries if e.action == action]
        if resource_type:
            entries = [e for e in entries if e.resource_type == resource_type]
        if severity:
            entries = [e for e in entries if e.severity == severity]
        if start_time:
            entries = [e for e in entries if e.timestamp >= start_time]
        if end_time:
            entries = [e for e in entries if e.timestamp <= end_time]
        return entries[-limit:]

    def get_statistics(self, days: int = 7) -> dict:
        """Get audit statistics for the last N days."""
        entries = self._load_all()
        cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timedelta
        cutoff -= timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        recent = [e for e in entries if e.timestamp >= cutoff_str]

        stats = {"total": len(recent), "by_action": {}, "by_severity": {}, "by_user": {}}
        for e in recent:
            stats["by_action"][e.action] = stats["by_action"].get(e.action, 0) + 1
            stats["by_severity"][e.severity] = stats["by_severity"].get(e.severity, 0) + 1
            stats["by_user"][e.user_name] = stats["by_user"].get(e.user_name, 0) + 1
        return stats

    def flush(self) -> None:
        """Write buffered entries to storage."""
        if not self._buffer:
            return
        try:
            with open(self.storage_path, "a", encoding="utf-8") as f:
                for entry in self._buffer:
                    f.write(entry.to_json() + "\n")
            self._buffer.clear()
        except Exception as e:
            print(f"Audit flush failed: {e}")

    def _load_all(self) -> list[AuditEntry]:
        """Load all audit entries from storage."""
        entries = []
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            entries.append(AuditEntry(**data))
                        except (json.JSONDecodeError, TypeError):
                            pass
        except FileNotFoundError:
            pass
        return entries


_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
