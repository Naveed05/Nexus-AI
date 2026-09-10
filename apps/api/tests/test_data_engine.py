import polars as pl
import pytest

from nexus.core.data_engine import DataIntelligenceEngine


def test_profile_detects_shape_nulls_duplicates_and_uniques() -> None:
    frame = pl.DataFrame(
        {
            "name": ["A", "B", "B"],
            "score": [10, None, 10],
        }
    )

    profile = DataIntelligenceEngine().profile(frame)

    assert profile.rows == 3
    assert profile.columns == 2
    assert profile.duplicate_rows == 0
    score = next(column for column in profile.column_profiles if column.name == "score")
    assert score.null_count == 1
    assert score.null_ratio == pytest.approx(1 / 3)


def test_quality_report_flags_missing_and_constant_columns() -> None:
    frame = pl.DataFrame(
        {
            "constant": ["x", "x", "x"],
            "value": [1, None, 3],
        }
    )

    report = DataIntelligenceEngine().quality_report(frame)

    assert report["duplicate_rows"] == 0
    assert report["constant_columns"] == ["constant"]
    assert report["quality_flags"]["has_missing_values"] is True
    assert report["quality_flags"]["has_constant_columns"] is True


def test_load_csv_bytes() -> None:
    frame = DataIntelligenceEngine().load_bytes(b"a,b\n1,2\n3,4\n", "csv")

    assert frame.shape == (2, 2)
    assert frame.columns == ["a", "b"]


def test_load_rejects_unsupported_format() -> None:
    with pytest.raises(ValueError, match="Unsupported format"):
        DataIntelligenceEngine().load_bytes(b"hello", "xlsx")
