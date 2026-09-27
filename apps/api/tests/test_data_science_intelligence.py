from __future__ import annotations
from pathlib import Path
from nexus.core.data_science_intelligence import DataScienceIntelligence
from nexus.core.dataset_workspace import DatasetWorkspace

def _service(tmp_path: Path):
    workspace=DatasetWorkspace(tmp_path/"datasets")
    return workspace,DataScienceIntelligence(workspace,tmp_path/"analysis.sqlite3")

def test_profile_and_analysis_produce_evidence(tmp_path: Path):
    workspace,service=_service(tmp_path)
    dataset=workspace.register(b"age,income,segment\n20,100,A\n21,110,A\n22,120,B\n22,120,B\n23,,B\n",filename="customers.csv",file_format="csv")
    profile=service.profile(dataset.dataset_id)["result"]
    assert profile["rows"]==5 and profile["columns"]==3 and profile["duplicate_rows"]==1
    assert profile["quality"]["null_columns"][0]["column"]=="income"
    result=service.analyze(dataset.dataset_id,target="segment")["result"]
    assert result["problem"]["type"]=="classification"
    assert result["cleaned_shape"]["rows"]==4
    assert result["cleaning_applied"]

def test_baseline_ml_returns_held_out_metrics(tmp_path: Path):
    workspace,service=_service(tmp_path)
    dataset=workspace.register(b"age,income,churn\n20,100,0\n21,110,0\n22,120,0\n23,130,1\n24,140,1\n25,150,1\n26,160,1\n27,170,0\n28,180,0\n29,190,1\n",filename="churn.csv",file_format="csv")
    result=service.baseline(dataset.dataset_id,"churn")["result"]
    assert result["test_rows"]>0 and result["train_rows"]>result["test_rows"]
    assert result["metrics"] and result["model"] in {"logistic_regression","ridge_regression"}
