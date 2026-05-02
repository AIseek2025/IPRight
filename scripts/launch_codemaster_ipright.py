from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys


CODEMASTER_ROOT = Path("/Users/brando/Documents/trae_projects/CodeMaster")
WORKSPACE_ROOT = Path("/Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight")
PROMPT_FILE = WORKSPACE_ROOT / "docs" / "codemaster" / "prompts" / "phase0_ipright_autodev.md"


def main() -> int:
    sys.path.insert(0, str(CODEMASTER_ROOT))

    from smart_gateway import SmartGateway  # noqa: WPS433
    from src.execution import PlatformExecutionRegistry  # noqa: WPS433

    prompt = PROMPT_FILE.read_text(encoding="utf-8")

    gateway = SmartGateway()
    gateway.platform_execution_registry = PlatformExecutionRegistry(workspace_root=WORKSPACE_ROOT)
    gateway.execution_registry.workspace_root = WORKSPACE_ROOT
    gateway.gateway_entrypoint.execution_registry = gateway.platform_execution_registry
    gateway.gateway_entrypoint._explicit_workspace_root = WORKSPACE_ROOT
    gateway.gateway_entrypoint._allow_default_isolated_workspace = False
    gateway.gateway_entrypoint._isolated_workspace_artifacts = None
    gateway.codemaster_path = WORKSPACE_ROOT
    gateway._sync_platform_execution_registry()

    original_build_gateway_entry_plan = gateway._build_gateway_entry_plan

    def _build_gateway_entry_plan_without_governance(*args, **kwargs):
        plan = original_build_gateway_entry_plan(*args, **kwargs)
        return replace(plan, governance_decision=None)

    gateway._build_gateway_entry_plan = _build_gateway_entry_plan_without_governance

    print(f"[codemaster] workspace={WORKSPACE_ROOT}")
    print(f"[codemaster] prompt_file={PROMPT_FILE}")
    print("[codemaster] launching IPRight autonomous development...")
    response = gateway.process(prompt)
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
