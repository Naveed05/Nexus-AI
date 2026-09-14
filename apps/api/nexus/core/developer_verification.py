from __future__ import annotations

from .developer_agent import DeveloperAgent, DeveloperVerificationPlan, DeveloperVerificationResult
from .verification_runner import VerificationRunner


class DeveloperVerificationService:
    """Execute a previously generated developer verification plan safely."""

    def __init__(self, agent: DeveloperAgent, runner: VerificationRunner) -> None:
        self.agent = agent
        self.runner = runner

    def run(
        self,
        plan: DeveloperVerificationPlan,
        *,
        focused: bool = True,
        timeout_seconds: int = 120,
    ) -> DeveloperVerificationResult:
        """Run one approved plan command and normalize it into developer evidence."""
        command = plan.focused_command if focused else plan.full_command
        try:
            result = self.runner.run(command, timeout_seconds=timeout_seconds)
        except ValueError as exc:
            return self.agent.verification_result(
                command,
                exit_code=2,
                output=str(exc),
            )
        return self.agent.verification_result(
            result.command,
            exit_code=result.exit_code,
            output=result.output,
        )
