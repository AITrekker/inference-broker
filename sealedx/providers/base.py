"""Provider adapter contract. See docs/provider-adapters.md."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

# Re-export ProviderError so adapters can ``from sealedx.providers.base import ProviderError``.
from sealedx.broker.errors import ProviderError  # noqa: F401


@dataclass(frozen=True)
class ProviderRequest:
    model: str
    prompt: str
    input: dict[str, Any]
    response_schema: dict[str, Any] | None
    request_id: str


@dataclass(frozen=True)
class ProviderResponse:
    output_text: str | None
    parsed_output: dict[str, Any] | None
    tokens_in: int | None
    tokens_out: int | None
    provider_request_id: str | None
    raw_metadata: dict[str, Any] | None = None


class ProviderAdapter(Protocol):
    """All adapters implement this Protocol; the broker treats them identically."""

    name: str

    def supports(self, model: str) -> bool: ...

    def complete(self, request: ProviderRequest) -> ProviderResponse: ...

    def estimate_cost_usd(self, tokens_in: int, tokens_out: int, model: str) -> Decimal: ...
