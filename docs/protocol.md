# Protocol

This document defines the wire-stable data types of `sealedx`. Field names and shapes here are normative; the Pydantic models in `sealedx/` follow this document, not the other way around.

## Conventions

- **Encoding.** UTF-8 JSON. ASCII-safe is not required.
- **Canonicalization.** Where a hash or a signature covers a JSON object, the canonical form is: keys sorted lexicographically, separators `(",", ":")`, ensure_ascii=False, no trailing newline.
- **Hashes.** Lowercase hex, prefixed with the algorithm. Currently `sha256:<64-hex>`.
- **Timestamps.** ISO-8601 in UTC, with `Z` suffix. Microsecond precision is allowed but not required.
- **IDs.** `pkg_<uuid4>`, `grant_<uuid4>`, `exec_<uuid4>`. UUIDv4, lowercase, no dashes stripped.
- **Money.** USD as decimal strings (e.g. `"0.0123"`). Floats are not used for money fields.
- **Versions.** This document is `protocol_version: 0.1`. Forward-incompatible changes bump the major; field additions with sensible defaults bump the minor.

## 1. WorkflowPackage

The vendor's published artifact. The `prompt_hash`/`input_schema_hash`/`output_schema_hash` are content-addressed; equal hashes mean byte-equal artifacts.

```json
{
  "protocol_version": "0.1",
  "package_id": "pkg_8a4c0e6e9c4b4a8e9c1b2a3d4e5f6071",
  "name": "immersive-video-planner",
  "version": "0.1.0",
  "publisher": "AITrekker",
  "license": "Apache-2.0",
  "prompt_hash": "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "input_schema_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "output_schema_hash": "sha256:2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
  "required_provider": null,
  "required_models": null,
  "created_at": "2026-05-15T00:00:00Z"
}
```

Notes:

- The prompt body itself is **not** part of the package document. It lives next to the package on disk and is referenced via its hash. This makes it possible to publish a package document without disclosing the prompt — relevant for the future case where package documents travel through a marketplace.
- `required_provider` is `null` to mean "any"; setting it to `"anthropic"` would refuse execution against an OpenAI grant.
- `required_models` is `null` for "any" or a list to constrain; the broker checks `grant.model in required_models`.

## 2. ExecutionGrant

The customer's bounded authorization. A grant carries no API key.

```json
{
  "protocol_version": "0.1",
  "grant_id": "grant_3c4f3e7e1b2a4b3c8d9e0f1a2b3c4d5e",
  "provider": "mock",
  "model": "mock-claude-sonnet-4-5",
  "budget_usd": "5.0000",
  "spent_usd": "0.0000",
  "expires_at": "2026-05-15T01:00:00Z",
  "allowed_models": null,
  "created_at": "2026-05-15T00:00:00Z",
  "status": "active"
}
```

State transitions:

- `active → expired` when wall clock passes `expires_at`.
- `active → exhausted` when `spent_usd >= budget_usd` after a charge.
- `active → revoked` only by explicit user action (`sealedx grant revoke <id>`).

The broker reads `status` derived from current state; persisted `status` is updated at the next mutation.

## 3. ExecutionRequest (in-memory, not persisted)

```json
{
  "request_id": "req_...",
  "package_id": "pkg_...",
  "grant_id": "grant_...",
  "input": { "...": "..." },
  "requested_at": "2026-05-15T00:00:00Z"
}
```

## 4. ExecutionResult

```json
{
  "result_id": "exec_...",
  "status": "succeeded",
  "output": { "...": "..." },
  "output_hash": "sha256:...",
  "error": null
}
```

`status` enum: `succeeded`, `invalid_input`, `invalid_output`, `budget_exceeded`, `grant_expired`, `provider_error`, `policy_denied`. Failed results carry `output: null` and a redacted `error` string.

## 5. ExecutionReceipt

Canonical, signed. Source of truth for audit and reconciliation.

