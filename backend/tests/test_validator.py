from __future__ import annotations

from app.services.validator import ManifestValidator


def test_validate_app_manifest_valid():
    v = ManifestValidator()
    manifest = {
        "product_name": "TestApp",
        "version": "V1.0",
        "app_type": "admin_web",
        "frontend_framework": "react_vite",
        "backend_framework": "fastapi",
        "entry_routes": ["/login", "/dashboard"],
        "demo_accounts": [{"username": "admin", "password": "admin123"}],
    }
    result = v.validate_app_manifest(manifest)
    assert result.valid
    assert len(result.errors) == 0


def test_validate_app_manifest_missing_field():
    v = ManifestValidator()
    manifest = {"product_name": "TestApp"}
    result = v.validate_app_manifest(manifest)
    assert not result.valid
    assert len(result.errors) > 0


def test_validate_app_manifest_no_demo_account():
    v = ManifestValidator()
    manifest = {
        "product_name": "TestApp",
        "version": "V1.0",
        "app_type": "admin_web",
        "frontend_framework": "react_vite",
        "backend_framework": "fastapi",
        "entry_routes": ["/login"],
        "demo_accounts": [],
    }
    result = v.validate_app_manifest(manifest)
    assert not result.valid


def test_validate_run_manifest_valid():
    v = ManifestValidator()
    manifest = {
        "install_commands": ["npm install"],
        "start_commands": ["npm run dev"],
        "health_checks": ["http://localhost:3000/"],
    }
    result = v.validate_run_manifest(manifest)
    assert result.valid


def test_validate_capture_manifest_missing_route():
    v = ManifestValidator()
    manifest = {
        "scenarios": [
            {"id": "s1", "title": "Test"},
        ],
    }
    result = v.validate_capture_manifest(manifest)
    assert not result.valid


def test_validate_code_index_warns_no_exclude():
    v = ManifestValidator()
    manifest = {
        "include_globs": ["src/**/*.ts"],
        "exclude_globs": [],
        "preferred_order": ["src/main.ts"],
    }
    result = v.validate_code_index_manifest(manifest)
    assert len(result.warnings) > 0


def test_validate_all():
    v = ManifestValidator()
    manifests = {
        "app_manifest": {"product_name": "A", "version": "V1", "app_type": "admin_web",
                         "frontend_framework": "react", "backend_framework": "fastapi",
                         "entry_routes": ["/"], "demo_accounts": [{"username": "u", "password": "p"}]},
        "run_manifest": {"install_commands": ["x"], "start_commands": ["y"], "health_checks": ["z"]},
        "capture_manifest": {"scenarios": [{"id": "a", "title": "t", "route": "/"}]},
        "code_index_manifest": {"include_globs": ["*.ts"], "exclude_globs": ["**/node_modules/**"], "preferred_order": []},
    }
    results = v.validate_all(manifests)
    assert v.is_all_valid(results)
