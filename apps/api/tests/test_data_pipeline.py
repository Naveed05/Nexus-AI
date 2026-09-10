import polars as pl
import pytest

from nexus.core.data_pipeline import DataPipeline


def test_cleaning_plan_is_evidence_driven() -> None:
    frame = pl.DataFrame({"age": [20, None, 20], "city": ["Pune", "Pune", "Pune"]})
    plan = DataPipeline().cleaning_plan(frame)
    assert {item["action"] for item in plan} == {"remove_duplicates", "impute_missing", "review_constant_column"}
    assert any(item.get("strategy") == "median" for item in plan)


def test_clean_applies_conservative_fixes() -> None:
    frame = pl.DataFrame({"age": [20, None, 20], "city": ["Pune", "Pune", "Pune"]})
    cleaned, changes = DataPipeline().clean(frame)
    assert cleaned.height == 2
    assert cleaned.get_column("age").null_count() == 0
    assert any(item["action"] == "remove_duplicates" for item in changes)
    assert any(item["action"] == "impute_missing" for item in changes)


def test_eda_returns_numeric_and_categorical_statistics() -> None:
    frame = pl.DataFrame({"age": [20, 30, 40], "city": ["Pune", "Pune", "Mumbai"]})
    eda = DataPipeline().eda(frame)
    assert eda["numeric"]["age"]["mean"] == pytest.approx(30.0)
    assert eda["categorical"]["city"]["unique_count"] == 2
    assert eda["categorical"]["city"]["top_values"][0]["city"] == "Pune"


def test_analyze_combines_profile_cleaning_and_eda() -> None:
    frame = pl.DataFrame({"score": [10, None, 10]})
    result = DataPipeline().analyze(frame)
    assert "profile" in result
    assert "cleaning_plan" in result
    assert "cleaning_applied" in result
    assert "eda" in result
