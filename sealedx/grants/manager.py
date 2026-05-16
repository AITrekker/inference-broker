"""Create, load, charge, expire, list grants."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sealedx.broker.errors import (
    BudgetExceededError,
    GrantExhaustedError,
    GrantExpiredError,
    GrantNotFoundError,
    GrantRevokedError,
)
from sealedx.grants.models import ExecutionGrant, GrantStatus
from sealedx.storage.paths import atomic_write_json, grants_dir, read_json


_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$", re.IGNORECASE)


def parse_duration(text: str) -> timedelta:
    """Parse durations like '30s', '15m', '1h', '2d'."""
    m = _DURATION_RE.match(text)
    if not m:
        raise ValueError(f"invalid duration {text!r}; expected forms like '30s', '15m', '1h', '2d'")
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit == "s":
        return timedelta(seconds=n)
    if unit == "m":
        return timedelta(minutes=n)
    if unit == "h":
        return timedelta(hours=n)
    return timedelta(days=n)


def create_grant(
    *,
    provider: str,
    model: str,
    budget_usd: Decimal | str | float,
    expires_in: str,
    allowed_models: list[str] | None = None,
) -> ExecutionGrant:
    grant_id = "grant_" + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    grant = ExecutionGrant(
        grant_id=grant_id,
        provider=provider,
        model=model,
        budget_usd=Decimal(str(budget_usd)),
        spent_usd=Decimal("0"),
        expires_at=now + parse_duration(expires_in),
        allowed_models=allowed_models,
        created_at=now,
        status=GrantStatus.active,
    )
    _persist(grant)
    return grant


def load_grant(grant_id: str) -> ExecutionGrant:
    path = grants_dir() / f"{grant_id}.json"
    if not path.exists():
        raise GrantNotFoundError(grant_id)
    return ExecutionGrant.model_validate(read_json(path))


def list_grants() -> list[ExecutionGrant]:
    out: list[ExecutionGrant] = []
    for path in sorted(grants_dir().glob("grant_*.json")):
        try:
            out.append(ExecutionGrant.model_validate(read_json(path)))
        except Exception:  # noqa: BLE001
            continue
    return out


def revoke(grant_id: str) -> ExecutionGrant:
    grant = load_grant(grant_id)
    grant = grant.model_copy(update={"status": GrantStatus.revoked})
    _persist(grant)
    return grant


def assert_usable(grant: ExecutionGrant) -> None:
    """Raise if the grant cannot accept a new charge."""
    status = grant.derived_status()
    if status == GrantStatus.revoked:
        raise GrantRevokedError(grant.grant_id)
    if status == GrantStatus.expired:
        raise GrantExpiredError(grant.grant_id)
    if status == GrantStatus.exhausted:
        raise GrantExhaustedError(grant.grant_id)


def charge(grant: ExecutionGrant, amount_usd: Decimal) -> ExecutionGrant:
    """Charge a grant. Raises BudgetExceededError if the post-charge total would exceed budget."""
    new_spent = grant.spent_usd + amount_usd
    if new_spent > grant.budget_usd:
        raise BudgetExceededError(grant.grant_id)
    new_status = GrantStatus.exhausted if new_spent >= grant.budget_usd else grant.status
    updated = grant.model_copy(update={"spent_usd": new_spent, "status": new_status})
    _persist(updated)
    return updated


def _persist(grant: ExecutionGrant) -> None:
    atomic_write_json(grants_dir() / f"{grant.grant_id}.json", grant.model_dump(mode="json"))
