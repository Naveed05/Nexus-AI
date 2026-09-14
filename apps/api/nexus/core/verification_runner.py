from __future__ import annotations

from dataclasses import dataclass
import shlex
import subprocess
from pathlib import Path


@dataclass(frozen=True)
class VerificationRun:
    """Bounded local pytest execution result suitable for developer evidence."""

    command: str
    status: str
    exit_code: int | None
    output: str
    timed_out: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "output": self.output,
            "timed_out": self.timed_out,
        }


class VerificationRunner:
    """Execute only generated pytest commands inside a bounded repository root."""

    _PREFIX = ("PYTHONPATH=.", "pytest", "-q")
    _MAX_OUTPUT = 20_000

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"verification root is not a directory: {self.root}")

    def run(self, command: str, *, timeout_seconds: int = 120) -> VerificationRun:
        """Run a narrow pytest command without a shell and with bounded output."""
        if not command.strip():
            raise ValueError("command must not be empty")
        if timeout_seconds < 1 or timeout_seconds > 600:
            raise ValueError("timeout_seconds must be between 1 and 600")
        parts = shlex.split(command)
        if len(parts) < 3 or tuple(parts[:3]) != self._PREFIX:
            raise ValueError("only generated PYTHONPATH=. pytest -q commands are allowed")
        if any(part in {"--shell", "--exec", "-c"} for part in parts[3:]):
            raise ValueError("shell execution flags are not allowed")

        try:
            completed = subprocess.run(
                parts,
                cwd=self.root,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            return VerificationRun(
                command=command.strip(),
                status="timeout",
                exit_code=None,
                output=output[-self._MAX_OUTPUT :],
                timed_out=True,
            )

        output = (completed.stdout or "") + (completed.stderr or "")
        return VerificationRun(
            command=command.strip(),
            status="passed" if completed.returncode == 0 else "failed",
            exit_code=completed.returncode,
            output=output[-self._MAX_OUTPUT :],
            timed_out=False,
        )
