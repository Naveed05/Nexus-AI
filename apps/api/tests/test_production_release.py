from types import SimpleNamespace

import pytest

from nexus.core.production_release import (
    ReleaseConfigurationError,
    build_release_manifest,
    readiness_payload,
    release_payload,
    validate_release_configuration,
)


def settings(**overrides):
    values = {
        "service_version": "1.0.0",
        "environment": "development",
        "deployment_mode": "single",
        "deployment_region": "",
        "instance_id": "",
        "beta_access_key": None,
        "state_backend": "sqlite",
        "queue_backend": "sqlite",
        "cache_backend": "memory",
        "object_storage_backend": "filesystem",
        "dataset_storage_path": ".nexus/data",
        "file_storage_path": ".nexus/files",
        "knowledge_index_path": ".nexus/knowledge/index.json",
        "run_storage_path": ".nexus/runs.sqlite3",
        "artifact_storage_path": ".nexus/artifacts",
        "artifact_registry_path": ".nexus/artifacts.sqlite3",
        "job_storage_path": ".nexus/jobs.sqlite3",
        "workflow_storage_path": ".nexus/workflows.sqlite3",
        "collaboration_audit_storage_path": ".nexus/collaboration_audit.sqlite3",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_release_fingerprint_is_deterministic():
    first = build_release_manifest(settings())
    second = build_release_manifest(settings())
    assert first.release_id == second.release_id
    assert len(first.release_id.rsplit("+", 1)[1]) == 16


def test_identity_changes_when_instance_changes():
    assert build_release_manifest(settings(instance_id="a")).release_id != build_release_manifest(settings(instance_id="b")).release_id


def test_production_configuration_requires_identity_and_access_key():
    manifest = build_release_manifest(settings(environment="production"), require_production=True)
    assert not manifest.configuration_valid
    assert "beta_access_key is required for production" in manifest.configuration_issues
    with pytest.raises(ReleaseConfigurationError):
        validate_release_configuration(settings(environment="production"), require_production=True)


def test_production_configuration_passes_when_complete():
    validate_release_configuration(
        settings(
            environment="production",
            deployment_region="ap-south-1",
            instance_id="nexus-01",
            beta_access_key="configured",
        ),
        require_production=True,
    )


def test_invalid_version_is_rejected():
    manifest = build_release_manifest(settings(service_version="latest"))
    assert manifest.configuration_valid is False
    assert "service_version must use semantic version format" in manifest.configuration_issues


def test_readiness_combines_release_and_runtime_checks():
    manifest = build_release_manifest(settings())
    payload = readiness_payload(
        manifest=manifest,
        runtime_ready=True,
        frontend_ready=True,
        scale_ready=True,
        runtime={"status": "ready"},
        scale={"ready": True},
    )
    assert payload["status"] == "ready"
    assert payload["checks"]["release_configuration"] is True
    assert release_payload(manifest)["release_id"] == manifest.release_id


def test_readiness_fails_when_scale_is_blocked():
    manifest = build_release_manifest(settings())
    payload = readiness_payload(
        manifest=manifest,
        runtime_ready=True,
        frontend_ready=True,
        scale_ready=False,
    )
    assert payload["status"] == "not_ready"
