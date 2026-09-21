from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AutonomyCapability:
    name: str
    allowed: bool
    requires_approval: bool
    reason: str


@dataclass(frozen=True)
class AutonomyPolicyMatrix:
    capabilities: tuple[AutonomyCapability, ...]

    def can(self, name: str) -> bool:
        return any(item.name == name and item.allowed and not item.requires_approval for item in self.capabilities)

    def approval_required(self, name: str) -> bool:
        return any(item.name == name and item.requires_approval for item in self.capabilities)


def default_autonomy_policy() -> AutonomyPolicyMatrix:
    return AutonomyPolicyMatrix((
        AutonomyCapability("plan", True, False, "planning is reversible"),
        AutonomyCapability("inspect", True, False, "inspection is read-only"),
        AutonomyCapability("revise", True, False, "revision is bounded by runtime budget"),
        AutonomyCapability("execute_tool", True, False, "execution remains behind tool security"),
        AutonomyCapability("external_side_effect", False, True, "side effects require explicit approval"),
        AutonomyCapability("change_policy", False, True, "policy changes are never self-authorized"),
    ))
