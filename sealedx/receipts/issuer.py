"""Build, canonicalize, and sign execution receipts.

Strategy: build the receipt model with a placeholder signature, dump to JSON via
Pydantic (the same form that gets persisted), strip the signature field, canonicalize,
sign. Verify is the symmetric operation. This guarantees the bytes signed equal the
bytes the verifier sees on disk modulo the signature field — no datetime/decimal
formatting drift.
"""

from __future__ import annotations

import base64
from typing import Any

from sealedx.receipts.canonical import canonical_json_bytes
from sealedx.receipts.models import ExecutionReceipt
from sealedx.security.keys import BrokerKeypair

_PLACEHOLDER_SIG = ""


def _signing_payload(receipt_dict: dict[str, Any]) -> bytes:
    """The canonical bytes covered by ``broker_signature``.

    ``receipt_dict`` is a Pydantic-dumped JSON-mode dict — every value is already
    a JSON-safe primitive. We strip the signature and canonicalize the rest.
    """
    payload = dict(receipt_dict)
    payload.pop("broker_signature", None)
    return canonical_json_bytes(payload)


def issue_receipt(
    *,
    keypair: BrokerKeypair,
    receipt_fields: dict[str, Any],
) -> ExecutionReceipt:
    """Sign ``receipt_fields`` and return a fully populated :class:`ExecutionReceipt`."""
    receipt_fields = dict(receipt_fields)
    receipt_fields["broker_public_key_id"] = keypair.key_id
    receipt_fields["broker_signature"] = _PLACEHOLDER_SIG

    # Validate, then dump to the same JSON-mode shape that gets persisted.
    unsigned_model = ExecutionReceipt.model_validate(receipt_fields)
    unsigned_dict = unsigned_model.model_dump(mode="json")

    payload = _signing_payload(unsigned_dict)
    sig = keypair.signing_key.sign(payload).signature
    sig_b64 = base64.b64encode(sig).decode("ascii")

    signed_dict = dict(unsigned_dict)
    signed_dict["broker_signature"] = sig_b64
    return ExecutionReceipt.model_validate(signed_dict)
