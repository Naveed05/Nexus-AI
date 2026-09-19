import sys

import pytest

from nexus.core.sandbox import PythonSandbox


def test_python_sandbox_captures_output() -> None:
    result = PythonSandbox().run("print(2 + 3)")

    assert result.timed_out is False
    assert result.return_code == 0
    assert result.stdout.strip() == "5"


def test_python_sandbox_reports_failures() -> None:
    result = PythonSandbox().run("raise ValueError('boom')")

    assert result.timed_out is False
    assert result.return_code != 0
    assert "ValueError" in result.stderr


def test_python_sandbox_times_out() -> None:
    result = PythonSandbox(timeout_seconds=1).run(
        f"import time; time.sleep(10)"
    )

    assert result.timed_out is True
    assert result.return_code == -1


def test_python_sandbox_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError, match="max_output_bytes"):
        PythonSandbox(max_output_bytes=0)

    with pytest.raises(ValueError, match="max_file_bytes"):
        PythonSandbox(max_file_bytes=0)

    with pytest.raises(ValueError, match="max_cpu_seconds"):
        PythonSandbox(max_cpu_seconds=0)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX resource limits are not available")
def test_python_sandbox_applies_posix_process_limits() -> None:
    result = PythonSandbox(timeout_seconds=2, max_cpu_seconds=1, max_file_bytes=1024).run(
        "from pathlib import Path; Path('x').write_bytes(b'a' * 2048)"
    )

    assert result.return_code != 0
    assert result.timed_out is False
