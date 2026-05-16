"""Provider adapter registry. Real adapters are imported on demand only."""

from __future__ import annotations

from sealedx.broker.errors import ProviderError
from sealedx.providers.base import ProviderAdapter
from sealedx.providers.mock import MockProvider, fixtures_dir_for_example

_KNOWN_PROVIDERS = {"mock", "openai", "anthropic"}


def get_adapter(provider: str, *, package_name: str | None = None) -> ProviderAdapter:
    if provider == "mock":
        fixtures = fixtures_dir_for_example(package_name) if package_name else None
        return MockProvider(fixtures_dir=fixtures)
    if provider == "openai":
        try:
            from sealedx.providers.openai_adapter import OpenAIAdapter
        except ImportError as e:  # pragma: no cover — exercised only when openai sdk is missing
            raise ProviderError(
                "provider_unavailable",
                "openai adapter requires the optional 'openai' extra: "
                "pip install 'sealedx[openai]'",
            ) from e
        return OpenAIAdapter()
    if provider == "anthropic":
        try:
            from sealedx.providers.anthropic_adapter import AnthropicAdapter
        except ImportError as e:  # pragma: no cover
            raise ProviderError(
                "provider_unavailable",
                "anthropic adapter requires the optional 'anthropic' extra",
            ) from e
        return AnthropicAdapter()
    raise ProviderError(
        "provider_unavailable",
        f"unknown provider {provider!r}; known: {sorted(_KNOWN_PROVIDERS)}",
    )
