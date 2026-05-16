"""Per-(provider, model) USD-per-Mtok cost estimates.

DATED. The table is conspicuously stamped with ``AS_OF`` and that date is recorded
into every receipt's ``policy_flags`` as ``cost_estimated:<as_of>``. Production
deployments must source rates from the provider's billing API, not this table.
"""

from __future__ import annotations

from decimal import Decimal

AS_OF = "2026-05-15"

# Costs are USD per million tokens, separately for input and output.
# Numbers are intentionally approximate. Receipts mark them as estimates.

OPENAI_COSTS: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4.1": (Decimal("2.00"), Decimal("8.00")),
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
    "gpt-4.1-nano": (Decimal("0.10"), Decimal("0.40")),
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "o3": (Decimal("2.00"), Decimal("8.00")),
    "o3-mini": (Decimal("1.10"), Decimal("4.40")),
}

ANTHROPIC_COSTS: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-4-7": (Decimal("15.00"), Decimal("75.00")),
    "claude-sonnet-4-6": (Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-4-5": (Decimal("1.00"), Decimal("5.00")),
    "claude-sonnet-4-5": (Decimal("3.00"), Decimal("15.00")),
    "claude-opus-4-5": (Decimal("15.00"), Decimal("75.00")),
}

# Mock provider: flat cents-per-token, predictable for budget tests.
MOCK_COST_PER_TOKEN = Decimal("0.000001")


def lookup(provider: str, model: str) -> tuple[Decimal, Decimal] | None:
    if provider == "openai":
        return OPENAI_COSTS.get(model)
    if provider == "anthropic":
        return ANTHROPIC_COSTS.get(model)
    return None


def estimate(provider: str, model: str, tokens_in: int, tokens_out: int) -> Decimal | None:
    rates = lookup(provider, model)
    if rates is None:
        return None
    in_rate, out_rate = rates
    cost = (Decimal(tokens_in) * in_rate + Decimal(tokens_out) * out_rate) / Decimal("1000000")
    return cost.quantize(Decimal("0.0001"))
