from pathlib import Path

import pytest

from nexus.core.code_index import CodebaseIndexer


def test_codebase_indexer_builds_metadata_and_searches(tmp_path: Path):
    (tmp_path / "app.py").write_text("from helper import greet\nprint(greet())\n", encoding="utf-8")
    (tmp_path / "helper.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=value\n", encoding="utf-8")

    indexer = CodebaseIndexer(tmp_path)
    files = indexer.build()

    assert [file.path for file in files] == ["app.py", "helper.py"]
    assert indexer.search("greet")[0].file.path == "app.py"
    assert indexer.summary()["file_count"] == 2


def test_codebase_indexer_resolves_python_dependencies(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "from helpers import greet\nfrom .service import run\n", encoding="utf-8"
    )
    (tmp_path / "helpers.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("def run():\n    return True\n", encoding="utf-8")

    indexer = CodebaseIndexer(tmp_path)
    indexer.build()

    assert {(edge.source, edge.target, edge.kind) for edge in indexer.dependencies()} == {
        ("app.py", "helpers.py", "import"),
        ("app.py", "service.py", "import"),
    }
    assert indexer.summary()["dependency_count"] == 2


def test_codebase_indexer_rejects_non_directory(tmp_path: Path):
    file_path = tmp_path / "file.py"
    file_path.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        CodebaseIndexer(file_path)
