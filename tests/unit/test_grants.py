from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from sealedx.broker.errors import (
    BudgetExceededError,
    GrantExpiredError,
    GrantRevokedError,
)
from sealedx.grants.manager import (
    assert_usable,
    charge,
    create_grant,
    list_grants,
    load_grant,
    parse_duration,
    revoke,
)
from sealedx.grants.models import GrantStatus


def test_parse_duration_units():
    assert parse_duration("30s") == timedelta(seconds=30)
    assert parse_duration("15m") == timedelta(minutes=15)
    assert parse_duration("1h") == timedelta(hours=1)
    assert parse_duration("2d") == timedelta(days=2)


def test_parse_duration_invalid():
    with pytest.raises(ValueError):
        parse_duration("forever")


def test_create_and_load_grant():
    g = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("5"),
        expires_in="1h",
    )
    assert g.grant_id.startswith("grant_")
    loaded = load_grant(g.grant_id)
    assert loaded.grant_id == g.grant_id
    assert loaded.budget_usd == Decimal("5")


def test_charge_deducts_and_persists():
    g = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("1"),
        expires_in="1h",
    )
    g = charge(g, Decimal("0.25"))
    assert g.spent_usd == Decimal("0.25")
    assert g.derived_status() == GrantStatus.active

    reloaded = load_grant(g.grant_id)
    assert reloaded.spent_usd == Decimal("0.25")


def test_charge_exceeding_budget_raises():
    g = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("1"),
        expires_in="1h",
    )
    with pytest.raises(BudgetExceededError):
        charge(g, Decimal("2"))


def test_charge_to_exact_budget_marks_exhausted():
    g = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("1"),
        expires_in="1h",
    )
    g = charge(g, Decimal("1"))
    assert g.derived_status() == GrantStatus.exhausted


def test_expired_grant_detected():
    g = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("5"),
        expires_in="1s",
    )
    far_future = datetime.now(UTC) + timedelta(hours=1)
    assert g.derived_status(now=far_future) == GrantStatus.expired


def test_assert_usable_rejects_revoked():
    g = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("5"),
        expires_in="1h",
    )
    revoke(g.grant_id)
    with pytest.raises(GrantRevokedError):
        assert_usable(load_grant(g.grant_id))


def test_assert_usable_rejects_expired_grant():
    g = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("5"),
        expires_in="1s",
    )
    # Mutate persisted record so derived_status() reads expired without sleeping.
    expired = g.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    from sealedx.grants.manager import _persist

    _persist(expired)
    with pytest.raises(GrantExpiredError):
        assert_usable(load_grant(g.grant_id))


def test_list_grants_finds_created():
    g = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("5"),
        expires_in="1h",
    )
    ids = {x.grant_id for x in list_grants()}
    assert g.grant_id in ids
