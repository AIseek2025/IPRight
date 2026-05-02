from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0


class ManifestValidator:
    """Validates generated app manifests against IPRight App Contract."""

    REQUIRED_APP_FIELDS = {
        "product_name": str,
        "version": str,
        "app_type": str,
        "frontend_framework": str,
        "backend_framework": str,
        "entry_routes": list,
        "demo_accounts": list,
    }

    REQUIRED_RUN_FIELDS = {
        "install_commands": list,
        "start_commands": list,
        "health_checks": list,
    }

    REQUIRED_CAPTURE_FIELDS = {
        "scenarios": list,
    }

    REQUIRED_CODE_INDEX_FIELDS = {
        "include_globs": list,
        "exclude_globs": list,
        "preferred_order": list,
    }

    def validate_app_manifest(self, manifest: dict) -> ValidationResult:
        result = ValidationResult()
        self._check_required(manifest, self.REQUIRED_APP_FIELDS, "app_manifest", result)

        entry_routes = manifest.get("entry_routes", [])
        if not entry_routes:
            result.errors.append("app_manifest: entry_routes must not be empty")

        demo_accounts = manifest.get("demo_accounts", [])
        if not demo_accounts:
            result.errors.append("app_manifest: must provide at least one demo_account")
        for acc in demo_accounts:
            if not acc.get("username") or not acc.get("password"):
                result.errors.append("app_manifest: each demo_account must have username and password")

        return result

    def validate_run_manifest(self, manifest: dict) -> ValidationResult:
        result = ValidationResult()
        self._check_required(manifest, self.REQUIRED_RUN_FIELDS, "run_manifest", result)

        for cmd in manifest.get("install_commands", []):
            if "&&" in cmd and len(cmd) > 500:
                result.warnings.append(f"run_manifest: long install command may fail: {cmd[:60]}...")

        if not manifest.get("health_checks"):
            result.errors.append("run_manifest: health_checks must not be empty")

        return result

    def validate_capture_manifest(self, manifest: dict) -> ValidationResult:
        result = ValidationResult()
        self._check_required(manifest, self.REQUIRED_CAPTURE_FIELDS, "capture_manifest", result)

        scenarios = manifest.get("scenarios", [])
        if not scenarios:
            result.errors.append("capture_manifest: must have at least one scenario")

        for i, scenario in enumerate(scenarios):
            if not scenario.get("id"):
                result.errors.append(f"capture_manifest: scenario[{i}] missing id")
            if not scenario.get("title"):
                result.errors.append(f"capture_manifest: scenario[{i}] missing title")
            if not scenario.get("route"):
                result.errors.append(f"capture_manifest: scenario[{i}] missing route")

        return result

    def validate_code_index_manifest(self, manifest: dict) -> ValidationResult:
        result = ValidationResult()
        self._check_required(manifest, self.REQUIRED_CODE_INDEX_FIELDS, "code_index_manifest", result)

        if not manifest.get("include_globs"):
            result.errors.append("code_index_manifest: include_globs must not be empty")

        exclude = manifest.get("exclude_globs", [])
        has_node_modules = any("node_modules" in g for g in exclude)
        has_dist = any("dist" in g for g in exclude) or any(".next" in g for g in exclude)
        if not has_node_modules:
            result.warnings.append("code_index_manifest: should exclude **/node_modules/**")
        if not has_dist:
            result.warnings.append("code_index_manifest: should exclude dist/build directories")

        return result

    def validate_all(self, manifests: dict[str, dict]) -> dict[str, ValidationResult]:
        results = {}
        if "app_manifest" in manifests:
            results["app_manifest"] = self.validate_app_manifest(manifests["app_manifest"])
        if "run_manifest" in manifests:
            results["run_manifest"] = self.validate_run_manifest(manifests["run_manifest"])
        if "capture_manifest" in manifests:
            results["capture_manifest"] = self.validate_capture_manifest(manifests["capture_manifest"])
        if "code_index_manifest" in manifests:
            results["code_index_manifest"] = self.validate_code_index_manifest(manifests["code_index_manifest"])
        return results

    def _check_required(self, manifest: dict, fields: dict, name: str, result: ValidationResult) -> None:
        for field, expected_type in fields.items():
            if field not in manifest:
                result.errors.append(f"{name}: missing required field '{field}'")
            elif not isinstance(manifest[field], expected_type):
                result.errors.append(
                    f"{name}: field '{field}' expected {expected_type.__name__}, got {type(manifest[field]).__name__}"
                )

    def is_all_valid(self, results: dict[str, ValidationResult]) -> bool:
        return all(r.valid for r in results.values())
