#!/usr/bin/env python3
"""
IPRight E2E Pipeline Runner
===========================
Runs the full IPRight pipeline end-to-end:
  Keyword -> PRD -> App -> Run -> Capture -> Manual Word -> Code Word -> Export

This script uses the example demo_app as the "generated" application,
bypassing the need for real LLM integration. It runs the pipeline stages
independently to verify the full chain works.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_ROOT / "tmp" / "e2e-workspace"


def log(step: str, msg: str = "") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {step:20s} {msg}")


def step1_setup_workspace(task_id: str) -> Path:
    """Create workspace directory structure."""
    task_dir = WORKSPACE_ROOT / "tasks" / task_id / "workspace"
    task_dir.mkdir(parents=True, exist_ok=True)
    for sub in ["prd", "manifests", "app", "artifacts/screenshots", "builds"]:
        (task_dir / sub).mkdir(parents=True, exist_ok=True)
    return task_dir


def step2_generate_prd(task_dir: Path, keyword: str, product_name: str, version: str) -> dict:
    """Generate PRD and development work order from template."""
    prd_dir = task_dir / "prd"
    prd_dir.mkdir(parents=True, exist_ok=True)

    prd_content = f"""# {product_name} 产品需求文档

## 产品定位
{product_name} 是一款面向园区管理的后台管理型 Web 应用系统。

## 技术栈
- 前端: React + Vite + TypeScript
- 后端: FastAPI + Python
- 数据库: PostgreSQL

## 核心功能模块
1. 首页/仪表盘 - 关键指标展示
2. 用户管理 - 用户的增删改查
3. 设备管理 - 设备台账与状态监控
4. 系统设置 - 系统参数配置

## 用户角色
- 管理员: 拥有全部系统权限

## 非功能需求
- 响应式设计，支持主流浏览器
- 提供 RESTful API
- 支持基础数据 CRUD
"""
    (prd_dir / "product_prd.md").write_text(prd_content, encoding="utf-8")

    work_order = f"""# {product_name} 开发任务书

## 页面任务
1. LoginPage: /login - 登录页
2. DashboardPage: /dashboard - 系统首页仪表盘
3. UserListPage: /users - 用户管理列表
4. DeviceListPage: /devices - 设备管理列表
5. SettingsPage: /settings - 系统设置

## API 任务
- POST /api/login - 用户登录
- GET /api/users - 用户列表
- GET /api/devices - 设备列表

