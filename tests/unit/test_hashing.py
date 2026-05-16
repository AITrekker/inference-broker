from __future__ import annotations

from sealedx.security.hashing import hash_bytes, hash_canonical_json, hash_text


def test_hash_namespaced():
    h = hash_text("hello")
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_text_and_bytes_equivalent():
    assert hash_text("hello world") == hash_bytes(b"hello world")


def test_canonical_json_independent_of_key_order():
    a = {"x": 1, "y": 2}
    b = {"y": 2, "x": 1}
    assert hash_canonical_json(a) == hash_canonical_json(b)


def test_canonical_json_distinguishes_values():
    assert hash_canonical_json({"x": 1}) != hash_canonical_json({"x": 2})
