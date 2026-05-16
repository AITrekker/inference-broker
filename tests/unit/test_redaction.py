"""Verify the redacting logger does not leak prompt or key bytes."""

from __future__ import annotations

from sealedx.security.redaction import redact, redact_error_message


def test_known_keys_redacted():
    out = redact({"api_key": "sk-supersecret", "name": "ok"})
    assert out["api_key"] == "<redacted>"
    assert out["name"] == "ok"


def test_nested_keys_redacted():
    out = redact({"creds": {"openai_api_key": "sk-abcdef1234567890abc"}})
    assert out["creds"]["openai_api_key"] == "<redacted>"


def test_prompt_field_redacted():
    out = redact({"prompt": "you are a secret system prompt"})
    assert out["prompt"] == "<redacted>"


def test_key_shape_substring_scrubbed_in_string():
    s = "error context: sk-1234567890abcdef happened"
    cleaned = redact_error_message(s)
    assert "sk-1234567890abcdef" not in cleaned
    assert "<redacted>" in cleaned


def test_anthropic_key_shape_scrubbed():
    s = "Authorization: sk-ant-1234567890abcdef"
    cleaned = redact_error_message(s)
    assert "sk-ant-1234567890abcdef" not in cleaned


def test_hf_token_shape_scrubbed():
    s = "token=hf_aabbccddeeff112233445566"
    cleaned = redact_error_message(s)
    assert "hf_aabbccddeeff112233445566" not in cleaned


def test_passthrough_for_safe_strings():
    safe = "this is a normal log line"
    assert redact_error_message(safe) == safe


def test_redact_lists():
    out = redact(["plain", {"prompt": "secret"}])
    assert out[0] == "plain"
    assert out[1]["prompt"] == "<redacted>"
