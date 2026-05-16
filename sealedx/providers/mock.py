"""Deterministic mock provider — the canonical reference adapter.

Behaviour:
- ``supports()`` returns True for any model whose name starts with ``mock-`` or
  matches an entry in ``KNOWN_MOCKS``.
- ``complete()`` looks for a fixture under
  ``examples/<package_name>/mock-fixtures/<input_fingerprint>.json`` (or under
  ``$SEALEDX_HOME/packages/<id>/mock-fixtures/`` if a package_id is provided).
  Falls back to a synthesized output that satisfies the response schema with
  schema-typed default values. The fingerprint is the SHA-256 of the canonical input.
- Token counts are deterministic: ``len(prompt+input)//4`` for in,
  ``len(output)//4`` for out.
- Cost is ``MOCK_COST_PER_TOKEN`` per token, flat. This makes budget-exceeded
  scenarios easy to express in tests.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from sealedx.providers.base import (
    ProviderAdapter,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)
from sealedx.providers.cost_table import MOCK_COST_PER_TOKEN
from sealedx.receipts.canonical import canonical_json_bytes
from sealedx.security.hashing import hash_bytes

KNOWN_MOCKS = {
    "mock-claude-sonnet-4-5",
    "mock-claude-haiku-4-5",
    "mock-gpt-4.1-mini",
    "mock-gpt-4o-mini",
}


def _input_fingerprint(input_obj: dict[str, Any]) -> str:
    return hash_bytes(canonical_json_bytes(input_obj)).removeprefix("sha256:")[:16]


def _default_for_schema(schema: dict[str, Any]) -> Any:
    """Synthesize a minimal value that satisfies ``schema``."""
    if "const" in schema:
        return schema["const"]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    if "default" in schema:
        return schema["default"]

    t = schema.get("type")
    # Handle array-form types ("type": ["string", "null"])
    if isinstance(t, list):
        for candidate in t:
            if candidate != "null":
                t = candidate
                break

    if t == "object":
        out: dict[str, Any] = {}
        props = schema.get("properties", {}) or {}
        for k, sub in props.items():
            out[k] = _default_for_schema(sub)
        return out
    if t == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            return [_default_for_schema(items)]
        return []
    if t == "string":
        return ""
    if t == "integer":
        return 0
    if t == "number":
        return 0
    if t == "boolean":
        return False
    if t == "null":
        return None
    # Unknown / unspecified — best-effort empty object
    return {}


class MockProvider(ProviderAdapter):
    name = "mock"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = fixtures_dir

    def supports(self, model: str) -> bool:
        return model in KNOWN_MOCKS or model.startswith("mock-")

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        if not self.supports(request.model):
            raise ProviderError(
                "model_not_found",
                f"mock provider does not support model {request.model!r}",
            )

        fp = _input_fingerprint(request.input)
        parsed: dict[str, Any] | None = None

        if self._fixtures_dir is not None:
            candidate = self._fixtures_dir / f"{fp}.json"
            if candidate.exists():
                parsed = json.loads(candidate.read_text(encoding="utf-8"))
            else:
                default_path = self._fixtures_dir / "default.json"
                if default_path.exists():
                    parsed = json.loads(default_path.read_text(encoding="utf-8"))

        if parsed is None:
            if request.response_schema is None:
                parsed = {"echo": request.input, "model": request.model}
            else:
                parsed = _default_for_schema(request.response_schema)
                if isinstance(parsed, dict) and "title" in parsed and parsed.get("title") == "":
                    # Light cosmetic touch so the demo output is not entirely empty.
                    topic = request.input.get("topic")
                    if isinstance(topic, str) and topic:
                        parsed["title"] = topic

        output_text = json.dumps(parsed, sort_keys=True)
        tokens_in = (len(request.prompt) + len(canonical_json_bytes(request.input))) // 4
        tokens_out = max(1, len(output_text) // 4)

        return ProviderResponse(
            output_text=output_text,
            parsed_output=parsed,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            provider_request_id=f"mock-req-{fp}",
            raw_metadata={"deterministic": True, "fingerprint": fp},
        )

    def estimate_cost_usd(self, tokens_in: int, tokens_out: int, model: str) -> Decimal:
        return (Decimal(tokens_in + tokens_out) * MOCK_COST_PER_TOKEN).quantize(Decimal("0.0001"))


def fixtures_dir_for_example(package_name: str) -> Path | None:
    """Look up fixtures under the source tree's examples/ directory.

    Used by the broker when a package was built from the in-tree examples. Returns None
    if no fixtures dir exists; the mock provider then synthesizes a default output.
    """
    here = Path(__file__).resolve().parent.parent.parent
    candidate = here / "examples" / package_name / "mock-fixtures"
    return candidate if candidate.exists() else None
