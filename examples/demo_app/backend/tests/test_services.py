"""Unit tests for the backend services of the demo application."""

import unittest
from datetime import datetime
from app.models import User, Device, Alert, Report, AppSettings
from app.services import UserService, DeviceService, AlertService, ReportService, SettingsService
from app.permissions import PermissionManager, Role, Permission


class TestUserService(unittest.TestCase):
    def setUp(self):
        self.service = UserService()
        self.user = User(id=1, name="测试用户", role="操作员", email="test@park.com",
                         phone="13800000001", department="测试部", status="正常",
                         created_at="2025-01-01T00:00:00")

    def test_validate_email_valid(self):
        self.assertTrue(self.service.validate_email("test@example.com"))
        self.assertTrue(self.service.validate_email("a@b.co"))

    def test_validate_email_invalid(self):
        self.assertFalse(self.service.validate_email("invalid"))
        self.assertFalse(self.service.validate_email("test@"))

    def test_validate_phone_valid(self):
        self.assertTrue(self.service.validate_phone("13800000001"))

    def test_validate_phone_invalid(self):
        self.assertFalse(self.service.validate_phone("123"))
        self.assertFalse(self.service.validate_phone("12345678901"))

    def test_can_create_user(self):
        self.assertTrue(self.service.can_create_user("管理员", "操作员"))
        self.assertTrue(self.service.can_create_user("管理员", "保安队长"))
        self.assertFalse(self.service.can_create_user("操作员", "管理员"))

    def test_calculate_account_age(self):
        days = self.service.calculate_account_age(self.user)
        self.assertGreater(days, 0)

    def test_generate_welcome_message(self):
        msg = self.service.generate_welcome_message(self.user)
        self.assertIn("测试用户", msg)
        self.assertIn("操作员", msg)


class TestDeviceService(unittest.TestCase):
    def setUp(self):
        self.service = DeviceService()
        self.devices = [
            Device(id="D1", name="设备1", type="监控", location="A区", status="在线"),
            Device(id="D2", name="设备2", type="通行", location="B区", status="离线"),
            Device(id="D3", name="设备3", type="消防", location="C区", status="维护中"),
            Device(id="D4", name="设备4", type="监控", location="D区", status="在线"),
        ]

    def test_get_online_count(self):
        self.assertEqual(self.service.get_online_count(self.devices), 2)

    def test_get_offline_count(self):
        self.assertEqual(self.service.get_offline_count(self.devices), 1)

    def test_get_maintenance_count(self):
        self.assertEqual(self.service.get_maintenance_count(self.devices), 1)

    def test_device_type_distribution(self):
        dist = self.service.device_type_distribution(self.devices)
        self.assertEqual(dist["监控"], 2)
        self.assertEqual(dist["通行"], 1)

    def test_find_devices_needing_attention(self):
        needs = self.service.find_devices_needing_attention(self.devices)
        self.assertEqual(len(needs), 2)

    def test_calculate_uptime_percentage(self):
        uptime = self.service.calculate_uptime_percentage(self.devices)
        self.assertEqual(uptime, 50.0)


class TestAlertService(unittest.TestCase):
    def setUp(self):
        self.service = AlertService()
        self.alerts = [
            Alert(id="A1", device="D1", type="温度", level="严重", time="2026-01-01", status="未处理"),
            Alert(id="A2", device="D2", type="压力", level="警告", time="2026-01-01", status="处理中"),
            Alert(id="A3", device="D3", type="流量", level="提示", time="2026-01-01", status="已处理"),
        ]

    def test_get_unresolved_count(self):
        self.assertEqual(self.service.get_unresolved_count(self.alerts), 2)

    def test_get_critical_count(self):
        self.assertEqual(self.service.get_critical_count(self.alerts), 1)

    def test_sort_by_severity(self):
        sorted_alerts = self.service.sort_by_severity(self.alerts)
        self.assertEqual(sorted_alerts[0].level, "严重")

    def test_resolve_alert(self):
        alert = self.alerts[0]
        resolved = self.service.resolve_alert(alert, "admin")
        self.assertEqual(resolved.status, "已处理")
        self.assertEqual(resolved.handler, "admin")

    def test_get_alerts_summary(self):
        summary = self.service.get_alerts_summary(self.alerts)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["unresolved"], 2)
        self.assertEqual(summary["critical"], 1)


