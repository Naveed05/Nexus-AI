import sys

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
