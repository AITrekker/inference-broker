"""OpenAI provider adapter. Imported only when the customer issues an OpenAI grant.

Tests do not exercise this module — it is gated on a real ``OPENAI_API_KEY``.
"""

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
from sealedx.security.redaction import get_logger, redact_error_message, unsafe_debug_prompt_enabled

log = get_logger("providers.openai")


class OpenAIAdapter(ProviderAdapter):
    name = "openai"

    def __init__(self) -> None:
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as e:
            raise ProviderError(
                "provider_unavailable",
                "openai package not installed; install with `pip install 'sealedx[openai]'`",
            ) from e
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ProviderError("auth_error", "OPENAI_API_KEY not set")
        self._client = OpenAI(api_key=api_key)

    def supports(self, model: str) -> bool:
        return any(model.startswith(prefix) for prefix in ("gpt-", "o3", "o4", "gpt-5"))

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        try:
            messages = [
                {"role": "system", "content": request.prompt},
                {"role": "user", "content": json.dumps(request.input, sort_keys=True)},
            ]
            kwargs: dict[str, Any] = {"model": request.model, "messages": messages}
            if request.response_schema is not None:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "sealedx_workflow_output",
                        "schema": request.response_schema,
                        "strict": True,
                    },
                }
            if unsafe_debug_prompt_enabled():
                log.debug("openai request: %s", kwargs)
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            raise ProviderError("provider_error", redact_error_message(str(e))) from None

        choice = resp.choices[0].message
        text = choice.content or ""
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
            tokens_in=getattr(usage, "prompt_tokens", None),
            tokens_out=getattr(usage, "completion_tokens", None),
            provider_request_id=getattr(resp, "id", None),
            raw_metadata=None,
        )

    def estimate_cost_usd(self, tokens_in: int, tokens_out: int, model: str) -> Decimal:
        result = estimate("openai", model, tokens_in, tokens_out)
        if result is None:
            return Decimal("0")
        return result
