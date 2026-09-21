from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScaleTopology:
    state_backend: str
    queue_backend: str
    cache_backend: str
    object_storage_backend: str
    horizontal_scaling_ready: bool
    blockers: tuple[str, ...]


def build_scale_topology(*, state_backend: str, queue_backend: str, cache_backend: str,
                         object_storage_backend: str) -> ScaleTopology:
    blockers: list[str] = []
    if state_backend == "sqlite":
        blockers.append("shared transactional state is required for multiple API instances")
    if queue_backend == "sqlite":
        blockers.append("shared distributed queue is required for multiple workers")
    if cache_backend == "memory":
        blockers.append("shared cache is required for cross-instance coordination")
    if object_storage_backend == "filesystem":
        blockers.append("shared object storage is required for durable multi-instance artifacts")
    return ScaleTopology(
        state_backend, queue_backend, cache_backend, object_storage_backend,
        not blockers, tuple(blockers),
    )


def topology_payload(topology: ScaleTopology) -> dict[str, Any]:
    return {
        "state_backend": topology.state_backend,
        "queue_backend": topology.queue_backend,
        "cache_backend": topology.cache_backend,
        "object_storage_backend": topology.object_storage_backend,
        "horizontal_scaling_ready": topology.horizontal_scaling_ready,
        "blockers": list(topology.blockers),
    }
