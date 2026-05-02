from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DEMO = ROOT / "examples" / "demo_app"
OUTPUT = ROOT / "tmp" / "final_docs_v2"
SCREENSHOTS = OUTPUT / "screenshots"

sys.path.insert(0, str(BACKEND))

from app.services.capture import PlaywrightCapture  # noqa: E402
from app.services.document.codebook import SourceCodeBookGenerator  # noqa: E402
from app.services.document.diagrams import generate_system_architecture_diagram  # noqa: E402
from app.services.document.manual import SoftwareManualGenerator  # noqa: E402


async def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    capture_manifest = json.loads((DEMO / "manifests" / "capture_manifest.json").read_text(encoding="utf-8"))
    app_manifest = json.loads((DEMO / "manifests" / "app_manifest.json").read_text(encoding="utf-8"))
    code_index = json.loads((DEMO / "manifests" / "code_index_manifest.json").read_text(encoding="utf-8"))

    capture = PlaywrightCapture(base_url="http://127.0.0.1:3003", output_dir=str(SCREENSHOTS))
    results = await capture.capture_scenarios(capture_manifest, app_manifest.get("demo_accounts", []))

    screenshots_meta: list[dict] = []
    for idx, result in enumerate(results, 1):
        if not result.success:
            continue
        screenshots_meta.append(
            {
                "page_title": result.page_title,
                "caption": f"图{idx} {result.page_title}",
                "image_path": result.image_path,
                "elements": result.elements,
                "steps": [],
            }
        )

    architecture_path = OUTPUT / "system_architecture.png"
    generate_system_architecture_diagram(str(architecture_path), app_manifest["product_name"])

    manual = SoftwareManualGenerator(product_name=app_manifest["product_name"], version=app_manifest["version"])
    manual.generate_full(
        screenshots_meta=screenshots_meta,
        modules=["登录认证", "仪表盘/首页", "用户管理", "设备管理", "报表统计", "告警管理", "系统设置"],
        arch_diagram_path=str(architecture_path),
    )
    manual_path = OUTPUT / "software_manual.docx"
    manual.save(str(manual_path))

    codebook = SourceCodeBookGenerator(product_name=app_manifest["product_name"], version=app_manifest["version"])
    codebook.generate(code_index, str(DEMO))
    codebook_path = OUTPUT / "source_code_book.docx"
    codebook.save(str(codebook_path))

    print(f"screenshots_ok={len(screenshots_meta)}")
    print(str(manual_path))
    print(str(codebook_path))
    print(f"manual_bytes={manual_path.stat().st_size}")
    print(f"codebook_bytes={codebook_path.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
