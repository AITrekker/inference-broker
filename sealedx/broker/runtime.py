"""Broker runtime — the orchestrator that composes packaging, grants, providers, receipts.

This is the only module that ties the whole pipeline together. The CLI calls
:func:`execute`; a future FastAPI server can call the same function unchanged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sealedx.broker.errors import (
    GrantPackageMismatchError,
    ProviderError,
    SealedxError,
)
from sealedx.grants.manager import assert_usable, charge, load_grant
from sealedx.grants.models import ExecutionGrant
from sealedx.packaging.models import WorkflowPackage
from sealedx.packaging.registry import (
    load_package,
    read_input_schema,
    read_output_schema,
    read_prompt,
)
from sealedx.providers.base import ProviderRequest
from sealedx.providers.cost_table import AS_OF as COST_TABLE_AS_OF
from sealedx.providers.registry import get_adapter
from sealedx.receipts.issuer import issue_receipt
from sealedx.receipts.models import ExecutionReceipt, ReceiptStatus
from sealedx.schemas.validate import SchemaValidationError, validate
from sealedx.security.hashing import hash_canonical_json
from sealedx.security.keys import load_or_create_broker_keypair
from sealedx.security.redaction import get_logger
from sealedx.storage.paths import (
    atomic_write_json,
    keys_dir,
    receipts_dir,
    results_dir,
)

log = get_logger("broker.runtime")


@dataclass
class BrokerExecution:
    receipt: ExecutionReceipt
    output: dict[str, Any] | None
    receipt_path: str
    result_path: str | None


def _check_grant_package_compat(grant: ExecutionGrant, pkg: WorkflowPackage) -> None:
    if pkg.required_provider and pkg.required_provider != grant.provider:
        raise GrantPackageMismatchError(
            f"package requires provider {pkg.required_provider!r}, grant uses {grant.provider!r}"
        )
    if pkg.required_models and grant.model not in pkg.required_models:
        raise GrantPackageMismatchError(
            f"grant model {grant.model!r} is not in the package's required_models list"
        )
    if grant.allowed_models and grant.model not in grant.allowed_models:
        raise GrantPackageMismatchError(
            f"grant model {grant.model!r} is not in the grant's allowed_models list"
        )


def _new_execution_id() -> str:
    return "exec_" + uuid.uuid4().hex


def _persist_result(execution_id: str, output: dict[str, Any] | None, status: str) -> str:
    path = results_dir() / f"{execution_id}.json"
    atomic_write_json(
        path,
        {"result_id": execution_id, "status": status, "output": output},
    )
    return str(path)


def _persist_receipt(receipt: ExecutionReceipt) -> str:
    path = receipts_dir() / f"{receipt.execution_id}.json"
    atomic_write_json(path, receipt.model_dump(mode="json"))
    return str(path)


def execute(
    *,
    package_id: str,
    grant_id: str,
    input: dict[str, Any],
) -> BrokerExecution:
    """Execute a workflow package against a grant. Always returns a signed receipt.

    Errors are converted to a non-success receipt — callers can rely on getting a
    :class:`BrokerExecution` back unless something catastrophic happens (e.g. disk
    failure during receipt persistence).
    """

    started_at = datetime.now(UTC)
    execution_id = _new_execution_id()
    keypair = load_or_create_broker_keypair(keys_dir())

    pkg = load_package(package_id)  # may raise PackageNotFoundError
    grant = load_grant(grant_id)    # may raise GrantNotFoundError

    base_fields: dict[str, Any] = {
        "execution_id": execution_id,
        "workflow_package_id": pkg.package_id,
        "workflow_name": pkg.name,
        "workflow_version": pkg.version,
        "prompt_hash": pkg.prompt_hash,
        "input_schema_hash": pkg.input_schema_hash,
        "output_schema_hash": pkg.output_schema_hash,
        "input_hash": hash_canonical_json(input),
        "output_hash": None,
        "provider": grant.provider,
        "model": grant.model,
        "tokens_in": None,
        "tokens_out": None,
        "estimated_cost_usd": None,
        "budget_usd": grant.budget_usd,
        "started_at": started_at,
        "completed_at": started_at,
        "status": ReceiptStatus.internal_error,
        "policy_flags": [],
    }

    def fail(status: ReceiptStatus, *, output: dict[str, Any] | None = None) -> BrokerExecution:
        base_fields["completed_at"] = datetime.now(UTC)
        base_fields["status"] = status
        if output is not None:
            base_fields["output_hash"] = hash_canonical_json(output)
        receipt = issue_receipt(keypair=keypair, receipt_fields=base_fields)
        receipt_path = _persist_receipt(receipt)
        result_path = _persist_result(execution_id, output, status.value)
        return BrokerExecution(
            receipt=receipt,
            output=output,
            receipt_path=receipt_path,
            result_path=result_path,
        )

    try:
        _check_grant_package_compat(grant, pkg)

        try:
            assert_usable(grant)
        except SealedxError as e:
            log.warning("grant unusable: %s", e.code)
            mapping = {
                "grant_expired": ReceiptStatus.grant_expired,
                "grant_exhausted": ReceiptStatus.grant_exhausted,
                "grant_revoked": ReceiptStatus.grant_revoked,
            }
            return fail(mapping.get(e.code, ReceiptStatus.policy_denied))

        # Validate input against the package's declared input schema.
        input_schema = read_input_schema(pkg.package_id)
        try:
            validate(input, input_schema, kind="input")
        except SchemaValidationError as e:
            log.warning("input rejected: %s", e.message)
            base_fields["policy_flags"].append("input_validation_errors:" + str(len(e.errors)))
            return fail(ReceiptStatus.invalid_input)

        # Pull prompt + output schema; these never leave the broker process.
        prompt = read_prompt(pkg.package_id)
        output_schema = read_output_schema(pkg.package_id)

        adapter = get_adapter(grant.provider, package_name=pkg.name)
        if not adapter.supports(grant.model):
            log.warning("model not supported by adapter")
            return fail(ReceiptStatus.policy_denied)

        request = ProviderRequest(
            model=grant.model,
            prompt=prompt,
            input=input,
            response_schema=output_schema,
            request_id=execution_id,
        )

        try:
            response = adapter.complete(request)
        except ProviderError as e:
            log.warning("provider_error code=%s", e.code)
            return fail(ReceiptStatus.provider_error)

        # Token counts and cost
        if response.tokens_in is not None and response.tokens_out is not None:
            base_fields["tokens_in"] = response.tokens_in
            base_fields["tokens_out"] = response.tokens_out
            cost = adapter.estimate_cost_usd(response.tokens_in, response.tokens_out, grant.model)
            base_fields["estimated_cost_usd"] = cost
            base_fields["policy_flags"].append(f"cost_estimated:{COST_TABLE_AS_OF}")
        else:
            base_fields["policy_flags"].append("usage_unavailable")
            cost = Decimal("0")

        # Pre-charge budget check
        try:
            charge(grant, cost)
        except SealedxError:
            log.warning("budget exceeded after provider call")
            return fail(ReceiptStatus.budget_exceeded)

        output = response.parsed_output
        if output is None:
            log.warning("provider returned no parseable JSON output")
            return fail(ReceiptStatus.invalid_output)

        # Validate output against schema
        try:
            validate(output, output_schema, kind="output")
        except SchemaValidationError as e:
            log.warning("output rejected: %s", e.message)
            base_fields["policy_flags"].append("output_validation_errors:" + str(len(e.errors)))
            return fail(ReceiptStatus.invalid_output, output=output)

        # Success
        base_fields["completed_at"] = datetime.now(UTC)
        base_fields["output_hash"] = hash_canonical_json(output)
        base_fields["status"] = ReceiptStatus.succeeded
        receipt = issue_receipt(keypair=keypair, receipt_fields=base_fields)
        receipt_path = _persist_receipt(receipt)
        result_path = _persist_result(execution_id, output, ReceiptStatus.succeeded.value)
        return BrokerExecution(
            receipt=receipt,
            output=output,
            receipt_path=receipt_path,
            result_path=result_path,
        )

    except SealedxError as e:
        # Known typed failure paths whose codes do not map to a receipt status — surface and
        # still emit a receipt so the audit trail is complete.
        log.warning("execution failed code=%s", e.code)
        return fail(ReceiptStatus.policy_denied)
