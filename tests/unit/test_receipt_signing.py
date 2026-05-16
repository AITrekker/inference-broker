"""Receipt sign/verify roundtrip + tamper detection.

These tests build a synthetic receipt directly via the issuer (no broker runtime),
so they isolate the cryptographic surface from the orchestration logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from nacl.signing import SigningKey

from sealedx.receipts.issuer import issue_receipt
from sealedx.receipts.models import ReceiptStatus
from sealedx.receipts.verifier import verify_receipt
from sealedx.security.keys import BrokerKeypair
from sealedx.storage.paths import atomic_write_json, keys_dir, receipts_dir


def _keypair() -> BrokerKeypair:
    sk = SigningKey.generate()
    return BrokerKeypair(key_id="broker-test-key-1", signing_key=sk, verify_key=sk.verify_key)


def _persist_keypair(kp: BrokerKeypair) -> None:
    """Persist the test keypair where the verifier expects it."""
    kdir = keys_dir()
    (kdir / "broker_ed25519.seed").write_bytes(kp.signing_key.encode())
    (kdir / "broker_ed25519.pub").write_bytes(bytes(kp.verify_key))


def _sample_fields(now: datetime) -> dict:
    return {
        "execution_id": "exec_test",
        "workflow_package_id": "pkg_test",
        "workflow_name": "test-flow",
        "workflow_version": "0.1.0",
        "prompt_hash": "sha256:" + "a" * 64,
        "input_schema_hash": "sha256:" + "b" * 64,
        "output_schema_hash": "sha256:" + "c" * 64,
        "input_hash": "sha256:" + "d" * 64,
        "output_hash": "sha256:" + "e" * 64,
        "provider": "mock",
        "model": "mock-claude-sonnet-4-5",
        "tokens_in": 100,
        "tokens_out": 50,
        "estimated_cost_usd": Decimal("0.0150"),
        "budget_usd": Decimal("5.0000"),
        "started_at": now,
        "completed_at": now,
        "status": ReceiptStatus.succeeded,
        "policy_flags": ["cost_estimated:2026-05-15"],
    }


def test_sign_verify_roundtrip(monkeypatch):
    kp = _keypair()
    now = datetime.now(UTC)
    receipt = issue_receipt(keypair=kp, receipt_fields=_sample_fields(now))

    # Persist the receipt and the broker public key under the test SEALEDX_HOME
    receipt_path = receipts_dir() / f"{receipt.execution_id}.json"
    atomic_write_json(receipt_path, receipt.model_dump(mode="json"))
    _persist_keypair(kp)
    monkeypatch.setenv("SEALEDX_BROKER_KEY_ID", kp.key_id)

    result = verify_receipt(receipt_path)
    assert result.signature_valid
    # No package on disk in this test, so hash re-derivations are skipped.
    assert result.errors == [] or all("could not re-derive" in e for e in result.errors)


def test_tampered_field_breaks_signature(monkeypatch):
    kp = _keypair()
    now = datetime.now(UTC)
    receipt = issue_receipt(keypair=kp, receipt_fields=_sample_fields(now))

    tampered = receipt.model_dump(mode="json")
    tampered["estimated_cost_usd"] = "9.9999"  # bump the cost

    receipt_path = receipts_dir() / f"{receipt.execution_id}.json"
    atomic_write_json(receipt_path, tampered)
    _persist_keypair(kp)
    monkeypatch.setenv("SEALEDX_BROKER_KEY_ID", kp.key_id)

    result = verify_receipt(receipt_path)
    assert not result.signature_valid


def test_signature_is_over_all_signed_fields(monkeypatch):
    """Tampering policy_flags should also break the signature."""
    kp = _keypair()
    now = datetime.now(UTC)
    receipt = issue_receipt(keypair=kp, receipt_fields=_sample_fields(now))

    tampered = receipt.model_dump(mode="json")
    tampered["policy_flags"] = ["nothing-to-see-here"]

    receipt_path = receipts_dir() / f"{receipt.execution_id}.json"
    atomic_write_json(receipt_path, tampered)
    _persist_keypair(kp)
    monkeypatch.setenv("SEALEDX_BROKER_KEY_ID", kp.key_id)

    result = verify_receipt(receipt_path)
    assert not result.signature_valid
