from __future__ import annotations

import shutil
from pathlib import Path


def create_local_snapshot(source: str, destination: str) -> str:
    """Create a point-in-time filesystem snapshot for beta backup drills."""
    src = Path(source)
    dst = Path(destination)
    if not src.exists():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return str(dst)
