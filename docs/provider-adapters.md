# Provider Adapters

`sealedx` is provider-neutral. The broker runtime knows nothing about specific providers; it talks to a `ProviderAdapter` and treats every adapter identically. This file documents the contract and shipped adapters.

## Adapter contract

```python
from typing import Protocol
from decimal import Decimal
from sealedx.providers.base import ProviderRequest, ProviderResponse

class ProviderAdapter(Protocol):
    name: str

    def supports(self, model: str) -> bool: ...

    def complete(self, request: ProviderRequest) -> ProviderResponse: ...

    def estimate_cost_usd(self, tokens_in: int, tokens_out: int, model: str) -> Decimal: ...
```

`ProviderRequest`:

```python
@dataclass(frozen=True)
class ProviderRequest:
    model: str
    prompt: str                              # the package's prompt body
    input: dict[str, Any]                    # validated user input
    response_schema: dict[str, Any] | None   # the package's output schema, if structured-output is required
    request_id: str
```

`ProviderResponse`:

```python
@dataclass(frozen=True)
class ProviderResponse:
    output_text: str | None
    parsed_output: dict[str, Any] | None     # already JSON-decoded if the adapter performed structured-output decoding
    tokens_in: int | None
    tokens_out: int | None
    provider_request_id: str | None
    raw_metadata: dict[str, Any] | None      # provider-specific; not signed into the receipt
```

`ProviderError` (in `sealedx.providers.base`) is the only exception type adapters may surface. It carries a redacted `message` and a `code` (`auth_error`, `rate_limited`, `model_not_found`, `bad_request`, `provider_unavailable`, `internal_error`).

## Adapter responsibilities

Every adapter must:

1. **Read credentials at call time, never from disk state.** No adapter caches keys.
2. **Convert provider-native errors to `ProviderError` with redacted messages.** Stack traces and provider error bodies go to local logs; never to receipts or the customer.
3. **Never emit prompt or input bytes at INFO level.** DEBUG-level logging of prompt is permitted only behind `--unsafe-debug-prompt`.
4. **Return `tokens_in`/`tokens_out` if the provider reports them**, otherwise `None`. The broker handles `None` by setting the `usage_unavailable` policy flag.
5. **Validate that the model is supported** via `supports(model)` before starting. The broker calls this first.
6. **Be deterministic where possible.** The mock provider must be deterministic. Real adapters may carry non-determinism from the provider; tests do not depend on real adapters.
7. **Use structured-output features when available.** If `response_schema` is provided and the provider supports JSON-mode / response-format / tools-as-output, use it. This raises the cost of prompt extraction via output (T9).

## Shipped adapters

### MockProvider (`sealedx/providers/mock.py`)

The canonical reference adapter. Required.

- `name = "mock"`
- Supports any model whose name starts with `mock-`.
- Reads optional fixtures from `examples/<package_name>/mock-fixtures/<input-fingerprint>.json`. If a fixture matches, returns it verbatim. Otherwise generates a deterministic placeholder that satisfies the package's output schema (filled with schema-typed defaults: empty strings for `string`, 0 for `number`, `[]` for `array`, etc.).
- Cost: $0.000001 per token in/out, flat. Lets budget-exceeded tests trigger predictably.
- Token counts: `len(prompt) // 4 + len(json.dumps(input)) // 4` for in; `len(json.dumps(output)) // 4` for out.

This adapter is what `scripts/demo.sh` and the entire test suite use. No external service.

### OpenAIAdapter (`sealedx/providers/openai.py`)

Optional. Imported only when `OPENAI_API_KEY` is set.

- `name = "openai"`
- Supports models matching `gpt-4*`, `gpt-4.1*`, `o*`, `gpt-5*` (loose prefix match — the v0 model registry is intentionally permissive).
- Uses Responses API with `response_format={"type": "json_schema", ...}` when `response_schema` is provided.
- Costs from `cost_table.OPENAI_COSTS_2026_05` — clearly dated, marked stale-soon in docs.

### AnthropicAdapter (`sealedx/providers/anthropic.py`)

Optional. Imported only when `ANTHROPIC_API_KEY` is set.

- `name = "anthropic"`
- Supports `claude-*` model IDs.
- Uses Messages API. For structured output, prepends a JSON-schema instruction to the system prompt and parses the assistant message as JSON. Tools-based JSON output is a v0.2 stretch.
- Costs from `cost_table.ANTHROPIC_COSTS_2026_05`.

### Hugging Face — stretch goal

Defined in `docs/roadmap.md`; not part of v0.1.

## Cost table

`sealedx/providers/cost_table.py` ships USD-per-million-token estimates per (provider, model) as of the document date. The table is conspicuously labeled and has an `as_of` field stamped into every receipt's `policy_flags` as `cost_estimated:<as_of>` so anyone reading the receipt knows the table version that produced the estimate.

For production, costs should come from the provider's billing API or an enterprise rate card, not a hard-coded table. v0 is honest about this.

## Adding a new adapter

1. Create `sealedx/providers/<name>.py` implementing `ProviderAdapter`.
2. Add an import-on-demand entry in `sealedx/providers/registry.py`:

```python
def get_adapter(provider: str) -> ProviderAdapter:
    if provider == "mock":
        from sealedx.providers.mock import MockProvider
        return MockProvider()
    if provider == "openai":
        from sealedx.providers.openai import OpenAIAdapter
        return OpenAIAdapter()
    ...
```

3. Add a row to `sealedx/providers/cost_table.py`.
4. Add adapter unit tests under `tests/unit/test_providers_<name>.py`. **Real-API tests are forbidden in CI**; gate them behind `pytest -m live`.
5. Update `docs/provider-adapters.md` (this file) and the README provider table.

## What adapters must not do

- Persist anything outside the broker's storage layer.
- Read or write the broker signing key.
- Modify grants directly. Charging is the broker's responsibility, computed from the adapter's response.
- Emit telemetry containing prompt or input bytes.
- Throw raw `Exception` — wrap in `ProviderError`.
