"""Pydantic model for the execution receipt. Wire-stable shape — see docs/protocol.md §5."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_serializer

PROTOCOL_VERSION = "0.1"
RECEIPT_VERSION = "0.1"


class ReceiptStatus(str, Enum):
    succeeded = "succeeded"
    invalid_input = "invalid_input"
    invalid_output = "invalid_output"
    budget_exceeded = "budget_exceeded"
    grant_expired = "grant_expired"
    grant_exhausted = "grant_exhausted"
    grant_revoked = "grant_revoked"
    provider_error = "provider_error"
    policy_denied = "policy_denied"
    internal_error = "internal_error"


class ExecutionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: str = PROTOCOL_VERSION
    receipt_version: str = RECEIPT_VERSION

    execution_id: str
    workflow_package_id: str
    workflow_name: str
    workflow_version: str

    prompt_hash: str
    input_schema_hash: str
    output_schema_hash: str
    input_hash: str
    output_hash: str | None

    provider: str
    model: str
    tokens_in: int | None
    tokens_out: int | None
    estimated_cost_usd: Decimal | None
    budget_usd: Decimal

    started_at: datetime
    completed_at: datetime
    status: ReceiptStatus
    policy_flags: list[str]

    broker_public_key_id: str
    broker_signature: str

    @field_serializer("budget_usd")
    def _ser_budget(self, value: Decimal) -> str:
        return f"{value:.4f}"

    @field_serializer("estimated_cost_usd")
    def _ser_cost(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return f"{value:.4f}"