```json
{
  "protocol_version": "0.1",
  "receipt_version": "0.1",
  "execution_id": "exec_4f5b6c7d8e9f0a1b2c3d4e5f60718293",
  "workflow_package_id": "pkg_8a4c0e6e9c4b4a8e9c1b2a3d4e5f6071",
  "workflow_name": "immersive-video-planner",
  "workflow_version": "0.1.0",
  "prompt_hash": "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "input_schema_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "output_schema_hash": "sha256:2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
  "input_hash": "sha256:6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
  "output_hash": "sha256:d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
  "provider": "mock",
  "model": "mock-claude-sonnet-4-5",
  "tokens_in": 1234,
  "tokens_out": 567,
  "estimated_cost_usd": "0.0123",
  "budget_usd": "5.0000",
  "started_at": "2026-05-15T00:00:00Z",
  "completed_at": "2026-05-15T00:00:00.412Z",
  "status": "succeeded",
  "policy_flags": [],
  "broker_public_key_id": "broker-dev-key-1",
  "broker_signature": "base64-encoded-ed25519-signature"
}
```

Field semantics:

- `prompt_hash`, `input_schema_hash`, `output_schema_hash` are copied from the package; they pin the executed package version.
- `input_hash` is over the canonical JSON of the request input.
- `output_hash` is over the canonical JSON of the result output. For non-`succeeded` statuses, this field is `null`.
- `provider`, `model`, `tokens_in`, `tokens_out` are taken from the adapter response, **not** from the grant request. This means the receipt records what actually ran, not what was asked.
- `estimated_cost_usd` is computed by the adapter using `cost_table`; it is `null` when token counts are unavailable.
- `budget_usd` records the grant's full budget at execution time, **not** the remaining budget — useful for downstream auditing.
- `policy_flags` is a list of strings. Empty in v0 unless an opt-in policy hook is installed. Reserved values: `usage_unavailable`, `output_schema_warn`, `cost_estimated`.
- `broker_public_key_id` identifies the broker's signing key. v0 ships `broker-dev-key-1` for demo purposes; production uses key IDs that map to a published key registry.

### Signature

The receipt is canonicalized (see Conventions) **with the `broker_signature` key removed**, then signed with Ed25519. The resulting 64-byte signature is base64-encoded (standard, padded).

```
canonical_bytes = canonical_json(receipt without broker_signature)
broker_signature = base64(Ed25519_Sign(broker_private_key, canonical_bytes))
```

Verification reverses this:

```
canonical_bytes = canonical_json(receipt without broker_signature)
ok = Ed25519_Verify(broker_public_key, canonical_bytes, base64_decode(broker_signature))
```

A verification implementation must also (where artifacts are available locally) re-derive `prompt_hash`, `input_schema_hash`, `output_schema_hash`, `input_hash`, `output_hash` from the artifacts and compare.

## 6. Vendor-side receipt (sketch, v0.2)

Not implemented in v0.1. Defined here so the v0 receipt schema does not back us into a corner.

```json
{
  "protocol_version": "0.1",
  "receipt_version": "0.1-vendor",
  "execution_id": "exec_...",
  "workflow_package_id": "pkg_...",
  "workflow_name": "immersive-video-planner",
  "workflow_version": "0.1.0",
  "prompt_hash": "sha256:...",
  "tokens_in": 1234,
  "tokens_out": 567,
  "started_at": "2026-05-15T00:00:00Z",
  "broker_public_key_id": "broker-dev-key-1",
  "broker_signature": "base64-..."
}
```

It deliberately omits provider name, model, customer-identifying fields, costs, and budgets. The vendor learns "my package was executed N times for these many tokens" — enough for usage-based billing, nothing more.

## 7. Versioning policy

- Adding a field with a default value: minor bump (`0.1 → 0.2`). Old verifiers can ignore unknown fields if they verify against the canonical bytes they were given (which is what they should do).
- Removing or renaming a field: major bump.
- Changing the canonicalization rule: major bump.
- Changing the signature algorithm: major bump and a new `broker_public_key_id` namespace.

## 8. Reference test vectors

`tests/unit/test_canonical.py` and `tests/unit/test_receipt_signing.py` lock down the canonical serialization and a sign/verify roundtrip with a known keypair. If a future change breaks these vectors, that is a protocol break and must bump the major version.
