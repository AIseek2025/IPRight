"""Permission and RBAC (Role-Based Access Control) system for the demo application."""

from enum import Enum
from typing import Optional


class Permission(Enum):
    VIEW_DASHBOARD = "view_dashboard"
    VIEW_USERS = "view_users"
    CREATE_USER = "create_user"
    EDIT_USER = "edit_user"
    DELETE_USER = "delete_user"
    VIEW_DEVICES = "view_devices"
    MANAGE_DEVICES = "manage_devices"
    VIEW_REPORTS = "view_reports"
    GENERATE_REPORTS = "generate_reports"
    VIEW_ALERTS = "view_alerts"
    MANAGE_ALERTS = "manage_alerts"
    EDIT_SETTINGS = "edit_settings"
    VIEW_LOGS = "view_logs"
    MANAGE_BACKUPS = "manage_backups"
    MANAGE_USERS = "manage_users"


class Role(Enum):
    ADMIN = "管理员"
    OPERATOR = "运维人员"
    SECURITY = "保安队长"
    FINANCE = "财务"
    INSPECTOR = "巡检员"
    VIEWER = "操作员"


ROLE_PERMISSIONS: dict[Role, list[Permission]] = {
    Role.ADMIN: [
        Permission.VIEW_DASHBOARD, Permission.VIEW_USERS, Permission.CREATE_USER,
        Permission.EDIT_USER, Permission.DELETE_USER, Permission.MANAGE_USERS,
        Permission.VIEW_DEVICES, Permission.MANAGE_DEVICES,
        Permission.VIEW_REPORTS, Permission.GENERATE_REPORTS,
        Permission.VIEW_ALERTS, Permission.MANAGE_ALERTS,
        Permission.EDIT_SETTINGS, Permission.VIEW_LOGS, Permission.MANAGE_BACKUPS,
    ],
    Role.OPERATOR: [
        Permission.VIEW_DASHBOARD, Permission.VIEW_USERS,
        Permission.VIEW_DEVICES, Permission.MANAGE_DEVICES,
        Permission.VIEW_ALERTS, Permission.MANAGE_ALERTS,
        Permission.VIEW_LOGS,
    ],
    Role.SECURITY: [
        Permission.VIEW_DASHBOARD, Permission.VIEW_DEVICES,
        Permission.VIEW_ALERTS, Permission.MANAGE_ALERTS,
        Permission.VIEW_LOGS,
    ],
    Role.FINANCE: [
        Permission.VIEW_DASHBOARD, Permission.VIEW_REPORTS,
        Permission.GENERATE_REPORTS,
    ],
    Role.INSPECTOR: [
        Permission.VIEW_DASHBOARD, Permission.VIEW_DEVICES,
        Permission.VIEW_ALERTS,
    ],
    Role.VIEWER: [
        Permission.VIEW_DASHBOARD, Permission.VIEW_USERS,
        Permission.VIEW_DEVICES, Permission.VIEW_REPORTS,
    ],
}


class PermissionManager:
    """Manages role-based permissions for the application."""

    def __init__(self):
        self._permissions: dict[Role, list[Permission]] = dict(ROLE_PERMISSIONS)

    def has_permission(self, role: Role, permission: Permission) -> bool:
        """Check if a role has a specific permission."""
        if role not in self._permissions:
            return False
        return permission in self._permissions[role]

    def has_all_permissions(self, role: Role, permissions: list[Permission]) -> bool:
        """Check if a role has all specified permissions."""
        return all(self.has_permission(role, p) for p in permissions)

    def has_any_permission(self, role: Role, permissions: list[Permission]) -> bool:
        """Check if a role has any of the specified permissions."""
        return any(self.has_permission(role, p) for p in permissions)

    def get_permissions(self, role: Role) -> list[Permission]:
        """Get all permissions for a role."""
        return self._permissions.get(role, [])

    def get_roles(self) -> list[Role]:
        """Get all available roles."""
        return list(self._permissions.keys())

    def get_role_by_name(self, name: str) -> Optional[Role]:
        """Find a role by its display name."""
        for role in Role:
            if role.value == name:
                return role
        return None

    def can_manage_user(self, current_role: Role, target_role: Role) -> bool:
        """Check if current role can manage another role."""
        role_levels = {
            Role.ADMIN: 100,
            Role.OPERATOR: 50,
            Role.SECURITY: 30,
            Role.FINANCE: 30,
            Role.INSPECTOR: 20,
            Role.VIEWER: 10,
        }
        current_level = role_levels.get(current_role, 0)
        target_level = role_levels.get(target_role, 0)

        if not self.has_permission(current_role, Permission.MANAGE_USERS):
            return False
        return current_level > target_level

    def get_assignable_roles(self, current_role: Role) -> list[Role]:
        """Get roles that can be assigned by the current role."""
        return [r for r in Role if self.can_manage_user(current_role, r)]

    def validate_permission(self, role_name: str, permission_name: str) -> bool:
        """Validate a permission by string names. Returns True if allowed."""
        role = self.get_role_by_name(role_name)
        if not role:
            return False
        try:
            permission = Permission(permission_name)
            return self.has_permission(role, permission)
        except ValueError:
            return False


permission_manager = PermissionManager()


def check_permission(role_name: str, permission: str) -> bool:
    """Convenience function for permission checking."""
    return permission_manager.validate_permission(role_name, permission)


def require_permission(permission: Permission):
    """Decorator to require a specific permission for a function."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            role_name = kwargs.pop("_role", "操作员")
            if not permission_manager.has_permission(
                permission_manager.get_role_by_name(role_name) or Role.VIEWER,
                permission,
            ):
                raise PermissionError(f"Role '{role_name}' lacks permission: {permission.value}")
            return func(*args, **kwargs)

        return wrapper

    return decorator
