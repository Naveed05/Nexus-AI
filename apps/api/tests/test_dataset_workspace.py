from uuid import uuid4

import pytest

from nexus.core.dataset_workspace import DatasetNotFoundError, DatasetWorkspace
from nexus.core.tools import (
    analyze_dataset_by_id,
    configure_dataset_workspace,
    profile_dataset_by_id,
)


CSV = b"name,value,score\na,10,1\nb,20,2\nc,30,3\n"


def test_workspace_registers_and_resolves_dataset(tmp_path):
    workspace = DatasetWorkspace(tmp_path)
    dataset = workspace.register(CSV, filename="sample.csv", file_format="csv")

    assert dataset.artifact_id is not None
    assert workspace.get(dataset.dataset_id) == dataset
    assert workspace.read_bytes(dataset.dataset_id) == CSV
    assert workspace.load(dataset.dataset_id).height == 3


def test_workspace_rejects_unknown_dataset(tmp_path):
    workspace = DatasetWorkspace(tmp_path)
    with pytest.raises(DatasetNotFoundError):
        workspace.get(uuid4())
    with pytest.raises(DatasetNotFoundError):
        workspace.load(uuid4())


def test_reference_tools_execute_against_registered_dataset(tmp_path):
    workspace = DatasetWorkspace(tmp_path)
    dataset = workspace.register(CSV, filename="sample.csv", file_format="csv")
    configure_dataset_workspace(workspace)

    profile = profile_dataset_by_id(str(dataset.dataset_id))
    analysis = analyze_dataset_by_id(str(dataset.dataset_id), target="score")

    assert profile["profile"]["rows"] == 3
    assert profile["profile"]["columns"] == 3
    assert analysis["rows"] == 3

    configure_dataset_workspace(None)


def test_reference_tools_fail_without_workspace():
    configure_dataset_workspace(None)
    with pytest.raises(RuntimeError, match="not configured"):
        profile_dataset_by_id(str(uuid4()))


def test_reference_tools_reject_invalid_or_unknown_ids(tmp_path):
    configure_dataset_workspace(DatasetWorkspace(tmp_path))
    with pytest.raises(ValueError, match="Invalid or unknown dataset_id"):
        profile_dataset_by_id("not-a-uuid")
    with pytest.raises(ValueError, match="Invalid or unknown dataset_id"):
        analyze_dataset_by_id(str(uuid4()))
    configure_dataset_workspace(None)
