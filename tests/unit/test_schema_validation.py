from __future__ import annotations

import json

import pytest

from sealedx.broker.errors import SealedxError
from sealedx.schemas.validate import is_valid_schema, validate


def _video_schemas(examples_root):
    base = examples_root / "immersive-video-planner"
    return (
        json.loads((base / "input.schema.json").read_text()),
        json.loads((base / "output.schema.json").read_text()),
    )


def test_valid_input_passes(examples_root):
    schema, _ = _video_schemas(examples_root)
    inp = json.loads((examples_root / "immersive-video-planner" / "input.json").read_text())
    validate(inp, schema, kind="input")


def test_missing_required_field_rejected(examples_root):
    schema, _ = _video_schemas(examples_root)
    bad = {"topic": "x"}
    with pytest.raises(SealedxError) as e:
        validate(bad, schema, kind="input")
    assert e.value.code == "invalid_input"


def test_wrong_enum_value_rejected(examples_root):
    schema, _ = _video_schemas(examples_root)
    bad = {
        "topic": "x",
        "audience": "y",
        "duration_seconds": 30,
        "interactivity_level": "extreme",
        "style": "z",
    }
    with pytest.raises(SealedxError) as e:
        validate(bad, schema, kind="input")
    assert e.value.code == "invalid_input"


def test_output_validation_uses_invalid_output_code(examples_root):
    _, output_schema = _video_schemas(examples_root)
    with pytest.raises(SealedxError) as e:
        validate({"title": ""}, output_schema, kind="output")
    assert e.value.code == "invalid_output"


def test_is_valid_schema_accepts_valid():
    ok, err = is_valid_schema({"type": "object"})
    assert ok and err is None


def test_is_valid_schema_rejects_invalid():
    ok, err = is_valid_schema({"type": "wat"})
    assert not ok and err
