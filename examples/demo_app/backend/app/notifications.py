"""WebSocket notification service for real-time updates in the demo application."""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable


@dataclass
class Notification:
    id: str
    type: str
    title: str
    content: str
    timestamp: str = ""
    read: bool = False
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")


class NotificationService:
    """Simple in-memory notification service with subscriber pattern."""

    def __init__(self):
        self._notifications: list[Notification] = []
        self._subscribers: dict[str, list[Callable[[Notification], Awaitable[None]]]] = {}
        self._id_counter: int = 0

    def _generate_id(self) -> str:
        self._id_counter += 1
        return f"NOTIF-{self._id_counter:06d}"

    async def send_notification(
        self,
        notification_type: str,
        title: str,
        content: str,
        data: Optional[dict] = None,
    ) -> Notification:
        notification = Notification(
            id=self._generate_id(),
            type=notification_type,
            title=title,
            content=content,
            data=data or {},
        )
        self._notifications.append(notification)
        await self._notify_subscribers(notification)
        return notification

    async def send_alert_notification(self, device: str, alert_type: str, level: str) -> Notification:
        return await self.send_notification(
            notification_type="alert",
            title=f"设备告警 - {device}",
            content=f"{device} 发生 {alert_type}，级别: {level}",
            data={"device": device, "alert_type": alert_type, "level": level},
        )

    async def send_system_notification(self, title: str, content: str) -> Notification:
        return await self.send_notification(
            notification_type="system",
            title=title,
            content=content,
        )

    async def send_report_notification(self, report_name: str) -> Notification:
        return await self.send_notification(
            notification_type="report",
            title="报表生成完成",
            content=f"{report_name} 已生成完毕，可前往下载",
            data={"report_name": report_name},
        )

    def subscribe(
        self,
        subscriber_id: str,
        callback: Callable[[Notification], Awaitable[None]],
    ) -> None:
        if subscriber_id not in self._subscribers:
            self._subscribers[subscriber_id] = []
        self._subscribers[subscriber_id].append(callback)

    def unsubscribe(self, subscriber_id: str, callback: Optional[Callable] = None) -> None:
        if subscriber_id not in self._subscribers:
            return
        if callback:
            self._subscribers[subscriber_id] = [
                cb for cb in self._subscribers[subscriber_id] if cb != callback
            ]
        else:
            del self._subscribers[subscriber_id]

    async def _notify_subscribers(self, notification: Notification) -> None:
        for subscriber_id, callbacks in list(self._subscribers.items()):
            for callback in callbacks:
                try:
                    await callback(notification)
                except Exception as e:
                    print(f"Notification callback error for {subscriber_id}: {e}")

    def get_notifications(
        self,
        notification_type: Optional[str] = None,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        result = self._notifications
        if notification_type:
            result = [n for n in result if n.type == notification_type]
        if unread_only:
            result = [n for n in result if not n.read]
        return list(reversed(result))[:limit]

    def mark_read(self, notification_id: str) -> bool:
        for notification in self._notifications:
            if notification.id == notification_id:
                notification.read = True
                return True
        return False

    def mark_all_read(self) -> int:
        count = 0
        for notification in self._notifications:
            if not notification.read:
                notification.read = True
                count += 1
        return count

    def get_unread_count(self) -> int:
        return sum(1 for n in self._notifications if not n.read)

    def clear_old_notifications(self, max_age_hours: int = 24) -> int:
        cutoff = time.time() - (max_age_hours * 3600)
        original_count = len(self._notifications)
        self._notifications = [
            n for n in self._notifications
            if self._parse_timestamp(n.timestamp) > cutoff
        ]
        return original_count - len(self._notifications)

    @staticmethod
    def _parse_timestamp(ts: str) -> float:
        try:
            import datetime
            dt = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            return dt.timestamp()
        except (ValueError, OSError):
            return 0.0


notification_service = NotificationService()
