from __future__ import annotations

import os
from collections.abc import Callable

from app.services.project_profile import build_backend_profile_source

GENERATED_BACKEND_APP_FILES = {
    "app_profile.py",
    "main.py",
    "routes.py",
    "models.py",
    "services.py",
}


def render_backend_main() -> str:
    return """from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.app_profile import APP_PROFILE

app = FastAPI(title=f\"{APP_PROFILE['product_name']} API\")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[\"*\"],
    allow_credentials=True,
    allow_methods=[\"*\"],
    allow_headers=[\"*\"],
)


def _find_module(module_key: str) -> dict:
    for module in APP_PROFILE[\"modules\"]:
        if module[\"key\"] == module_key:
            return module
    raise HTTPException(status_code=404, detail=\"模块不存在\")


@app.get(\"/health\")
def health():
    return {
        \"status\": \"ok\",
        \"version\": APP_PROFILE[\"version\"],
        \"service\": APP_PROFILE[\"product_name\"],
        \"scene\": APP_PROFILE[\"scene\"],
    }


@app.post(\"/api/login\")
def login(username: str = \"\", password: str = \"\"):
    if username == \"admin\" and password == \"admin123\":
        return {
            \"success\": True,
            \"token\": \"demo-token-xxx\",
            \"role\": APP_PROFILE[\"user_roles\"][0],
            \"expires_at\": \"2026-12-31\",
        }
    return {\"success\": False, \"message\": \"用户名或密码错误\"}


@app.get(\"/api/overview\")
def overview():
    return {
        \"product_name\": APP_PROFILE[\"product_name\"],
        \"version\": APP_PROFILE[\"version\"],
        \"scene\": APP_PROFILE[\"scene\"],
        \"industry_scope\": APP_PROFILE[\"industry_scope\"],
        \"roles\": APP_PROFILE[\"user_roles\"],
        \"modules\": [module[\"title\"] for module in APP_PROFILE[\"modules\"]],
    }


@app.get(\"/api/dashboard/stats\")
def dashboard_stats():
    return {
        \"cards\": APP_PROFILE[\"dashboard_metrics\"],
        \"module_count\": len(APP_PROFILE[\"modules\"]),
        \"role_count\": len(APP_PROFILE[\"user_roles\"]),
        \"generated_at\": datetime.now().isoformat(),
    }


@app.get(\"/api/modules\")
def list_modules():
    return {
        \"total\": len(APP_PROFILE[\"modules\"]),
        \"items\": [
            {
                \"key\": module[\"key\"],
                \"title\": module[\"title\"],
                \"route\": module[\"route\"],
                \"description\": module[\"description\"],
                \"primary_action\": module[\"primary_action\"],
            }
            for module in APP_PROFILE[\"modules\"]
        ],
    }


@app.get(\"/api/modules/{module_key}/items\")
def module_items(
    module_key: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
):
    module = _find_module(module_key)
    rows = module[\"rows\"]
    if keyword:
        rows = [row for row in rows if any(keyword in str(cell) for cell in row)]
    start = (page - 1) * page_size
    return {
        \"module\": module[\"title\"],
        \"headers\": module[\"table_headers\"],
        \"total\": len(rows),
        \"page\": page,
        \"page_size\": page_size,
        \"items\": rows[start:start + page_size],
    }


@app.get(\"/api/settings\")
def get_settings():
    return {
        \"system_name\": APP_PROFILE[\"product_name\"],
        \"version\": APP_PROFILE[\"version\"],
        \"industry_scope\": APP_PROFILE[\"industry_scope\"],
        \"support_environment\": APP_PROFILE[\"support_environment\"],
        \"development_tools\": APP_PROFILE[\"development_tools\"],
        \"programming_language\": APP_PROFILE[\"programming_language\"],
    }
"""


def render_backend_routes() -> str:
    return """from __future__ import annotations

from app.app_profile import APP_PROFILE


def list_route_map() -> list[dict]:
    return [
        {\"path\": \"/dashboard\", \"title\": \"系统首页\"},
        *[
            {\"path\": module[\"route\"], \"title\": module[\"title\"]}
            for module in APP_PROFILE[\"modules\"]
        ],
    ]
"""


def render_backend_models() -> str:
    return """from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModuleRecord:
    key: str
    title: str
    route: str
    primary_action: str
    description: str
"""


def render_backend_services() -> str:
    return """from __future__ import annotations

from app.app_profile import APP_PROFILE


def summarize_profile() -> dict:
    return {
        \"product_name\": APP_PROFILE[\"product_name\"],
        \"scene\": APP_PROFILE[\"scene\"],
        \"module_count\": len(APP_PROFILE[\"modules\"]),
        \"roles\": APP_PROFILE[\"user_roles\"],
    }
"""


def write_generated_backend_files(
    backend_root: str,
    profile: dict,
    write_text: Callable[[str, str], None],
) -> None:
    app_root = os.path.join(backend_root, "app")
    write_text(os.path.join(app_root, "app_profile.py"), build_backend_profile_source(profile))
    write_text(os.path.join(app_root, "main.py"), render_backend_main())
    write_text(os.path.join(app_root, "routes.py"), render_backend_routes())
    write_text(os.path.join(app_root, "models.py"), render_backend_models())
    write_text(os.path.join(app_root, "services.py"), render_backend_services())
