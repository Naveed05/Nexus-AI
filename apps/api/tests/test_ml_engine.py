import polars as pl
import pytest

from nexus.core.ml_engine import MLEngine


def test_detect_problem_refuses_to_guess_target() -> None:
    frame = pl.DataFrame({"age": [20, 30, 40], "income": [10, 20, 30]})
    result = MLEngine().detect_problem(frame)
    assert result["problem_type"] == "descriptive"
    assert result["target"] is None


def test_detect_problem_identifies_classification() -> None:
    frame = pl.DataFrame({"age": [20, 30, 40, 50], "segment": ["A", "B", "A", "B"]})
    result = MLEngine().detect_problem(frame, "segment")
    assert result["problem_type"] == "classification"


def test_detect_problem_identifies_regression() -> None:
    frame = pl.DataFrame({"x": [1, 2, 3, 4, 5, 6], "target": [10, 20, 30, 40, 50, 60]})
    result = MLEngine().detect_problem(frame, "target")
    assert result["problem_type"] == "regression"


def test_baseline_returns_evaluation_metrics() -> None:
    frame = pl.DataFrame({"x": list(range(1, 21)), "target": [2 * x + 1 for x in range(1, 21)]})
    result = MLEngine().baseline(frame, "target")
    assert result["model"] == "ridge_regression"
    assert set(result["metrics"]) == {"mae", "rmse", "r2"}
    assert result["test_rows"] == 4
    assert result["metrics"]["r2"] == pytest.approx(1.0, abs=0.1)
