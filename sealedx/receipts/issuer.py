"""Build, canonicalize, and sign execution receipts."""

from __future__ import annotations

import base64
from datetime import datetime
from decimal import Decimal
from typing import Any

from sealedx.receipts.canonical import canonical_json_bytes
from sealedx.receipts.models import ExecutionReceipt, ReceiptStatus
from sealedx.security.keys import BrokerKeypair


def _serializable(receipt_fields: dict[str, Any]) -> dict[str, Any]:
    """Convert datetimes / Decimals into JSON-safe primitives matching the wire format."""
    out = {}
    for k, v in receipt_fields.items():
        if isinstance(v, datetime):
            # Always UTC; trailing Z; microseconds preserved
            out[k] = v.astimezone(tz=v.tzinfo).isoformat().replace("+00:00", "Z")
        elif isinstance(v, Decimal):
            out[k] = f"{v:.4f}"
        elif isinstance(v, ReceiptStatus):
            out[k] = v.value
        else:
            out[k] = v
    return out


def _signing_payload(receipt_fields: dict[str, Any]) -> bytes:
    """The canonical bytes covered by the broker signature.

    Excludes ``broker_signature`` (which is the field we're computing) but keeps every
    other field, including ``broker_public_key_id``.
    """
    payload = dict(receipt_fields)
    payload.pop("broker_signature", None)
    return canonical_json_bytes(_serializable(payload))


def issue_receipt(
    *,
    keypair: BrokerKeypair,
    receipt_fields: dict[str, Any],
) -> ExecutionReceipt:
    """Sign ``receipt_fields`` and return a fully populated :class:`ExecutionReceipt`."""
    receipt_fields = dict(receipt_fields)
    receipt_fields["broker_public_key_id"] = keypair.key_id
    payload = _signing_payload(receipt_fields)
    sig = keypair.signing_key.sign(payload).signature
    receipt_fields["broker_signature"] = base64.b64encode(sig).decode("ascii")
    return ExecutionReceipt.model_validate(receipt_fields)
