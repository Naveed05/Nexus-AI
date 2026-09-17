"""Durable, integrity-checked storage for benchmark baselines."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Final

from nexus.core.benchmarks import BenchmarkBaseline


_STORE_SCHEMA: Final[str] = "nexus-benchmark-baseline-v1"
_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class BenchmarkBaselineStore:
    """File-backed benchmark baseline store with atomic writes and tamper detection."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_key(key: str) -> str:
        if not isinstance(key, str) or not _SAFE_KEY.fullmatch(key):
            raise ValueError("invalid benchmark baseline key")
        return key

    def _path(self, key: str) -> Path:
        return self._root / f"{self._validate_key(key)}.json"

    def save(self, key: str, baseline: BenchmarkBaseline) -> None:
        path = self._path(key)
        baseline_payload = baseline.as_dict()
        envelope = {
            "schema": _STORE_SCHEMA,
            "baseline": baseline_payload,
            "integrity": __import__("hashlib").sha256(
                _canonical_json(baseline_payload).encode("utf-8")
            ).hexdigest(),
        }
        serialized = _canonical_json(envelope) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=self._root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def load(self, key: str) -> BenchmarkBaseline:
        path = self._path(key)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"benchmark baseline not found: {key}") from exc
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid benchmark baseline store JSON") from exc
        if not isinstance(envelope, dict) or envelope.get("schema") != _STORE_SCHEMA:
            raise ValueError("unsupported benchmark baseline store schema")
        baseline_payload = envelope.get("baseline")
        integrity = envelope.get("integrity")
        if not isinstance(baseline_payload, dict) or not isinstance(integrity, str):
            raise ValueError("invalid benchmark baseline store payload")
        expected = __import__("hashlib").sha256(
            _canonical_json(baseline_payload).encode("utf-8")
        ).hexdigest()
        if integrity != expected:
            raise ValueError("benchmark baseline store integrity check failed")
        return BenchmarkBaseline.from_dict(baseline_payload)

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            raise FileNotFoundError(f"benchmark baseline not found: {key}")

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()
