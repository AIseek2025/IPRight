#!/usr/bin/env python3
"""
IPRight Full Demo Runner
========================
Starts the demo app, captures screenshots, generates Word documents.
Proves the complete IPRight chain works end-to-end with a real running app.
"""

import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_APP = PROJECT_ROOT / "examples" / "demo_app"


def log(msg: str) -> None:
    print(f"\033[36m[{time.strftime('%H:%M:%S')}]\033[0m {msg}")


class DemoRunner:
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or PROJECT_ROOT / "tmp" / "demo_output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir = self.output_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.frontend_proc = None
        self.backend_proc = None
        self.task_id = uuid.uuid4().hex[:8]

    def _tail_log(self, path: Path, *, lines: int = 20) -> str:
        if not path.exists():
            return "(log file missing)"
        content = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(content[-lines:]) if content else "(log file empty)"

    def _ensure_frontend_dependencies(self) -> None:
        frontend_dir = DEMO_APP / "frontend"
        node_modules = frontend_dir / "node_modules"
        if node_modules.exists():
            return

        log("Installing demo frontend dependencies (npm ci)...")
        subprocess.run(
            ["npm", "ci"],
            cwd=str(frontend_dir),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def start_services(self) -> bool:
        log("Starting demo app services...")
        backend_log = self.log_dir / "demo_backend.log"
        frontend_log = self.log_dir / "demo_frontend.log"
        backend_log.write_text("", encoding="utf-8")
        frontend_log.write_text("", encoding="utf-8")

        try:
            backend_path = DEMO_APP / "backend"
            log(f"Starting backend (uvicorn)...")
            backend_fp = backend_log.open("w", encoding="utf-8")
            self.backend_proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"],
                cwd=str(backend_path),
                stdout=backend_fp,
                stderr=subprocess.STDOUT,
            )
            log(f"  Backend PID: {self.backend_proc.pid}")
        except Exception as e:
            log(f"  Backend start failed: {e}")
            return False

        time.sleep(2)

        try:
            self._ensure_frontend_dependencies()
            frontend_path = DEMO_APP / "frontend"
            log("Building demo frontend...")
            subprocess.run(
                ["npm", "run", "build"],
                cwd=str(frontend_path),
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log("Starting frontend (Vite preview)...")
            frontend_fp = frontend_log.open("w", encoding="utf-8")
            self.frontend_proc = subprocess.Popen(
                ["npx", "vite", "preview", "--host", "127.0.0.1", "--port", "3001", "--strictPort"],
                cwd=str(frontend_path),
                stdout=frontend_fp,
                stderr=subprocess.STDOUT,
            )
            log(f"  Frontend PID: {self.frontend_proc.pid}")
        except Exception as e:
            log(f"  Frontend start failed: {e}")
            self.stop_services()
            return False

        log("Waiting for services to be ready...")
        return self._wait_for_health()

    def _wait_for_health(self, timeout: int = 20) -> bool:
        import httpx
        start = time.time()
        backend_ok = frontend_ok = False

        while time.time() - start < timeout:
            try:
                resp = httpx.get("http://127.0.0.1:8001/health", timeout=2)
                if resp.status_code == 200:
                    if not backend_ok:
                        log(f"  Backend healthy: {resp.json()}")
                    backend_ok = True
            except Exception:
                pass

            try:
                resp = httpx.get("http://127.0.0.1:3001/", timeout=2, follow_redirects=True)
                if resp.status_code < 500:
                    frontend_ok = True
            except Exception:
                pass

            if backend_ok and frontend_ok:
                log("  All services healthy!")
                return True
            time.sleep(1)

        log(f"  Health check timeout. Backend: {backend_ok}, Frontend: {frontend_ok}")
        log("  Backend log tail:")
        log(self._tail_log(self.log_dir / "demo_backend.log"))
        log("  Frontend log tail:")
        log(self._tail_log(self.log_dir / "demo_frontend.log"))
        return backend_ok

    def capture_screenshots(self) -> list[dict]:
        log("Capturing screenshots...")
        sys.path.insert(0, str(PROJECT_ROOT / "backend"))
        from app.services.capture import PlaywrightCapture

        screenshots_dir = self.output_dir / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        app_manifest_path = DEMO_APP / "manifests" / "app_manifest.json"
        capture_manifest_path = DEMO_APP / "manifests" / "capture_manifest.json"

        app_manifest = json.loads(app_manifest_path.read_text(encoding="utf-8"))
        capture_manifest = json.loads(capture_manifest_path.read_text(encoding="utf-8"))

        capture = PlaywrightCapture(
            base_url="http://127.0.0.1:3001",
            output_dir=str(screenshots_dir),
            headless=True,
        )

        results = asyncio.run(capture.capture_scenarios(
            capture_manifest, app_manifest.get("demo_accounts", [])
        ))

        manifest_data = []
        for r in results:
            status = "✅" if r.success else "❌"
            log(f"  {status} {r.scenario_id}: {r.page_title} ({r.route})")
            if not r.success and r.error:
                log(f"       Error: {r.error}")

            manifest_data.append({
                "scenario_id": r.scenario_id,
                "page_title": r.page_title,
                "route": r.route,
                "image_file": str(r.image_path),
                "success": r.success,
                "caption": r.caption,
                "elements": r.elements,
            })

        manifest_path = self.output_dir / "screenshot_manifest.json"
        manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2))

        return manifest_data

    def generate_documents(self, screenshot_manifest: list[dict]) -> dict:
        log("Generating Word documents...")
        sys.path.insert(0, str(PROJECT_ROOT / "backend"))

        from app.services.document.manual import SoftwareManualGenerator
        from app.services.document.codebook import SourceCodeBookGenerator
        from app.services.document.diagrams import generate_system_architecture_diagram

        app_manifest = json.loads((DEMO_APP / "manifests" / "app_manifest.json").read_text(encoding="utf-8"))
        code_index = json.loads((DEMO_APP / "manifests" / "code_index_manifest.json").read_text(encoding="utf-8"))

        product_name = app_manifest["product_name"]
        version = app_manifest["version"]

        screenshots_meta = []
        for item in screenshot_manifest:
            if item.get("success"):
                screenshots_meta.append({
                    "page_title": item.get("page_title", ""),
                    "caption": item.get("caption", ""),
                    "image_path": item.get("image_file", ""),
                    "elements": item.get("elements", []),
                    "steps": item.get("steps", []),
                })

        docs_dir = self.output_dir / "exports"
        docs_dir.mkdir(parents=True, exist_ok=True)

        manual_path = docs_dir / "software_manual.docx"
        arch_diagram_path = docs_dir / "system_architecture.png"
        generate_system_architecture_diagram(str(arch_diagram_path), product_name)
        manual_gen = SoftwareManualGenerator(product_name=product_name, version=version)
        manual_gen.generate_full(
            screenshots_meta=screenshots_meta,
            modules=["登录认证", "仪表盘/首页", "用户管理", "设备管理", "报表统计", "告警管理", "系统设置"],
            arch_diagram_path=str(arch_diagram_path),
        )
        manual_gen.save(str(manual_path))
        manual_size = manual_path.stat().st_size
        log(f"  ✅ Software Manual: {manual_size} bytes - {manual_path}")

        code_path = docs_dir / "source_code_book.docx"
        code_gen = SourceCodeBookGenerator(product_name=product_name, version=version)
        code_gen.generate(code_index, str(DEMO_APP))
        code_gen.save(str(code_path))
        code_size = code_path.stat().st_size
        log(f"  ✅ Source Code Book: {code_size} bytes - {code_path}")

        return {
            "manual_path": str(manual_path),
            "manual_size": manual_size,
            "code_path": str(code_path),
            "code_size": code_size,
        }

    def stop_services(self) -> None:
        log("Stopping services...")
        for proc in [self.frontend_proc, self.backend_proc]:
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    def run(self) -> dict:
        log("=" * 60)
        log("  IPRight Full Demo Runner")
        log(f"  Task ID: {self.task_id}")
        log("=" * 60)

        report = {"task_id": self.task_id, "stages": {}}

        if not self.start_services():
            log("Failed to start services. Aborting.")
            report["stages"]["services"] = "failed"
            return report
        report["stages"]["services"] = "ok"

        screenshots = self.capture_screenshots()
        report["stages"]["screenshots"] = {
            "total": len(screenshots),
            "success": sum(1 for s in screenshots if s.get("success")),
        }

        docs = self.generate_documents(screenshots)
        report["stages"]["documents"] = docs

        self.stop_services()

        log("=" * 60)
        log("  Demo Complete!")
        log(f"  Screenshots: {report['stages']['screenshots']['success']}/{report['stages']['screenshots']['total']}")
        log(f"  Manual Word: {docs.get('manual_size', 0)} bytes")
        log(f"  Code Word:   {docs.get('code_size', 0)} bytes")
        log(f"  Output dir:  {self.output_dir}")
        log("=" * 60)

        report_path = self.output_dir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

        return report


if __name__ == "__main__":
    runner = DemoRunner()
    runner.run()
