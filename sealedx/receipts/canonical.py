"""Canonical JSON serialization used for hashing and signing.

Convention (locked by tests/unit/test_canonical.py):
- keys sorted lexicographically
- separators ``(",", ":")`` — no whitespace
- ``ensure_ascii=False``
- UTF-8 encoded
- no trailing newline

This is *not* RFC 8785 (JCS); it is a smaller, widely-used convention that suffices for v0.
Migration to JCS is non-breaking on the inputs we use. See docs/limitations.md.
"""

from __future__ import annotations

import json
from typing import Any


def canonical_json_str(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_json_bytes(obj: Any) -> bytes:
    return canonical_json_str(obj).encode("utf-8")
