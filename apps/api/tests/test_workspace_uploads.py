from nexus.api.main import client, dataset_workspace, file_registry, file_store, workspace_registry


def test_workspace_csv_upload_registers_dataset_and_surfaces_it():
    workspace = workspace_registry.create(name="CSV upload test")
    try:
        response = client.post(
            f"/api/v1/workspaces/{workspace.workspace_id}/files",
            headers={"X-User-Id": "csv-upload-test"},
            files={"file": ("sample.csv", b"name,value\na,10\nb,20\n", "text/csv")},
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["dataset_ready"] is True
        assert payload["dataset_id"]
        assert payload["metadata"]["dataset_id"] == payload["dataset_id"]

        listed = client.get(f"/api/v1/workspaces/{workspace.workspace_id}/files").json()
        assert listed[0]["filename"] == "sample.csv"
        assert listed[0]["dataset_id"] == payload["dataset_id"]
        assert str(payload["dataset_id"]) in {
            str(dataset.dataset_id) for dataset in workspace_registry.context(workspace.workspace_id).dataset_ids
        }
    finally:
        for file_ref in list(file_registry.list(workspace_id=workspace.workspace_id)):
            file_store.delete(file_ref)
            file_registry.remove(file_ref.file_id, workspace_id=workspace.workspace_id)
        for dataset_id in list(workspace_registry.context(workspace.workspace_id).dataset_ids):
            dataset_workspace.registry.remove(dataset_id)
        workspace_registry.remove(workspace.workspace_id)
