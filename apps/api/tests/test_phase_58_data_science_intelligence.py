from pathlib import Path

from nexus.core.data_science_intelligence import DataScienceIntelligence
from nexus.core.dataset_workspace import DatasetWorkspace


def test_data_science_profile_analysis_and_history_are_durable(tmp_path: Path) -> None:
    datasets = DatasetWorkspace(tmp_path / "data")
    dataset = datasets.register(b"name,score\na,10\nb,20\nc,30\nd,40\ne,50\n", filename="scores.csv", file_format="csv")
    service = DataScienceIntelligence(datasets, tmp_path / "data_science.sqlite3")

    profile = service.profile(dataset.dataset_id)
    analysis = service.analyze(dataset.dataset_id)
    history = service.history(dataset.dataset_id)

    assert profile["analysis_type"] == "profile"
    assert profile["result"]["rows"] == 5
    assert analysis["analysis_type"] == "analysis"
    assert analysis["result"]["cleaned_shape"]["rows"] == 5
    assert len(history) == 2


def test_data_science_baseline_uses_registered_dataset(tmp_path: Path) -> None:
    datasets = DatasetWorkspace(tmp_path / "data")
    dataset = datasets.register(
        b"age,score\n20,1\n21,2\n22,3\n23,4\n24,5\n25,6\n26,7\n27,8\n28,9\n29,10\n",
        filename="scores.csv",
        file_format="csv",
    )
    service = DataScienceIntelligence(datasets, tmp_path / "data_science.sqlite3")
    result = service.baseline(dataset.dataset_id, "score")
    assert result["analysis_type"] == "baseline_ml"
    assert result["result"]["problem"]["target"] == "score"
    assert result["result"]["test_rows"] > 0
