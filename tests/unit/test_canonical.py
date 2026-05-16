"""Lock down canonical JSON serialization. Any change here is a protocol break."""

from __future__ import annotations

from sealedx.receipts.canonical import canonical_json_bytes, canonical_json_str


def test_keys_sorted():
    obj = {"b": 1, "a": 2, "c": 3}
    assert canonical_json_str(obj) == '{"a":2,"b":1,"c":3}'


def test_no_whitespace():
    obj = {"a": [1, 2, {"k": "v"}]}
    assert canonical_json_str(obj) == '{"a":[1,2,{"k":"v"}]}'


def test_nested_keys_sorted():
    obj = {"outer": {"z": 1, "a": 2}, "another": {"y": 3, "b": 4}}
    expected = '{"another":{"b":4,"y":3},"outer":{"a":2,"z":1}}'
    assert canonical_json_str(obj) == expected


def test_unicode_preserved():
    # ensure_ascii=False — non-ASCII chars stay as themselves
    obj = {"name": "Colissée"}
    s = canonical_json_str(obj)
    assert "Colissée" in s


def test_bytes_round_trip_through_json():
    import json

    obj = {"a": 1, "b": [None, True, False]}
    canonical = canonical_json_bytes(obj)
    assert json.loads(canonical) == obj
