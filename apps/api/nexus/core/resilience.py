"""Operational resilience and disaster-recovery primitives for NEXUS.

Backups are explicit, local, checksum-verified snapshots of the durable SQLite
control-plane stores. The module never exposes database contents through API
responses and never deletes source state during backup.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any


class BackupError(RuntimeError):
    """Raised when a backup cannot satisfy the integrity contract."""


@dataclass(frozen=True)
class BackupFile:
    source: str
    snapshot: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class BackupManifest:
    backup_id: str
    created_at: str
    files: tuple[BackupFile, ...]
    verified: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_sqlite(path: Path) -> None:
    try:
        with sqlite3.connect(path) as db:
            result = db.execute("PRAGMA quick_check").fetchone()
    except sqlite3.Error as exc:
        raise BackupError(f"unable to inspect SQLite store: {path}") from exc
    if not result or str(result[0]).lower() != "ok":
        raise BackupError(f"SQLite integrity check failed: {path}")


def create_backup(
    *,
    backup_root: str | Path,
    stores: dict[str, str | Path],
    backup_id: str | None = None,
) -> BackupManifest:
    root = Path(backup_root)
    root.mkdir(parents=True, exist_ok=True)
    identifier = backup_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = root / identifier
    target.mkdir(parents=False, exist_ok=False)

    files: list[BackupFile] = []
    try:
        for name, source_value in sorted(stores.items()):
            source = Path(source_value)
            if not source.exists():
                continue
            if not source.is_file():
                raise BackupError(f"backup source is not a file: {source}")
            _validate_sqlite(source)
            destination = target / f"{name}.sqlite3"
            shutil.copy2(source, destination)
            _validate_sqlite(destination)
            files.append(
                BackupFile(
                    source=str(source),
                    snapshot=str(destination),
                    size_bytes=destination.stat().st_size,
                    sha256=_sha256(destination),
                )
            )
        if not files:
            raise BackupError("no durable stores were available for backup")

        manifest = BackupManifest(
            backup_id=identifier,
            created_at=datetime.now(timezone.utc).isoformat(),
            files=tuple(files),
            verified=True,
        )
        (target / "manifest.json").write_text(
            json.dumps(backup_payload(manifest), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return manifest
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise


def verify_backup(path: str | Path) -> BackupManifest:
    root = Path(path)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise BackupError("backup manifest is missing")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = tuple(
            BackupFile(
                source=str(item["source"]),
                snapshot=str(item["snapshot"]),
                size_bytes=int(item["size_bytes"]),
                sha256=str(item["sha256"]),
            )
            for item in raw["files"]
        )
        manifest = BackupManifest(
            backup_id=str(raw["backup_id"]),
            created_at=str(raw["created_at"]),
            files=files,
            verified=False,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BackupError("invalid backup manifest") from exc

    for item in manifest.files:
        snapshot = Path(item.snapshot)
        if not snapshot.is_file():
            raise BackupError(f"backup snapshot is missing: {snapshot}")
        if snapshot.stat().st_size != item.size_bytes:
            raise BackupError(f"backup size mismatch: {snapshot}")
        if _sha256(snapshot) != item.sha256:
            raise BackupError(f"backup checksum mismatch: {snapshot}")
        _validate_sqlite(snapshot)

    return BackupManifest(
        backup_id=manifest.backup_id,
        created_at=manifest.created_at,
        files=manifest.files,
        verified=True,
    )


def list_backups(backup_root: str | Path, *, limit: int = 20) -> list[BackupManifest]:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    root = Path(backup_root)
    if not root.exists():
        return []
    results: list[BackupManifest] = []
    for child in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        try:
            results.append(verify_backup(child))
        except BackupError:
            continue
        if len(results) >= limit:
            break
    return results


def backup_payload(manifest: BackupManifest) -> dict[str, Any]:
    payload = asdict(manifest)
    payload["files"] = [asdict(item) for item in manifest.files]
    return payload
