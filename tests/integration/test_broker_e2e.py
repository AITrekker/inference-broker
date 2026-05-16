"""End-to-end broker tests using the mock provider — no API keys required."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sealedx.broker import runtime
from sealedx.grants.manager import _persist as persist_grant
from sealedx.grants.manager import create_grant, load_grant, revoke
from sealedx.packaging.builder import package
from sealedx.receipts.models import ReceiptStatus
from sealedx.receipts.verifier import verify_receipt


def _build_video_planner_package(video_planner_paths):
    return package(
        name="immersive-video-planner",
        version="0.1.0",
        prompt_path=video_planner_paths["prompt"],
        input_schema_path=video_planner_paths["input_schema"],
        output_schema_path=video_planner_paths["output_schema"],
    )


def test_e2e_succeeds_with_mock_fixture(video_planner_paths):
    pkg = _build_video_planner_package(video_planner_paths)
    grant = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("5"),
        expires_in="1h",
    )
    inp = json.loads(video_planner_paths["input"].read_text())

    result = runtime.execute(
        package_id=pkg.package_id,
        grant_id=grant.grant_id,
        input=inp,
    )
    assert result.receipt.status == ReceiptStatus.succeeded
    assert result.output is not None
    assert result.output["title"] == "Building the Colosseum: Rome's Greatest Stage"
    # Six scenes summing to 90 seconds
    durations = [s["duration_seconds"] for s in result.output["scenes"]]
    assert sum(durations) == 90


def test_e2e_receipt_verifies(video_planner_paths):
    pkg = _build_video_planner_package(video_planner_paths)
    grant = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("5"),
        expires_in="1h",
    )
    inp = json.loads(video_planner_paths["input"].read_text())

    result = runtime.execute(
        package_id=pkg.package_id,
        grant_id=grant.grant_id,
        input=inp,
    )
    verification = verify_receipt(Path(result.receipt_path))
    assert verification.signature_valid
    assert verification.ok
    assert verification.hash_checks["prompt_hash"]
    assert verification.hash_checks["input_schema_hash"]
    assert verification.hash_checks["output_schema_hash"]
    assert verification.hash_checks["output_hash"]


def test_invalid_input_rejected_with_receipt(video_planner_paths):
    pkg = _build_video_planner_package(video_planner_paths)
    grant = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("5"),
        expires_in="1h",
    )
    bad_input = {"topic": "x"}  # missing required fields

    result = runtime.execute(
        package_id=pkg.package_id,
        grant_id=grant.grant_id,
        input=bad_input,
    )
    assert result.receipt.status == ReceiptStatus.invalid_input
    # Even on failure, the receipt is signed and verifiable
    verification = verify_receipt(Path(result.receipt_path))
    assert verification.signature_valid
    # Grant should not have been charged
    assert load_grant(grant.grant_id).spent_usd == Decimal("0")


def test_expired_grant_rejected(video_planner_paths):
    pkg = _build_video_planner_package(video_planner_paths)
    grant = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("5"),
        expires_in="1h",
    )
    # Backdate the grant past expiry without sleeping.
    expired = grant.model_copy(
        update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    persist_grant(expired)

    inp = json.loads(video_planner_paths["input"].read_text())
    result = runtime.execute(
        package_id=pkg.package_id,
        grant_id=grant.grant_id,
        input=inp,
    )
    assert result.receipt.status == ReceiptStatus.grant_expired


def test_revoked_grant_rejected(video_planner_paths):
    pkg = _build_video_planner_package(video_planner_paths)
    grant = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("5"),
        expires_in="1h",
    )
    revoke(grant.grant_id)
    inp = json.loads(video_planner_paths["input"].read_text())
    result = runtime.execute(
        package_id=pkg.package_id,
        grant_id=grant.grant_id,
        input=inp,
    )
    assert result.receipt.status == ReceiptStatus.grant_revoked


def test_budget_exhausted_rejected(video_planner_paths):
    pkg = _build_video_planner_package(video_planner_paths)
    # Budget so small that the mock provider's cost exceeds it.
    # Mock cost = 0.000001 * (tokens_in + tokens_out). Roman colosseum demo uses ~1.2k tokens
    # so cost is ~$0.0012. Budget = $0.0001 << $0.0012.
    grant = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("0.0001"),
        expires_in="1h",
    )
    inp = json.loads(video_planner_paths["input"].read_text())
    result = runtime.execute(
        package_id=pkg.package_id,
        grant_id=grant.grant_id,
        input=inp,
    )
    assert result.receipt.status == ReceiptStatus.budget_exceeded


def test_grant_provider_mismatch_rejected(video_planner_paths):
    """Package requires a specific provider; grant uses another -> policy_denied."""
    from sealedx.packaging.builder import package as build_pkg

    pkg = build_pkg(
        name="immersive-video-planner",
        version="0.1.0",
        prompt_path=video_planner_paths["prompt"],
        input_schema_path=video_planner_paths["input_schema"],
        output_schema_path=video_planner_paths["output_schema"],
        required_provider="anthropic",
    )
    grant = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("5"),
        expires_in="1h",
    )
    inp = json.loads(video_planner_paths["input"].read_text())
    result = runtime.execute(
        package_id=pkg.package_id,
        grant_id=grant.grant_id,
        input=inp,
    )
    assert result.receipt.status == ReceiptStatus.policy_denied


def test_no_prompt_in_logs(video_planner_paths, caplog, capsys):
    """The full broker pipeline must not emit prompt bytes at INFO level."""
    pkg = _build_video_planner_package(video_planner_paths)
    grant = create_grant(
        provider="mock",
        model="mock-claude-sonnet-4-5",
        budget_usd=Decimal("5"),
        expires_in="1h",
    )
    inp = json.loads(video_planner_paths["input"].read_text())

    # The marker is the first sentence of the immersive-video-planner prompt.
    prompt_text = video_planner_paths["prompt"].read_text()
    prompt_marker = prompt_text.split(".")[0]

    import logging

    with caplog.at_level(logging.INFO, logger="sealedx"):
        runtime.execute(package_id=pkg.package_id, grant_id=grant.grant_id, input=inp)

    captured = capsys.readouterr()
    haystack = caplog.text + captured.out + captured.err
    assert prompt_marker not in haystack
