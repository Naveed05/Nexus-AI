from uuid import UUID

from nexus.api.main import client, workspace_registry


def test_document_ingestion_indexes_chunks_and_scopes_search() -> None:
    workspace = workspace_registry.create(name="Knowledge")
    other = workspace_registry.create(name="Other")

    upload = client.post(
        f"/api/v1/workspaces/{workspace.workspace_id}/documents",
        files={"file": ("guide.md", b"NEXUS supports verified agent workflows.\n\nRetrieval keeps knowledge scoped to a workspace.", "text/markdown")},
    )
    assert upload.status_code == 201
    body = upload.json()
    document_id = UUID(body["document_id"])
    assert body["file_format"] == "md"
    assert body["chunk_count"] >= 1
    assert document_id in workspace_registry.context(workspace.workspace_id).document_ids

    results = client.post(
        f"/api/v1/workspaces/{workspace.workspace_id}/search",
        json={"query": "workspace retrieval knowledge", "top_k": 3},
    )
    assert results.status_code == 200
    assert results.json()
    assert results.json()[0]["document_id"] == str(document_id)

    isolated = client.post(
        f"/api/v1/workspaces/{other.workspace_id}/search",
        json={"query": "workspace retrieval knowledge", "top_k": 3},
    )
    assert isolated.status_code == 200
    assert isolated.json() == []


def test_document_endpoint_rejects_unsupported_format() -> None:
    workspace = workspace_registry.create(name="Docs")
    response = client.post(
        f"/api/v1/workspaces/{workspace.workspace_id}/documents",
        files={"file": ("manual.pdf", b"not a pdf parser yet", "application/pdf")},
    )
    assert response.status_code == 415
