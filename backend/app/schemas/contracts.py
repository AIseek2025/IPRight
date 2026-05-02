from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AppManifest:
    product_name: str
    version: str
    app_type: str = "admin_web"
    frontend_framework: str = "react_vite"
    backend_framework: str = "fastapi"
    entry_routes: list[str] = field(default_factory=list)
    demo_accounts: list[dict] = field(default_factory=list)


@dataclass
class RunManifest:
    install_commands: list[str] = field(default_factory=list)
    start_commands: list[str] = field(default_factory=list)
    working_directories: dict[str, str] = field(default_factory=dict)
    ports: dict[str, int] = field(default_factory=dict)
    health_checks: list[str] = field(default_factory=list)


@dataclass
class CaptureScenario:
    id: str
    title: str
    route: str
    requires_auth: bool = False
    actions: list[dict] = field(default_factory=list)
    capture_type: str = "full_page"
    priority: int = 0


@dataclass
class CaptureManifest:
    scenarios: list[CaptureScenario] = field(default_factory=list)


@dataclass
class CodeIndexManifest:
    include_globs: list[str] = field(default_factory=list)
    exclude_globs: list[str] = field(default_factory=list)
    preferred_order: list[str] = field(default_factory=list)
    line_density_target: int = 55
