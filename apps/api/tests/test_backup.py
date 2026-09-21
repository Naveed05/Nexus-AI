from pathlib import Path

from nexus.core.backup import create_local_snapshot


def test_backup_snapshot_copies_runtime_state(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "runs.txt").write_text("run-state")
    destination = tmp_path / "backups" / "snapshot"

    result = create_local_snapshot(str(source), str(destination))

    assert result == str(destination)
    assert (destination / "runs.txt").read_text() == "run-state"
