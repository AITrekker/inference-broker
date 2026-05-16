"""Verify a receipt's signature and re-derive its content hashes."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from sealedx.packaging.registry import (
    read_input_schema,
    read_output_schema,
    read_prompt,
)
from sealedx.receipts.canonical import canonical_json_bytes
from sealedx.security.hashing import hash_canonical_json, hash_text
from sealedx.security.keys import load_verify_key
from sealedx.storage.paths import keys_dir, read_json, results_dir


@dataclass
class VerificationResult:
    ok: bool
    signature_valid: bool
    hash_checks: dict[str, bool]
    errors: list[str]

    def summary(self) -> str:
        lines = [f"signature: {'OK' if self.signature_valid else 'INVALID'}"]
        for name, ok in self.hash_checks.items():
            lines.append(f"{name}: {'match' if ok else 'MISMATCH'}")
        if self.errors:
            lines.append("errors:")
            for e in self.errors:
                lines.append(f"  - {e}")
        return "\n".join(lines)


def _verify_signature(
    receipt_fields: dict[str, Any],
    verify_key: VerifyKey,
) -> tuple[bool, str | None]:
    sig_b64 = receipt_fields.get("broker_signature")
    if not sig_b64:
        return False, "receipt missing broker_signature"
    payload = dict(receipt_fields)
    payload.pop("broker_signature")
    canonical = canonical_json_bytes(payload)
    try:
        verify_key.verify(canonical, base64.b64decode(sig_b64))
    except BadSignatureError:
        return False, "signature does not verify"
    except Exception as e:  # noqa: BLE001
        return False, f"signature verification failed: {e}"
    return True, None


def verify_receipt(
    receipt_path: Path,
    *,
    verify_key: VerifyKey | None = None,
) -> VerificationResult:
    """Verify a receipt at ``receipt_path``.

    Re-derives prompt / input-schema / output-schema / output hashes from local
    artifacts where possible. Verifies the Ed25519 signature against the broker's
    published public key (loaded from ``$SEALEDX_HOME/keys`` unless ``verify_key``
    is supplied).
    """
    errors: list[str] = []
    hash_checks: dict[str, bool] = {}
    receipt_fields = read_json(receipt_path)

    if verify_key is None:
        try:
            _, verify_key = load_verify_key(keys_dir())
        except FileNotFoundError as e:
            return VerificationResult(False, False, {}, [str(e)])

    sig_ok, sig_err = _verify_signature(receipt_fields, verify_key)
    if sig_err:
        errors.append(sig_err)

    package_id = receipt_fields.get("workflow_package_id")
    if package_id:
        try:
            prompt = read_prompt(package_id)
            hash_checks["prompt_hash"] = hash_text(prompt) == receipt_fields.get("prompt_hash")
        except Exception as e:  # noqa: BLE001
            errors.append(f"could not re-derive prompt_hash: {e}")
        try:
            schema = read_input_schema(package_id)
            hash_checks["input_schema_hash"] = (
                hash_canonical_json(schema) == receipt_fields.get("input_schema_hash")
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"could not re-derive input_schema_hash: {e}")
        try:
            schema = read_output_schema(package_id)
            hash_checks["output_schema_hash"] = (
                hash_canonical_json(schema) == receipt_fields.get("output_schema_hash")
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"could not re-derive output_schema_hash: {e}")

    execution_id = receipt_fields.get("execution_id")
    if execution_id:
        result_path = results_dir() / f"{execution_id}.json"
        if result_path.exists():
            try:
                result = read_json(result_path)
                output = result.get("output")
                if output is None and receipt_fields.get("output_hash") is None:
                    hash_checks["output_hash"] = True
                elif output is not None:
                    hash_checks["output_hash"] = (
                        hash_canonical_json(output) == receipt_fields.get("output_hash")
                    )
            except Exception as e:  # noqa: BLE001
                errors.append(f"could not re-derive output_hash: {e}")

    all_hashes_ok = all(hash_checks.values()) if hash_checks else True
    return VerificationResult(
        ok=sig_ok and all_hashes_ok,
        signature_valid=sig_ok,
        hash_checks=hash_checks,
        errors=errors,
    )
