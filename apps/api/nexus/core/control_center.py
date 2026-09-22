from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_control_center_summary(
    *,
    deployment: dict[str, Any],
    runtime: dict[str, Any],
    agents: list[dict[str, Any]],
    audit: dict[str, Any],
    models: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    active_runs = [run for run in runs if run.get("status") in {"created", "running"}]
    failed_runs = [run for run in runs if run.get("status") == "failed"]
    completed_runs = [run for run in runs if run.get("status") == "completed"]

    return {
        "generated_at": now,
        "overall_status": "healthy" if deployment.get("ready") and audit.get("valid", False) else "degraded",
        "deployment": deployment,
        "runtime": runtime,
        "agents": {
            "count": len(agents),
            "items": agents,
        },
        "audit": audit,
        "models": {
            "count": len(models),
            "available": sum(1 for model in models if model.get("health", {}).get("available")),
            "items": models,
        },
        "tools": {
            "count": len(tools),
            "items": tools,
        },
        "runs": {
            "total": len(runs),
            "active": len(active_runs),
            "completed": len(completed_runs),
            "failed": len(failed_runs),
            "recent": list(reversed(runs[-12:])),
        },
    }
