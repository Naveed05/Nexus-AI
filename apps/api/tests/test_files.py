from io import BytesIO
from uuid import uuid4

import pytest

from nexus.core.files import FileNotFoundError, FileRegistry, LocalFileStore


def test_store_and_read_workspace_file(tmp_path):
    workspace_id = uuid4()
    store = LocalFileStore(tmp_path)

    file = store.put(
        BytesIO(b"hello nexus"),
        filename="../notes.txt",
        workspace_id=workspace_id,
        mime_type="text/plain",
    )

    assert file.filename == "notes.txt"
    assert file.workspace_id == workspace_id
    assert file.size_bytes == 11
    assert store.exists(file)
    assert store.get(file) == b"hello nexus"
    assert (tmp_path / str(workspace_id)).is_dir()


def test_store_rejects_path_traversal_key(tmp_path):
    store = LocalFileStore(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        store._safe_path("../../outside.txt")


def test_registry_scopes_files_to_workspace(tmp_path):
    registry = FileRegistry()
    workspace_a = uuid4()
    workspace_b = uuid4()
    store = LocalFileStore(tmp_path)
    file_a = registry.register(
        store.put(b"a", filename="a.txt", workspace_id=workspace_a)
    )
    file_b = registry.register(
        store.put(b"b", filename="b.txt", workspace_id=workspace_b)
    )

    assert registry.get(file_a.file_id, workspace_id=workspace_a) == file_a
    assert registry.list(workspace_id=workspace_a) == (file_a,)
    with pytest.raises(FileNotFoundError):
        registry.get(file_a.file_id, workspace_id=workspace_b)
    assert [file.file_id for file in registry.list()] == [file_a.file_id, file_b.file_id]


def test_registry_remove(tmp_path):
    registry = FileRegistry()
    workspace_id = uuid4()
    file = registry.register(
        LocalFileStore(tmp_path).put(b"data", filename="data.bin", workspace_id=workspace_id)
    )

    assert registry.remove(file.file_id, workspace_id=workspace_id) == file
    with pytest.raises(FileNotFoundError):
        registry.get(file.file_id)
