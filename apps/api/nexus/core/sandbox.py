from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import ast


@dataclass(frozen=True)
class SandboxResult:
    stdout: str
    stderr: str
    return_code: int
    timed_out: bool
    workspace: str


class PythonSandbox:
    """Constrained prototype runner for Python jobs.

    The runner applies OS resource limits where the host supports them and
    launches Python in isolated mode with a minimal environment. Production
    deployments should still use a dedicated container/worker boundary.
    """

    def __init__(
        self,
        timeout_seconds: int = 10,
        *,
        max_output_bytes: int = 1_048_576,
        max_cpu_seconds: int | None = None,
        max_file_bytes: int = 10_485_760,
        allow_network: bool = False,
        max_files: int = 128,
    ) -> None:
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least 1")
        if max_output_bytes < 1:
            raise ValueError("max_output_bytes must be at least 1")
        if max_file_bytes < 1:
            raise ValueError("max_file_bytes must be at least 1")
        if max_cpu_seconds is not None and max_cpu_seconds < 1:
            raise ValueError("max_cpu_seconds must be at least 1")
        if max_files < 1:
            raise ValueError("max_files must be at least 1")
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.max_cpu_seconds = max_cpu_seconds or timeout_seconds
        self.max_file_bytes = max_file_bytes
        self.allow_network = allow_network
        self.max_files = max_files

    def _preexec_limits(self):
        if os.name != "posix":
            return None

        import resource

        cpu_limit = self.max_cpu_seconds
        file_limit = self.max_file_bytes
        output_limit = self.max_output_bytes

        def apply_limits() -> None:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
            resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
            # Keep the child from inheriting an unexpectedly large stdout/stderr
            # pipe allowance through the OS file-size boundary where supported.
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        return apply_limits

    def _validate_code(self, code: str) -> None:
        if self.allow_network:
            return
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return
        blocked = {
            "socket", "ssl", "urllib", "http", "http.client",
            "ftplib", "telnetlib", "smtplib", "imaplib", "poplib",
            "requests", "httpx", "aiohttp",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name == module or name.startswith(module + ".") for name in names for module in blocked):
                raise ValueError("network access is disabled in the Python sandbox")

    def run(self, code: str) -> SandboxResult:
        if not code.strip():
            raise ValueError("Python code cannot be empty")
        self._validate_code(code)

        with tempfile.TemporaryDirectory(prefix="nexus-job-") as workspace:
            workspace_path = Path(workspace)
            script_path = workspace_path / "main.py"
            script_path.write_text(code, encoding="utf-8")

            env = {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
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
                    start_new_session=(os.name == "posix"),
                    preexec_fn=self._preexec_limits(),
                )
            except subprocess.TimeoutExpired as exc:
                return SandboxResult(
                    stdout=(exc.stdout or "")[: self.max_output_bytes],
                    stderr=(exc.stderr or "")[: self.max_output_bytes],
                    return_code=-1,
                    timed_out=True,
                    workspace=workspace,
                )

            file_count = sum(1 for path in workspace_path.rglob("*") if path.is_file())
            if file_count > self.max_files:
                return SandboxResult(
                    stdout=completed.stdout[: self.max_output_bytes],
                    stderr=(completed.stderr + f"\nsandbox file limit exceeded: {file_count} > {self.max_files}")[: self.max_output_bytes],
                    return_code=1,
                    timed_out=False,
                    workspace=workspace,
                )

            stdout = completed.stdout[: self.max_output_bytes]
            stderr = completed.stderr[: self.max_output_bytes]
            return SandboxResult(
                stdout=stdout,
                stderr=stderr,
                return_code=completed.returncode,
                timed_out=False,
                workspace=workspace,
            )
