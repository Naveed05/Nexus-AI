from pathlib import Path

from nexus.core.code_index import CodebaseIndexer


def test_codebase_indexer_builds_metadata_and_searches(tmp_path: Path):
    (tmp_path / "app.py").write_text("def calculate_total(value):\n    return value * 2\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("NEXUS developer workspace\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=value\n", encoding="utf-8")
    ignored = tmp_path / "node_modules"
    ignored.mkdir()
    (ignored / "bad.js").write_text("secret", encoding="utf-8")

    indexer = CodebaseIndexer(tmp_path)
    files = indexer.build()

    assert [item.path for item in files] == ["README.md", "app.py"]
    assert indexer.summary()["file_count"] == 2
    matches = indexer.search("calculate total")
    assert matches
    assert matches[0].file.path == "app.py"
    assert matches[0].file.language == "python"
    assert matches[0].file.sha256


def test_codebase_indexer_limits_search_results_and_empty_queries(tmp_path: Path):
    (tmp_path / "one.py").write_text("alpha beta", encoding="utf-8")
    (tmp_path / "two.py").write_text("alpha", encoding="utf-8")
    indexer = CodebaseIndexer(tmp_path)
    indexer.build()

    assert indexer.search("   ") == ()
    assert len(indexer.search("alpha", top_k=1)) == 1
