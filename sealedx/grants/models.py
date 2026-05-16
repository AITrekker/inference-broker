"""Pydantic model for an execution grant.

A grant carries no API key. Provider credentials are resolved at execution time
from the environment. See docs/protocol.md §2.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_serializer

PROTOCOL_VERSION = "0.1"


class GrantStatus(str, Enum):
    active = "active"
    expired = "expired"
    exhausted = "exhausted"
    revoked = "revoked"


class ExecutionGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: str = PROTOCOL_VERSION
    grant_id: str
    provider: str
    model: str
    budget_usd: Decimal
    spent_usd: Decimal = Field(default=Decimal("0"))
    expires_at: datetime
    allowed_models: list[str] | None = None
    created_at: datetime
    status: GrantStatus = GrantStatus.active

    @field_serializer("budget_usd", "spent_usd")
    def _ser_decimal(self, value: Decimal) -> str:
        return f"{value:.4f}"

    def derived_status(self, *, now: datetime | None = None) -> GrantStatus:
        """Compute the effective status without mutating ``self``."""
        if self.status == GrantStatus.revoked:
            return GrantStatus.revoked
        ts = now or datetime.now(UTC)
        if ts >= self.expires_at:
            return GrantStatus.expired
        if self.spent_usd >= self.budget_usd:
            return GrantStatus.exhausted
        return GrantStatus.active

    def remaining_usd(self) -> Decimal:
        rem = self.budget_usd - self.spent_usd
        return rem if rem > 0 else Decimal("0")
