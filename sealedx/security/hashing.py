"""SHA-256 helpers. Hashes are namespaced as ``sha256:<hex>`` so the algorithm can migrate later."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from sealedx.receipts.canonical import canonical_json_bytes

ALG_PREFIX = "sha256:"


def hash_bytes(data: bytes) -> str:
    return ALG_PREFIX + hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return ALG_PREFIX + h.hexdigest()


def hash_canonical_json(obj: Any) -> str:
    return hash_bytes(canonical_json_bytes(obj))
