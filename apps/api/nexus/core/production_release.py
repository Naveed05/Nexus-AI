"""Production 1.0 release and readiness contracts for NEXUS.

This module keeps release identity deterministic and makes production
configuration failures explicit before traffic is accepted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from pathlib import Path
from typing import Any


_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class ReleaseConfigurationError(ValueError):
    """Raised when a deployment cannot satisfy the production release contract."""


@dataclass(frozen=True)
class ReleaseManifest:
    release_id: str
    version: str
    environment: str
    deployment_mode: str
    region: str
    instance_id: str
    state_backend: str
    queue_backend: str
    cache_backend: str
    object_storage_backend: str
    configuration_valid: bool
    configuration_issues: tuple[str, ...]


def _configuration_issues(settings: Any, *, require_production: bool = False) -> list[str]:
    issues: list[str] = []
    version = str(getattr(settings, "service_version", "")).strip()
    environment = str(getattr(settings, "environment", "")).strip().lower()
    mode = str(getattr(settings, "deployment_mode", "")).strip().lower()

    if not _VERSION_RE.fullmatch(version):
        issues.append("service_version must use semantic version format")
    if not environment:
        issues.append("environment is required")
    if not mode:
        issues.append("deployment_mode is required")

    production = require_production or environment == "production"
    if production:
        if not str(getattr(settings, "beta_access_key", "") or "").strip():
            issues.append("beta_access_key is required for production")
        if not str(getattr(settings, "deployment_region", "")).strip():
            issues.append("deployment_region is required for production")
        if not str(getattr(settings, "instance_id", "")).strip():
            issues.append("instance_id is required for production")

    for name in (
        "state_backend",
        "queue_backend",
        "cache_backend",
        "object_storage_backend",
    ):
        if not str(getattr(settings, name, "")).strip():
            issues.append(f"{name} is required")

    for name in (
        "dataset_storage_path",
        "file_storage_path",
        "knowledge_index_path",
        "run_storage_path",
        "artifact_storage_path",
        "artifact_registry_path",
        "job_storage_path",
        "workflow_storage_path",
        "collaboration_audit_storage_path",
    ):
        value = str(getattr(settings, name, "")).strip()
        if not value:
            issues.append(f"{name} is required")
        else:
            path = Path(value)
            parent = path.parent
            if parent.exists() and not parent.is_dir():
                issues.append(f"{name} parent must be a directory")

    return issues


def validate_release_configuration(settings: Any, *, require_production: bool = False) -> None:
    issues = _configuration_issues(settings, require_production=require_production)
    if issues:
        raise ReleaseConfigurationError("; ".join(issues))


def _fingerprint_payload(settings: Any) -> dict[str, str]:
    return {
        "version": str(getattr(settings, "service_version", "")),
        "environment": str(getattr(settings, "environment", "")),
        "deployment_mode": str(getattr(settings, "deployment_mode", "")),
        "region": str(getattr(settings, "deployment_region", "")),
        "instance_id": str(getattr(settings, "instance_id", "")),
        "state_backend": str(getattr(settings, "state_backend", "")),
        "queue_backend": str(getattr(settings, "queue_backend", "")),
        "cache_backend": str(getattr(settings, "cache_backend", "")),
        "object_storage_backend": str(getattr(settings, "object_storage_backend", "")),
    }


def build_release_manifest(settings: Any, *, require_production: bool = False) -> ReleaseManifest:
    issues = _configuration_issues(settings, require_production=require_production)
    payload = _fingerprint_payload(settings)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    fingerprint = hashlib.sha256(encoded).hexdigest()[:16]
    return ReleaseManifest(
        release_id=f"{payload['version']}+{fingerprint}",
        version=payload["version"],
        environment=payload["environment"],
        deployment_mode=payload["deployment_mode"],
        region=payload["region"],
        instance_id=payload["instance_id"],
        state_backend=payload["state_backend"],
        queue_backend=payload["queue_backend"],
        cache_backend=payload["cache_backend"],
        object_storage_backend=payload["object_storage_backend"],
        configuration_valid=not issues,
        configuration_issues=tuple(issues),
    )


def release_payload(manifest: ReleaseManifest) -> dict[str, Any]:
    payload = asdict(manifest)
    payload["configuration_issues"] = list(manifest.configuration_issues)
    return payload


def readiness_payload(
    *,
    manifest: ReleaseManifest,
    runtime_ready: bool,
    frontend_ready: bool,
    scale_ready: bool,
    runtime: dict[str, Any] | None = None,
    scale: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks = {
        "runtime": bool(runtime_ready),
        "frontend": bool(frontend_ready),
        "scale_contract": bool(scale_ready),
        "release_configuration": manifest.configuration_valid,
    }
    return {
        "status": "ready" if all(checks.values()) else "not_ready",
        "service": "nexus-api",
        "release": release_payload(manifest),
        "checks": checks,
        "runtime": runtime or {},
        "scale": scale or {},
    }
