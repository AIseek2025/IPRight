from __future__ import annotations

import argparse
import os
import zipfile

from app.services.document.diagrams import (
    _resolve_cjk_font_path,
    generate_system_architecture_diagram,
)
from app.services.document.manual import SoftwareManualGenerator
from workers.stages.delivery_support import load_screenshots_meta
from workers.stages.handlers import (
    _load_manifest,
    _load_prd_summary,
    artifacts_dir,
    screenshots_dir,
)


def regenerate_manual(task_id: str, build_id: str) -> None:
    export_dir = os.path.join(
        "/opt/ipright/shared/workspace/tasks",
        task_id,
        "builds",
        build_id,
        "exports",
    )
    output_path = os.path.join(export_dir, "software_manual.docx")
    arch_path = os.path.join(export_dir, "system_architecture.png")

    project_profile = _load_manifest(task_id, "project_profile") or {}
    prd_summary = _load_prd_summary(task_id)
    product_name = project_profile.get("product_name") or project_profile.get("topic_label") or "IPRight"
    version = project_profile.get("version") or "V1.0"
    screenshots_meta = load_screenshots_meta(
        task_id,
        artifacts_dir,
        screenshots_dir,
        lambda name: _load_manifest(task_id, name),
    )

    print("font_path", _resolve_cjk_font_path())
    print("product_name", product_name)
    print("version", version)
    print("screenshots_meta", len(screenshots_meta))
    for item in screenshots_meta[:5]:
        image_path = item.get("image_path", "")
        print(item.get("page_title"), os.path.basename(image_path), os.path.exists(image_path))

    os.makedirs(export_dir, exist_ok=True)
    generated_arch_path = generate_system_architecture_diagram(arch_path, product_name, profile=project_profile)

    generator = SoftwareManualGenerator(
        product_name=product_name,
        version=version,
        profile=project_profile,
    )
    generator.generate_full(
        prd_summary=prd_summary,
        screenshots_meta=screenshots_meta,
        modules=[module.get("title", "") for module in project_profile.get("modules", [])],
        arch_diagram_path=generated_arch_path,
    )
    generator.save(output_path)

    with zipfile.ZipFile(output_path) as handle:
        media = [name for name in handle.namelist() if name.startswith("word/media/")]
    print("media_count", len(media))
    print("output", output_path, os.path.getsize(output_path))


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate a task's software manual from existing artifacts.")
    parser.add_argument("task_id")
    parser.add_argument("build_id")
    args = parser.parse_args()
    regenerate_manual(args.task_id, args.build_id)


if __name__ == "__main__":
    main()