## Demo 账号
- admin / admin123
"""
    (prd_dir / "development_work_order.md").write_text(work_order, encoding="utf-8")

    prd_summary = {
        "app_type": "admin_web",
        "user_roles": ["admin"],
        "core_modules": ["首页", "用户管理", "设备管理", "系统设置"],
        "required_pages": ["/login", "/dashboard", "/users", "/devices", "/settings"],
    }
    (prd_dir / "product_summary.json").write_text(json.dumps(prd_summary, ensure_ascii=False, indent=2))

    return prd_summary


def step3_copy_demo_app(task_dir: Path) -> None:
    """Copy the example demo_app as the 'generated' application."""
    demo_app = PROJECT_ROOT / "examples" / "demo_app"
    app_dir = task_dir / "app"

    if app_dir.exists():
        shutil.rmtree(app_dir)

    shutil.copytree(demo_app, app_dir, dirs_exist_ok=True)

    # Copy manifests to the manifests dir
    for mf in ["app_manifest.json", "run_manifest.json", "capture_manifest.json", "code_index_manifest.json"]:
        src = app_dir / "manifests" / mf
        dst = task_dir / "manifests" / mf
        if src.exists():
            shutil.copy(src, dst)


def step4_validate_manifests(task_dir: Path) -> dict:
    """Validate all manifests."""
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    from app.services.validator import ManifestValidator

    validator = ManifestValidator()
    manifests = {}
    for name in ["app_manifest", "run_manifest", "capture_manifest", "code_index_manifest"]:
        mf_path = task_dir / "manifests" / f"{name}.json"
        if mf_path.exists():
            manifests[name] = json.loads(mf_path.read_text(encoding="utf-8"))

    results = validator.validate_all(manifests)
    return {"all_valid": validator.is_all_valid(results), "results": results}


def step5_verify_run(app_dir: Path) -> dict:
    """Verify the app starts and health check passes."""
    import subprocess
    import time as time_mod

    run_manifest = json.loads((app_dir / "manifests" / "run_manifest.json").read_text(encoding="utf-8"))
    ports = run_manifest.get("ports", {})
    frontend_port = ports.get("frontend", 3000)
    backend_port = ports.get("backend", 8000)
    health_urls = run_manifest.get("health_checks", [])

    results = {"frontend_running": False, "backend_running": False, "processes": []}

    # Try starting services
    start_cmds = run_manifest.get("start_commands", [])
    processes = []
    for cmd in start_cmds:
        try:
            proc = subprocess.Popen(cmd, cwd=str(app_dir), shell=True,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(proc)
            results["processes"].append({"command": cmd, "pid": proc.pid})
        except Exception as e:
            results["processes"].append({"command": cmd, "error": str(e)})

    # Wait for startup
    time_mod.sleep(5)

    # Health checks via httpx
    try:
        import httpx
        for url in health_urls:
            try:
                resp = httpx.get(url, timeout=5, follow_redirects=True)
                if resp.status_code < 500:
                    if "3000" in url or ":3000" in url:
                        results["frontend_running"] = True
                    if "8000" in url or ":8000" in url:
                        results["backend_running"] = True
            except Exception:
                pass
    except ImportError:
        pass

    # Cleanup
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass

    return results


def step6_capture_screenshots(task_dir: Path) -> list:
    """Capture screenshots using Playwright or stub."""
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    from app.services.capture import PlaywrightCapture
    import asyncio

    capture_manifest = json.loads((task_dir / "manifests" / "capture_manifest.json").read_text(encoding="utf-8"))
    app_manifest = json.loads((task_dir / "manifests" / "app_manifest.json").read_text(encoding="utf-8"))

    screenshots_dir = task_dir / "artifacts" / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    capture = PlaywrightCapture(
        base_url="http://127.0.0.1:3000",
        output_dir=str(screenshots_dir),
        headless=True,
    )

    async def run_capture():
        return await capture.capture_scenarios(capture_manifest, app_manifest.get("demo_accounts", []))

    results = asyncio.run(run_capture())

    screenshot_manifest = []
    for r in results:
        screenshot_manifest.append({
            "scenario_id": r.scenario_id,
            "page_title": r.page_title,
            "route": r.route,
            "image_file": str(r.image_path),
            "success": r.success,
            "caption": r.caption,
            "elements": r.elements,
            "error": r.error,
        })

    (task_dir / "artifacts" / "screenshot_manifest.json").write_text(
        json.dumps(screenshot_manifest, ensure_ascii=False, indent=2))

    return screenshot_manifest


def step7_generate_documents(task_dir: Path, product_name: str, version: str) -> dict:
    """Generate both Word documents."""
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

    from app.services.document.manual import SoftwareManualGenerator
    from app.services.document.codebook import SourceCodeBookGenerator
    from app.services.document.diagrams import generate_system_architecture_diagram

    screenshot_manifest = []
    sm_path = task_dir / "artifacts" / "screenshot_manifest.json"
    if sm_path.exists():
        screenshot_manifest = json.loads(sm_path.read_text(encoding="utf-8"))

    screenshots_meta = []
    for item in screenshot_manifest:
        screenshots_meta.append({
            "page_title": item.get("page_title", ""),
            "caption": item.get("caption", ""),
            "image_path": item.get("image_file", ""),
            "elements": item.get("elements", []),
            "steps": item.get("steps", []),
        })

    exports_dir = task_dir / "builds" / "build_001" / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    # Generate Software Manual
    manual_gen = SoftwareManualGenerator(product_name=product_name, version=version)
    arch_diagram_path = exports_dir / "system_architecture.png"
    generate_system_architecture_diagram(str(arch_diagram_path), product_name)
    manual_gen.generate_full(
        screenshots_meta=screenshots_meta,
        modules=["登录认证", "仪表盘/首页", "用户管理", "设备管理", "报表统计", "告警管理", "系统设置"],
        arch_diagram_path=str(arch_diagram_path),
    )
    manual_path = exports_dir / "software_manual.docx"
    manual_gen.save(str(manual_path))

    # Generate Source Code Book
    code_index = json.loads((task_dir / "manifests" / "code_index_manifest.json").read_text(encoding="utf-8"))
    app_dir = task_dir / "app"
    code_gen = SourceCodeBookGenerator(product_name=product_name, version=version)
    code_gen.generate(code_index, str(app_dir))
    code_path = exports_dir / "source_code_book.docx"
    code_gen.save(str(code_path))

    return {
        "manual": str(manual_path),
        "source_code": str(code_path),
        "manual_size": os.path.getsize(str(manual_path)),
        "source_code_size": os.path.getsize(str(code_path)),
    }


def run_full_pipeline(keyword: str = "智慧园区管理平台",
                      product_name: str = "智慧园区管理平台",
                      version: str = "V1.0") -> dict:
    """Run the complete IPRight pipeline end-to-end."""
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    report = {
        "pipeline_run": datetime.now().isoformat(),
        "task_id": task_id,
        "keyword": keyword,
        "product_name": product_name,
        "version": version,
        "stages": {},
    }

    log("PIPELINE START", f"task_id={task_id} keyword={keyword}")

    # Step 1: Setup workspace
    log("STEP 1", "Setting up workspace...")
    task_dir = step1_setup_workspace(task_id)
    report["stages"]["setup"] = "ok"

    # Step 2: Generate PRD
    log("STEP 2", "Generating PRD and work order...")
    prd_summary = step2_generate_prd(task_dir, keyword, product_name, version)
    report["stages"]["prd"] = {"ok": True, "modules": prd_summary.get("core_modules", [])}

    # Step 3: Copy demo app
    log("STEP 3", "Copying demo application...")
    step3_copy_demo_app(task_dir)
    report["stages"]["app_copy"] = "ok"

    # Step 4: Validate manifests
    log("STEP 4", "Validating manifests...")
    validation = step4_validate_manifests(task_dir)
    report["stages"]["validation"] = {"all_valid": validation["all_valid"]}

    # Step 5: Verify run
    log("STEP 5", "Verifying app startup...")
    try:
        runtime = step5_verify_run(task_dir / "app")
        report["stages"]["runtime"] = runtime
    except Exception as e:
        report["stages"]["runtime"] = {"error": str(e)}

    # Step 6: Capture screenshots
    log("STEP 6", "Capturing screenshots...")
    try:
        screenshots = step6_capture_screenshots(task_dir)
        report["stages"]["screenshots"] = {
            "count": len(screenshots),
            "success": sum(1 for s in screenshots if s.get("success")),
        }
    except Exception as e:
        report["stages"]["screenshots"] = {"error": str(e)}

    # Step 7: Generate documents
    log("STEP 7", "Generating Word documents...")
    try:
        docs = step7_generate_documents(task_dir, product_name, version)
        report["stages"]["documents"] = docs
    except Exception as e:
        report["stages"]["documents"] = {"error": str(e)}

    # Save report
    report_path = WORKSPACE_ROOT / "tasks" / task_id / "pipeline_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    log("PIPELINE COMPLETE", f"Report: {report_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("  IPRight E2E Pipeline Report")
    print("=" * 60)
    print(f"  Task ID:        {task_id}")
    print(f"  Product:        {product_name} {version}")
    print(f"  Workspace:      {task_dir}")
    print(f"  PRD:            {'✅' if report['stages'].get('prd', {}).get('ok') else '❌'}")
    print(f"  Manifests:      {'✅' if report['stages'].get('validation', {}).get('all_valid') else '❌'}")
    docs = report["stages"].get("documents", {})
    if docs.get("manual"):
        print(f"  Manual Word:    ✅ ({docs.get('manual_size', 0)} bytes)")
    else:
        print(f"  Manual Word:    ❌")
    if docs.get("source_code"):
        print(f"  Code Word:      ✅ ({docs.get('source_code_size', 0)} bytes)")
    else:
        print(f"  Code Word:      ❌")
    print("=" * 60)

    return report


if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "智慧园区管理平台"
    pn = sys.argv[2] if len(sys.argv) > 2 else kw
    ver = sys.argv[3] if len(sys.argv) > 3 else "V1.0"

    run_full_pipeline(keyword=kw, product_name=pn, version=ver)
