from pathlib import Path

import pytest

from nexus.core.resilience import BackupError, create_backup, verify_backup, list_backups


def make_store(path: Path, value: str) -> None:
    import sqlite3
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE state (value TEXT)")
        db.execute("INSERT INTO state(value) VALUES (?)", (value,))
        db.commit()


def test_backup_is_checksum_verified(tmp_path):
    state = tmp_path / "state.sqlite3"
    make_store(state, "one")
    manifest = create_backup(
        backup_root=tmp_path / "backups",
        stores={"state": state},
        backup_id="backup-001",
    )
    assert manifest.verified is True
    verified = verify_backup(tmp_path / "backups" / "backup-001")
    assert verified.verified is True
    assert verified.files[0].sha256 == manifest.files[0].sha256


def test_backup_skips_missing_optional_stores(tmp_path):
    state = tmp_path / "state.sqlite3"
    make_store(state, "one")
    manifest = create_backup(
        backup_root=tmp_path / "backups",
        stores={"state": state, "missing": tmp_path / "missing.sqlite3"},
        backup_id="backup-002",
    )
    assert [item.source for item in manifest.files] == [str(state)]


def test_backup_detects_tampering(tmp_path):
    state = tmp_path / "state.sqlite3"
    make_store(state, "one")
    create_backup(backup_root=tmp_path / "backups", stores={"state": state}, backup_id="backup-003")
    snapshot = tmp_path / "backups" / "backup-003" / "state.sqlite3"
    with snapshot.open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(BackupError, match="checksum mismatch"):
        verify_backup(tmp_path / "backups" / "backup-003")


def test_corrupt_source_is_rejected(tmp_path):
    source = tmp_path / "bad.sqlite3"
    source.write_bytes(b"not sqlite")
    with pytest.raises(BackupError):
        create_backup(backup_root=tmp_path / "backups", stores={"bad": source}, backup_id="bad")


def test_list_backups_returns_verified_snapshots(tmp_path):
    state = tmp_path / "state.sqlite3"
    make_store(state, "one")
    root = tmp_path / "backups"
    create_backup(backup_root=root, stores={"state": state}, backup_id="a")
    create_backup(backup_root=root, stores={"state": state}, backup_id="b")
    assert [item.backup_id for item in list_backups(root)] == ["b", "a"]
