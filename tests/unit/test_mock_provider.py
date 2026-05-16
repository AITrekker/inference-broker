from __future__ import annotations

import json

import pytest

from sealedx.broker.errors import ProviderError
from sealedx.providers.base import ProviderRequest
from sealedx.providers.mock import MockProvider


def _schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "items"],
        "properties": {
            "title": {"type": "string"},
            "items": {"type": "array", "items": {"type": "string"}},
        },
    }


def _request(model="mock-claude-sonnet-4-5", schema=None):
    return ProviderRequest(
        model=model,
        prompt="prompt body — must not appear in any log",
        input={"a": 1, "b": "two"},
        response_schema=schema or _schema(),
        request_id="req-test",
    )


def test_mock_supports_known_models():
    m = MockProvider()
    assert m.supports("mock-claude-sonnet-4-5")
    assert m.supports("mock-anything")
    assert not m.supports("gpt-4.1")


def test_mock_rejects_unknown_model():
    m = MockProvider()
    bad = ProviderRequest(
        model="not-a-mock", prompt="", input={}, response_schema=None, request_id="r"
    )
    with pytest.raises(ProviderError) as e:
        m.complete(bad)
    assert e.value.code == "model_not_found"


def test_mock_returns_schema_default():
    resp = MockProvider().complete(_request())
    assert resp.parsed_output is not None
    assert resp.parsed_output["items"] == [""]
    assert resp.tokens_in is not None and resp.tokens_in > 0
    assert resp.tokens_out is not None and resp.tokens_out > 0


def test_mock_is_deterministic():
    a = MockProvider().complete(_request())
    b = MockProvider().complete(_request())
    assert a.parsed_output == b.parsed_output
    assert a.tokens_in == b.tokens_in
    assert a.tokens_out == b.tokens_out


def test_mock_uses_fixture_when_present(tmp_path):
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    payload = {"title": "from-fixture", "items": ["a", "b"]}
    # Compute the same fingerprint the provider will compute for our input
    from sealedx.providers.mock import _input_fingerprint

    inp = {"a": 1, "b": "two"}
    fp = _input_fingerprint(inp)
    (fixture_dir / f"{fp}.json").write_text(json.dumps(payload))

    m = MockProvider(fixtures_dir=fixture_dir)
    req = ProviderRequest(
        model="mock-claude-sonnet-4-5",
        prompt="p",
        input=inp,
        response_schema=_schema(),
        request_id="r",
    )
    resp = m.complete(req)
    assert resp.parsed_output == payload


def test_mock_cost_is_predictable():
    m = MockProvider()
    cost = m.estimate_cost_usd(1_000_000, 0, "mock-claude-sonnet-4-5")
    # 1M tokens × 0.000001 USD/token = $1.00
    assert cost == cost.normalize().__class__("1.0000")
