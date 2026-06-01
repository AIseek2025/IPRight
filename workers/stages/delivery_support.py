from __future__ import annotations

import json
import os
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select

from app.models.db import Artifact
from app.services.document.application_form import ApplicationFormGenerator
from app.services.document.codebook import SourceCodeBookGenerator
from app.services.document.diagrams import generate_system_architecture_diagram
from app.services.document.manual import SoftwareManualGenerator


def load_screenshots_meta(
    task_id: str,
    artifacts_dir_fn: Callable[[str], str],
    screenshots_dir_fn: Callable[[str], str],
    load_json_manifest: Callable[[str], dict | None],
) -> list[dict]:
    raw = load_json_manifest("screenshot_manifest")
    if not isinstance(raw, list):
        manifest_path = os.path.join(artifacts_dir_fn(task_id), "screenshot_manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            raw = loaded if isinstance(loaded, list) else []
        else:
            raw = []

    screenshots_meta = []
    for item in raw:
        image_file = item.get("image_file", "")
        screenshots_meta.append(
            {
                "page_title": item.get("page_title", ""),
                "caption": item.get("caption", ""),
                "route": item.get("route", ""),
                "elements": item.get("elements", []),
                "image_path": os.path.join(screenshots_dir_fn(task_id), image_file) if image_file else "",
                "steps": item.get("steps", []),
            }
        )
    return screenshots_meta


async def generate_manual_delivery(
    task,
    task_id: str,
    build_id: str,
    project_profile: dict,
    prd_content: str,
    prd_summary: dict,
    screenshots_meta: list[dict],
    exports_dir_fn: Callable[[str, str], str],
    create_artifact: Callable[..., Awaitable],
    merge_manual_llm_content: Callable[[dict, dict, list[dict]], dict],
    db_factory,
) -> tuple[str, str, int, str]:
    from app.services.llm import get_llm_client

    llm = get_llm_client()
    manual_llm_used = getattr(getattr(llm, "config", None), "doc_model", "llm_generated")
    manual_resp = await llm.generate_manual_content(
        product_name=task.product_name,
        version=task.version,
        profile=project_profile,
        prd_summary={**prd_summary, "prd_markdown": prd_content},
        screenshots_meta=screenshots_meta,
    )
    if not manual_resp.success or not manual_resp.structured:
        raise RuntimeError(f"manual llm generation failed: {manual_resp.error or 'empty manual response'}")

    page_overrides = manual_resp.structured.get("page_overrides") or []
    if screenshots_meta and not page_overrides:
        raise RuntimeError("manual llm generation failed: missing page_overrides for screenshots")

    project_profile = merge_manual_llm_content(
        project_profile,
        manual_resp.structured,
        screenshots_meta,
    )

    generator = SoftwareManualGenerator(
        product_name=task.product_name,
        version=task.version,
        profile=project_profile,
    )
    export_dir = exports_dir_fn(task_id, build_id)
    arch_diagram_path = generate_system_architecture_diagram(
        os.path.join(export_dir, "system_architecture.png"),
        task.product_name,
        profile=project_profile,
    )
    generator.generate_full(
        prd_summary=prd_summary,
        screenshots_meta=screenshots_meta,
        modules=[module.get("title", "") for module in project_profile.get("modules", [])],
        arch_diagram_path=arch_diagram_path,
    )

    output_path = os.path.join(export_dir, "software_manual.docx")
    generator.save(output_path)
    await create_artifact(
        db_factory,
        task_id,
        build_id,
        "software_manual_docx",
        "software_manual.docx",
        output_path,
    )

    application_form_path = os.path.join(export_dir, "application_form.docx")
    application_form = ApplicationFormGenerator(
        product_name=task.product_name,
        version=task.version,
    )
    application_form.generate(project_profile)
    application_form.save(application_form_path)
    await create_artifact(
        db_factory,
        task_id,
        build_id,
        "application_form_docx",
        "application_form.docx",
        application_form_path,
    )

    return output_path, application_form_path, len(screenshots_meta), manual_llm_used


async def generate_code_book_delivery(
    task,
    task_id: str,
    build_id: str,
    code_index: dict,
    workspace_root: str,
    exports_dir_fn: Callable[[str, str], str],
    create_artifact: Callable[..., Awaitable],
    db_factory,
) -> str:
    generator = SourceCodeBookGenerator(
        product_name=task.product_name,
        version=task.version,
    )

    export_dir = exports_dir_fn(task_id, build_id)
    output_path = os.path.join(export_dir, "source_code_book.docx")
    generator.generate(code_index, workspace_root)
    generator.save(output_path)

    await create_artifact(
        db_factory,
        task_id,
        build_id,
        "source_code_book_docx",
        "source_code_book.docx",
        output_path,
    )
    return output_path


async def publish_task_exports(task_id: str, build_id: str, db_factory) -> None:
    from app.models.db import Export

    async with db_factory()() as db:
        artifact_mapping: dict[tuple[str, str], uuid.UUID] = {}
        artifacts_q = await db.execute(
            select(Artifact).where(
                Artifact.task_id == uuid.UUID(task_id),
                Artifact.build_id == uuid.UUID(build_id),
            )
        )
        for artifact in artifacts_q.scalars().all():
            artifact_mapping[(artifact.artifact_type, artifact.artifact_name)] = artifact.id

        for export_type, filename in [
            ("manual_docx", "software_manual.docx"),
            ("source_code_docx", "source_code_book.docx"),
            ("application_form_docx", "application_form.docx"),
        ]:
            artifact_type = {
                "manual_docx": "software_manual_docx",
                "source_code_docx": "source_code_book_docx",
                "application_form_docx": "application_form_docx",
            }[export_type]
            new_export_id = uuid.uuid4()
            export = Export(
                id=new_export_id,
                task_id=uuid.UUID(task_id),
                build_id=uuid.UUID(build_id),
                export_type=export_type,
                artifact_id=artifact_mapping.get((artifact_type, filename)),
                file_name=filename,
                download_url=f"/api/v1/exports/{new_export_id}/download",
                status="ready",
            )
            db.add(export)

        bundle_export = Export(
            task_id=uuid.UUID(task_id),
            build_id=uuid.UUID(build_id),
            export_type="bundle_zip",
            file_name="full_delivery_bundle.zip",
            download_url=f"/api/v1/tasks/{task_id}/bundle/download",
            status="ready",
        )
        db.add(bundle_export)
        await db.commit()
