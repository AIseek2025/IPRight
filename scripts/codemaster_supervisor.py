from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE_ROOT = Path("/Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight")
DOCS_ROOT = WORKSPACE_ROOT / "docs"
CODEMASTER_DOCS_ROOT = DOCS_ROOT / "codemaster"
PROMPTS_ROOT = CODEMASTER_DOCS_ROOT / "prompts"
BASE_PROMPT = PROMPTS_ROOT / "phase1_ipright_10h_autopilot.md"
CURRENT_PROMPT = PROMPTS_ROOT / "current_supervised_autopilot.md"
STATUS_JSON = CODEMASTER_DOCS_ROOT / "autopilot_status.json"
STATUS_MD = DOCS_ROOT / "STATUS_REPORT.md"
WORK_SUMMARY_MD = DOCS_ROOT / "WORK_SUMMARY_PHASE1.md"
HANDOFF_MD = CODEMASTER_DOCS_ROOT / "04_current_cycle_handoff.md"
CAPSULE_MD = CODEMASTER_DOCS_ROOT / "05_current_cycle_capsule.md"
REQUESTS_ROOT = WORKSPACE_ROOT / ".codemaster_orchestration" / "opencode" / "requests"
SUPERVISOR_LOG = CODEMASTER_DOCS_ROOT / "supervisor_runs.jsonl"
LAUNCHER = WORKSPACE_ROOT / "scripts" / "launch_codemaster_ipright_long_autopilot.py"
EXECUTOR = WORKSPACE_ROOT / "scripts" / "run_pending_opencode_request.py"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run IPRight CodeMaster unattended supervisor.")
    parser.add_argument("--max-hours", type=float, default=10.0)
    parser.add_argument("--max-iterations", type=int, default=100)
    parser.add_argument("--cooldown-seconds", type=int, default=5)
    parser.add_argument("--continue-if-remaining", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _latest_request_path(before: set[Path] | None = None) -> Path:
    candidates = sorted(REQUESTS_ROOT.glob("opencode_session_request_*.json"))
    if before:
        candidates = [path for path in candidates if path not in before]
    if not candidates:
        raise RuntimeError("No new opencode session request was generated.")
    return candidates[-1]


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def _extract_markdown_bullets(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    capture = False
    items: list[str] = []
    target = heading.strip()
    for raw in lines:
        line = raw.rstrip()
        if line.startswith("#"):
            normalized = line.lstrip("#").strip()
            capture = normalized == target
            continue
        if not capture:
            continue
        stripped = line.strip()
        if stripped.startswith(("## ", "### ", "# ")):
            break
        if stripped.startswith(("- ", "* ", "1. ", "2. ", "3. ", "4. ", "5. ")):
            items.append(stripped)
    return items


def _fallback_status_payload() -> dict[str, object]:
    status_text = _read_text(STATUS_MD)
    handoff_text = _read_text(HANDOFF_MD)
    remaining = _extract_markdown_bullets(status_text, "下一阶段目标")
    if not remaining:
        remaining = _extract_markdown_bullets(handoff_text, "未完成项")
    blockers = _extract_markdown_bullets(status_text, "当前阻塞")
    hard_blocker = any("硬阻塞" in item and "无硬阻塞" not in item for item in blockers)
    summary = ""
    for line in status_text.splitlines():
        if line.startswith("## 当前阶段"):
            continue
        if line.strip().startswith("Phase "):
            summary = line.strip()
            break
    return {
        "status": "in_progress",
        "project_completed": False,
        "hard_blocker": hard_blocker,
        "summary": summary or "未读取到结构化总结，按未完成处理",
        "completed_items": [],
        "remaining_items": remaining,
        "hard_blockers": blockers,
        "next_priority": remaining[:3],
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "fallback_markdown",
    }


def _load_status_payload() -> dict[str, object]:
    if STATUS_JSON.exists():
        try:
            payload = json.loads(STATUS_JSON.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            return payload
    return _fallback_status_payload()


def _has_remaining_items(status_payload: dict[str, object]) -> bool:
    remaining = status_payload.get("remaining_items")
    if not isinstance(remaining, list):
        return False
    return any(str(item).strip() for item in remaining)


def _write_prompt(iteration: int, status_payload: dict[str, object], elapsed_seconds: float, deadline_seconds: float) -> Path:
    base = _read_text(BASE_PROMPT)
    remaining = status_payload.get("remaining_items") or []
    blockers = status_payload.get("hard_blockers") or []
    next_priority = status_payload.get("next_priority") or []
    summary = str(status_payload.get("summary") or "").strip()
    prompt = textwrap.dedent(
        f"""
        {base}

        ## 九、Supervisor Continuation Context

        - 当前 supervisor iteration: {iteration}
        - 已运行秒数: {int(elapsed_seconds)}
        - 本轮总预算秒数: {int(deadline_seconds)}
        - 当前结构化状态文件: `docs/codemaster/autopilot_status.json`
        - 当前状态摘要: {summary or "暂无摘要，按未完成继续推进"}

        ### 当前必须优先回读的最新工件
        - `docs/STATUS_REPORT.md`
        - `docs/WORK_SUMMARY_PHASE1.md`
        - `docs/codemaster/04_current_cycle_handoff.md`
        - `docs/codemaster/05_current_cycle_capsule.md`
        - `docs/codemaster/autopilot_status.json`（若不存在，请本轮创建）

        ### 当前待完成项
        {chr(10).join(f"- {item}" for item in remaining[:8]) if remaining else "- 若未显式完成，请继续推进项目主链，不要停"}

        ### 当前下一优先级
        {chr(10).join(f"- {item}" for item in next_priority[:5]) if next_priority else "- 继续打通真实运行、截图、Word 导出与下载主链"}

        ### 当前硬阻塞
        {chr(10).join(f"- {item}" for item in blockers[:5]) if blockers else "- 无硬阻塞，继续开发"}

        ## 十、结构化状态文件要求

        本轮结束前，必须更新 `docs/codemaster/autopilot_status.json`，格式至少包含：
        ```json
        {{
          "status": "in_progress|completed|hard_blocked",
          "project_completed": false,
          "hard_blocker": false,
          "summary": "一句话总结当前进展",
          "completed_items": ["本轮完成项"],
          "remaining_items": ["剩余未完成项"],
          "hard_blockers": ["硬阻塞，如无则空数组"],
          "next_priority": ["下一轮首要事项"],
          "last_updated": "ISO8601"
        }}
        ```

        如果项目没有完成，就必须把 `status` 写成 `in_progress` 并明确列出 `remaining_items`，不要把未完成项目误写为完成。

        ## 十一、停止规则

        - 只有当 `project_completed=true` 时，才允许视为项目完成
        - 只有当存在真实不可自动修复的硬阻塞时，才允许写 `hard_blocked`
        - 如果既未完成也无硬阻塞，就继续开发，不要停
        """
    ).strip() + "\n"
    CURRENT_PROMPT.write_text(prompt, encoding="utf-8")
    return CURRENT_PROMPT


def _append_supervisor_log(payload: dict[str, object]) -> None:
    SUPERVISOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SUPERVISOR_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(cmd: list[str], *, dry_run: bool = False) -> int:
    print(f"[supervisor] run: {' '.join(cmd)}")
    if dry_run:
        return 0
    completed = subprocess.run(cmd, cwd=str(WORKSPACE_ROOT), check=False)
    return int(completed.returncode)


def main() -> int:
    args = _parse_args()
    started = time.time()
    deadline_seconds = int(args.max_hours * 3600)
    last_status = _load_status_payload()
    continue_if_remaining = args.continue_if_remaining or os.environ.get("IPRIGHT_CONTINUE_IF_REMAINING", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    for iteration in range(1, args.max_iterations + 1):
        elapsed = time.time() - started
        if elapsed >= deadline_seconds:
            print("[supervisor] time budget reached, stopping.")
            return 0

        completed = bool(last_status.get("project_completed")) or str(last_status.get("status") or "").strip() == "completed"
        has_remaining = _has_remaining_items(last_status)
        if completed:
            if continue_if_remaining and has_remaining:
                print("[supervisor] project marked completed but remaining items exist; continuing.")
            else:
                print("[supervisor] project already marked completed, stopping.")
                return 0
        if bool(last_status.get("hard_blocker")) or str(last_status.get("status") or "").strip() == "hard_blocked":
            print("[supervisor] hard blocker detected, stopping.")
            return 1

        prompt_path = _write_prompt(iteration, last_status, elapsed, deadline_seconds)
        before_requests = set(REQUESTS_ROOT.glob("opencode_session_request_*.json"))
        launch_code = _run(
            ["python3", str(LAUNCHER), str(prompt_path)],
            dry_run=args.dry_run,
        )
        if launch_code != 0:
            raise RuntimeError(f"launcher failed with exit code {launch_code}")
        if args.dry_run:
            _append_supervisor_log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "iteration": iteration,
                    "request_path": None,
                    "project_completed": bool(last_status.get("project_completed")),
                    "hard_blocker": bool(last_status.get("hard_blocker")),
                    "status": str(last_status.get("status") or "unknown"),
                    "summary": str(last_status.get("summary") or ""),
                    "mode": "dry_run",
                }
            )
            continue

        request_path = _latest_request_path(before_requests)
        execute_code = _run(
            ["python3", str(EXECUTOR), str(request_path)],
            dry_run=args.dry_run,
        )
        if execute_code != 0:
            print(f"[supervisor] executor returned non-zero exit code: {execute_code}")

        time.sleep(args.cooldown_seconds)
        last_status = _load_status_payload()
        _append_supervisor_log(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "iteration": iteration,
                "request_path": str(request_path),
                "project_completed": bool(last_status.get("project_completed")),
                "hard_blocker": bool(last_status.get("hard_blocker")),
                "status": str(last_status.get("status") or "unknown"),
                "summary": str(last_status.get("summary") or ""),
            }
        )

    print("[supervisor] max iterations reached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
