from __future__ import annotations

from dataclasses import dataclass
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
    return ScaleDeployment(mode, region, instance_id, topology, not blockers, tuple(blockers))


def deployment_payload(deployment: ScaleDeployment) -> dict[str, Any]:
    return {
        "mode": deployment.mode,
        "region": deployment.region,
        "instance_id": deployment.instance_id,
        "ready": deployment.ready,
        "blockers": list(deployment.blockers),
        "topology": {
            "state_backend": deployment.topology.state_backend,
            "queue_backend": deployment.topology.queue_backend,
            "cache_backend": deployment.topology.cache_backend,
            "object_storage_backend": deployment.topology.object_storage_backend,
            "horizontal_scaling_ready": deployment.topology.horizontal_scaling_ready,
        },
    }
