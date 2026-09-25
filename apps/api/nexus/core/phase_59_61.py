from __future__ import annotations

from typing import Any
from uuid import UUID

from .collaboration_audit import CollaborationAuditLog
from .collaboration_runtime import CollaborationRuntime
from .distributed_execution import DistributedExecutionBridge
from .governance import GovernanceStore


class PhaseControlPlane:
    """Small integration facade for the three new production control planes."""

    def __init__(self, collaboration: CollaborationRuntime, distributed: DistributedExecutionBridge, governance: GovernanceStore, audit: CollaborationAuditLog) -> None:
        self.collaboration = collaboration
        self.distributed = distributed
        self.governance = governance
        self.audit = audit

    def status(self) -> dict[str, Any]:
        return {
            "collaboration_audit": self.audit.stats(),
            "governance": {"ready": True},
            "distributed_workers": self.distributed.workers.metrics(),
        }

    def worker_claim(self, worker_id: UUID) -> dict[str, Any] | None:
        lease = self.distributed.claim_next(worker_id)
        return lease.payload() if lease else None
