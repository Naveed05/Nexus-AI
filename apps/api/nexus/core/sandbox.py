from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import tempfile


@dataclass(frozen=True)
class SandboxResult:
    stdout: str
    stderr: str
    return_code: int
    timed_out: bool
    workspace: str


class PythonSandbox:
    """Constrained prototype runner for Python jobs.

    This is deliberately not exposed as a NEXUS tool yet. Production execution
    will move to an isolated container/worker with stronger CPU, memory,
    filesystem, network, and process controls.
    """

    def __init__(self, timeout_seconds: int = 10) -> None:
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least 1")
        self.timeout_seconds = timeout_seconds

    def run(self, code: str) -> SandboxResult:
        if not code.strip():
            raise ValueError("Python code cannot be empty")

        with tempfile.TemporaryDirectory(prefix="nexus-job-") as workspace:
            workspace_path = Path(workspace)
            script_path = workspace_path / "main.py"
            script_path.write_text(code, encoding="utf-8")

            env = {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONIOENCODING": "utf-8",
            }

            try:
                completed = subprocess.run(
                    [sys.executable, "-I", str(script_path)],
                    cwd=workspace,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                return SandboxResult(
                    stdout=exc.stdout or "",
                    stderr=exc.stderr or "Execution timed out.",
                    return_code=-1,
                    timed_out=True,
                    workspace=workspace,
                )

            return SandboxResult(
                stdout=completed.stdout,
                stderr=completed.stderr,
                return_code=completed.returncode,
                timed_out=False,
                workspace=workspace,
            )