class TestReportService(unittest.TestCase):
    def setUp(self):
        self.service = ReportService()
        self.reports = [
            Report(id="R1", name="报表1", type="库存", creator="系统", date="2026-01-01", status="已完成"),
            Report(id="R2", name="报表2", type="巡检", creator="张工", date="2026-01-02", status="处理中"),
        ]

    def test_generate_report_name(self):
        date = datetime(2026, 1, 15)
        name = self.service.generate_report_name("库存", date)
        self.assertIn("库存", name)
        self.assertIn("2026", name)

    def test_filter_by_type(self):
        filtered = self.service.filter_by_type(self.reports, "库存")
        self.assertEqual(len(filtered), 1)

    def test_get_pending_reports(self):
        pending = self.service.get_pending_reports(self.reports)
        self.assertEqual(len(pending), 1)

    def test_calculate_completion_rate(self):
        rate = self.service.calculate_completion_rate(self.reports)
        self.assertEqual(rate, 50.0)


class TestSettingsService(unittest.TestCase):
    def setUp(self):
        self.service = SettingsService()

    def test_get_default_settings(self):
        settings = self.service.get_default_settings()
        self.assertEqual(settings.system_name, "智慧园区管理平台")
        self.assertEqual(settings.password_min_length, 8)

    def test_validate_settings_valid(self):
        settings = self.service.get_default_settings()
        errors = self.service.validate_settings(settings)
        self.assertEqual(len(errors), 0)

    def test_validate_settings_invalid(self):
        settings = AppSettings(log_retention_days=0, password_min_length=3)
        errors = self.service.validate_settings(settings)
        self.assertGreater(len(errors), 0)

    def test_merge_settings(self):
        settings = self.service.get_default_settings()
        updated = self.service.merge_settings(settings, {"system_name": "新名称", "log_retention_days": 180})
        self.assertEqual(updated.system_name, "新名称")
        self.assertEqual(updated.log_retention_days, 180)
        self.assertEqual(updated.password_min_length, 8)


class TestPermissionManager(unittest.TestCase):
    def setUp(self):
        self.pm = PermissionManager()

    def test_admin_has_all_permissions(self):
        self.assertTrue(self.pm.has_permission(Role.ADMIN, Permission.VIEW_DASHBOARD))
        self.assertTrue(self.pm.has_permission(Role.ADMIN, Permission.DELETE_USER))
        self.assertTrue(self.pm.has_permission(Role.ADMIN, Permission.MANAGE_BACKUPS))

    def test_viewer_permissions(self):
        self.assertTrue(self.pm.has_permission(Role.VIEWER, Permission.VIEW_DASHBOARD))
        self.assertFalse(self.pm.has_permission(Role.VIEWER, Permission.DELETE_USER))

    def test_can_manage_user(self):
        self.assertTrue(self.pm.can_manage_user(Role.ADMIN, Role.VIEWER))
        self.assertFalse(self.pm.can_manage_user(Role.VIEWER, Role.ADMIN))

    def test_validate_permission(self):
        self.assertTrue(self.pm.validate_permission("管理员", "view_dashboard"))
        self.assertFalse(self.pm.validate_permission("操作员", "delete_user"))

    def test_get_assignable_roles(self):
        roles = self.pm.get_assignable_roles(Role.ADMIN)
        self.assertGreater(len(roles), 0)
        self.assertNotIn(Role.ADMIN, roles)


if __name__ == "__main__":
    unittest.main()
