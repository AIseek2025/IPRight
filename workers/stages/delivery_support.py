from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

from sqlalchemy import select

from app.models.db import Artifact
from app.services.document.application_form import ApplicationFormGenerator
from app.services.document.codebook import SourceCodeBookGenerator
from app.services.document.diagrams import generate_system_architecture_diagram
from app.services.document.manual_compose import (
    build_variation_seed,
    render_manual_markdown_to_docx,
    validate_optional_manual_modules,
    validate_required_manual_modules,
)

logger = logging.getLogger(__name__)

_MANUAL_LLM_MAX_ATTEMPTS = 4


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
    prd_summary: dict,
    screenshots_meta: list[dict],
    exports_dir_fn: Callable[[str, str], str],
    create_artifact: Callable[..., Awaitable],
    merge_manual_llm_content: Callable[[dict, dict, list[dict]], dict],
    db_factory,
) -> tuple[str, str, int, str]:
    manual_llm_used = "deepseek-markdown"
    export_dir = exports_dir_fn(task_id, build_id)
    variation_seed = build_variation_seed(task_id, build_id, task.product_name, project_profile.get("design_seed", ""))
    project_profile = dict(project_profile or {})
    project_profile["variation_seed"] = variation_seed

    arch_diagram_path = os.path.join(export_dir, "system_architecture.png")
    diagram_spec: dict | None = None
    try:
        from app.services.llm import get_llm_client

        llm = get_llm_client()
        diagram_resp = await llm.generate_architecture_diagram_spec(
            product_name=task.product_name,
            profile=project_profile,
            task_id=task_id,
        )
        if diagram_resp.success and isinstance(diagram_resp.structured, dict):
            candidate = diagram_resp.structured.get("diagram_spec") or diagram_resp.structured
            if isinstance(candidate, dict) and candidate.get("nodes"):
                diagram_spec = candidate
                manual_llm_used = "deepseek-markdown+diagram"
    except Exception:
        logger.exception("Architecture diagram LLM spec generation failed for task %s", task_id)

    generate_system_architecture_diagram(
        arch_diagram_path,
        task.product_name,
        profile=project_profile,
        diagram_spec=diagram_spec,
    )

    manual_markdown = ""
    selected_optional_modules: list[str] = []
    last_missing_required: list[str] = []
    last_missing_optional: list[str] = []

    try:
        from app.services.llm import get_llm_client

        llm = get_llm_client()
        for attempt in range(1, _MANUAL_LLM_MAX_ATTEMPTS + 1):
            attempt_profile = {
                **project_profile,
                "variation_seed": build_variation_seed(variation_seed, str(attempt)),
                "manual_retry_attempt": attempt - 1,
            }
            markdown_resp = await llm.generate_manual_markdown(
                product_name=task.product_name,
                version=task.version,
                profile=attempt_profile,
                prd_summary=prd_summary,
                screenshots_meta=screenshots_meta,
                task_id=task_id,
            )
            if not markdown_resp.success or not isinstance(markdown_resp.structured, dict):
                logger.warning(
                    "Manual markdown LLM attempt %s failed for task %s: %s",
                    attempt,
                    task_id,
                    getattr(markdown_resp, "error", "unknown"),
                )
                continue

            candidate_markdown = str(markdown_resp.structured.get("manual_markdown", "")).strip()
            optional_modules = markdown_resp.structured.get("selected_optional_modules")
            candidate_optional: list[str] = []
            if isinstance(optional_modules, list):
                candidate_optional = [str(item).strip() for item in optional_modules if str(item).strip()]

            required_ok, missing_required = validate_required_manual_modules(candidate_markdown)
            optional_ok = True
            missing_optional: list[str] = []
            if len(candidate_optional) >= 4:
                optional_ok, missing_optional = validate_optional_manual_modules(
                    candidate_markdown, candidate_optional
                )

            last_missing_required = missing_required
            last_missing_optional = missing_optional

            if candidate_markdown and required_ok and optional_ok:
                manual_markdown = candidate_markdown
                selected_optional_modules = candidate_optional
                manual_llm_used = "deepseek-markdown" if attempt == 1 else f"deepseek-markdown-retry-{attempt}"
                break

            logger.warning(
                "Manual markdown validation failed on attempt %s for task %s: missing_required=%s missing_optional=%s",
                attempt,
                task_id,
                missing_required,
                missing_optional,
            )
    except Exception:
        logger.exception("Manual markdown LLM generation failed for task %s", task_id)

    if manual_markdown and selected_optional_modules:
        project_profile["selected_optional_modules"] = selected_optional_modules

    if not manual_markdown:
        detail_parts = []
        if last_missing_required:
            detail_parts.append("缺少必选章节: " + ", ".join(last_missing_required))
        if last_missing_optional:
            detail_parts.append("缺少选做章节: " + ", ".join(last_missing_optional))
        detail = "；".join(detail_parts) if detail_parts else "LLM 未返回可通过校验的说明书 Markdown"
        raise RuntimeError(
            f"软件说明书生成失败（已重试 {_MANUAL_LLM_MAX_ATTEMPTS} 次，禁止回退固定模板）: {detail}"
        )

    doc = render_manual_markdown_to_docx(
        markdown=manual_markdown,
        product_name=task.product_name,
        version=task.version,
        screenshots_meta=screenshots_meta,
        arch_diagram_path=arch_diagram_path,
        variation_seed=variation_seed,
    )
    output_path = os.path.join(export_dir, "software_manual.docx")
    doc.save(output_path)

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

    _warm_bundle_download(task_id)


def _warm_bundle_download(task_id: str) -> bool:
    api_token = os.getenv("IPRIGHT_API_TOKEN", "").strip()
    if not api_token:
        logger.warning("Skipping bundle warmup for task %s: missing IPRIGHT_API_TOKEN", task_id)
        return False

    request = urllib_request.Request(
        f"http://127.0.0.1:18000/api/v1/tasks/{task_id}/bundle/download",
        headers={"Authorization": f"Bearer {api_token}"},
    )
    try:
        with urllib_request.urlopen(request, timeout=120) as response:
            while response.read(1024 * 1024):
                pass
        return True
    except (urllib_error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("Bundle warmup failed for task %s: %s", task_id, exc)
        return False
