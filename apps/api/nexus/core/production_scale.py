from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from nexus.core.scale import ScaleTopology


@dataclass(frozen=True)
class ScaleDeployment:
    mode: str
    region: str
    instance_id: str
    topology: ScaleTopology
    ready: bool
    blockers: tuple[str, ...]
    contract_version: str
    deployment_fingerprint: str


def build_scale_deployment(*, mode: str, region: str, instance_id: str, topology: ScaleTopology) -> ScaleDeployment:
    mode = mode.strip().lower()
    region = region.strip()
    instance_id = instance_id.strip()
    if mode not in {"single", "horizontal", "global"}:
        raise ValueError("deployment mode must be single, horizontal, or global")

    blockers = list(topology.blockers)
    if mode == "single":
        blockers = []
    else:
        if not topology.horizontal_scaling_ready:
            blockers.extend(topology.blockers)
        if not region:
            blockers.append("deployment region is required for distributed runtime")
        if not instance_id:
            blockers.append("instance identity is required for distributed runtime")

    blockers = list(dict.fromkeys(blockers))
    contract_version = "phase-35.v1"
    fingerprint_payload = {
        "contract_version": contract_version,
        "mode": mode,
        "region": region,
        "instance_id": instance_id,
        "state_backend": topology.state_backend,
        "queue_backend": topology.queue_backend,
        "cache_backend": topology.cache_backend,
        "object_storage_backend": topology.object_storage_backend,
    }
    canonical = json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    fingerprint = hashlib.sha256(canonical).hexdigest()
    return ScaleDeployment(
        mode, region, instance_id, topology, not blockers, tuple(blockers),
        contract_version, fingerprint,
    )


def deployment_payload(deployment: ScaleDeployment) -> dict[str, Any]:
    return {
        "mode": deployment.mode,
        "region": deployment.region,
        "instance_id": deployment.instance_id,
        "ready": deployment.ready,
        "blockers": list(deployment.blockers),
        "contract_version": deployment.contract_version,
        "deployment_fingerprint": deployment.deployment_fingerprint,
        "topology": {
            "state_backend": deployment.topology.state_backend,
            "queue_backend": deployment.topology.queue_backend,
            "cache_backend": deployment.topology.cache_backend,
            "object_storage_backend": deployment.topology.object_storage_backend,
            "horizontal_scaling_ready": deployment.topology.horizontal_scaling_ready,
        },
    }
