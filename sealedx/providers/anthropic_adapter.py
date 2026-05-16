"""Anthropic provider adapter. Gated on ANTHROPIC_API_KEY; not exercised by tests."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

from sealedx.providers.base import (
    ProviderAdapter,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)
from sealedx.providers.cost_table import estimate
from sealedx.security.redaction import get_logger, redact_error_message

log = get_logger("providers.anthropic")


_JSON_INSTRUCTION = (
    "\n\nReturn ONLY a JSON object that conforms to the following JSON Schema. "
    "Do not include any prose, markdown fencing, or commentary.\n"
    "JSON Schema:\n"
)


class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"

    def __init__(self) -> None:
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError as e:
            raise ProviderError(
                "provider_unavailable",
                "anthropic package not installed; install with `pip install 'sealedx[anthropic]'`",
            ) from e
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ProviderError("auth_error", "ANTHROPIC_API_KEY not set")
        self._client = anthropic.Anthropic(api_key=api_key)

    def supports(self, model: str) -> bool:
        return model.startswith("claude-")

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        system = request.prompt
        if request.response_schema is not None:
            schema_text = json.dumps(request.response_schema, sort_keys=True)
            system = system + _JSON_INSTRUCTION + schema_text
        try:
            resp = self._client.messages.create(
                model=request.model,
                max_tokens=4096,
                system=system,
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(request.input, sort_keys=True),
                    }
                ],
            )
        except Exception as e:  # noqa: BLE001
            raise ProviderError("provider_error", redact_error_message(str(e))) from None

        text_chunks = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        text = "".join(text_chunks)
        parsed: dict[str, Any] | None
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                parsed = None
        except json.JSONDecodeError:
            parsed = None

        usage = getattr(resp, "usage", None)
        return ProviderResponse(
            output_text=text,
            parsed_output=parsed,
            tokens_in=getattr(usage, "input_tokens", None),
            tokens_out=getattr(usage, "output_tokens", None),
            provider_request_id=getattr(resp, "id", None),
            raw_metadata=None,
        )

    def estimate_cost_usd(self, tokens_in: int, tokens_out: int, model: str) -> Decimal:
        result = estimate("anthropic", model, tokens_in, tokens_out)
        if result is None:
            return Decimal("0")
        return result
