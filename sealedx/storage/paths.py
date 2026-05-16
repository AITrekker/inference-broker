"""Filesystem layout under ``$SEALEDX_HOME`` and atomic write helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def sealedx_home() -> Path:
    override = os.environ.get("SEALEDX_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".sealedx"


def packages_dir() -> Path:
    p = sealedx_home() / "packages"
    p.mkdir(parents=True, exist_ok=True)
    return p


def package_dir(package_id: str) -> Path:
    p = packages_dir() / package_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def grants_dir() -> Path:
    p = sealedx_home() / "grants"
    p.mkdir(parents=True, exist_ok=True)
    return p


def receipts_dir() -> Path:
    p = sealedx_home() / "receipts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_dir() -> Path:
    p = sealedx_home() / "results"
    p.mkdir(parents=True, exist_ok=True)
    return p


def keys_dir() -> Path:
    p = sealedx_home() / "keys"
    p.mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    return p


def atomic_write_bytes(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Write ``data`` to ``path`` via tmp + fsync + rename. Mode applied to the final file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".sealedx-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, mode: int = 0o600) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode=mode)


def atomic_write_json(path: Path, obj: Any, mode: int = 0o600) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True), mode=mode)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
