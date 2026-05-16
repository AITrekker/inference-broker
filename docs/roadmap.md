# Roadmap

What v0.1 deliberately defers, in roughly the order it would be tackled. Each item below has a one-paragraph rationale and a sketch of where it lands in the existing architecture.

## v0.2 — Closing the obvious gaps

### R-1. Customer-signed execution grants

**Why.** Today the broker is the source of truth for grants. A grant should be a bearer token signed by the customer's key, validated offline by the broker. This makes the broker stateless w.r.t. grants and prevents replay across brokers.

**Where.** New module `sealedx/grants/tokens.py`. `ExecutionGrant` gains a `customer_signature` and a `customer_public_key_id`. The broker's grant manager moves from "create" to "verify."

### R-2. Vendor-side usage receipts

**Why.** A vendor needs to invoice for usage. v0.1 emits one receipt addressed to the customer/auditor; v0.2 emits a paired receipt addressed to the vendor that omits provider, model, costs, and customer-identifying fields. Schema is sketched in `docs/protocol.md` §6.

**Where.** `sealedx/receipts/issuer.py` gains `issue_vendor_receipt`. The CLI gets `sealedx receipt vendor <execution_id>`.

### R-3. Receipt transparency log

**Why.** Locally a receipt proves "the broker key signed this." It does not prove uniqueness or non-equivocation. A public, append-only log with witness cosignatures (Sigsum or Rekor-class) raises auditability dramatically.

**Where.** `sealedx/receipts/transparency.py`. The broker submits receipt hashes to the log post-issuance; verification gains `--check-log`. Reference deployment uses an existing Sigsum witness in v0.2.

### R-4. Hugging Face adapter

**Why.** Diversifies provider coverage; HF Inference Endpoints are a natural target for compliance-conscious customers.

**Where.** `sealedx/providers/huggingface.py`. Mostly mechanical.

### R-5. FastAPI broker service

**Why.** A CLI is the wrong front end for a marketplace integration. A FastAPI service that wraps the existing `sealedx.broker.execute(...)` library function is small and unblocks remote brokerage.

**Where.** New `sealedx/server/` subpackage. The runtime is already library-shaped; this is a wrapper.

### R-6. Broker key rotation

**Why.** v0 has one keypair. Production needs rotation, revocation, and key-binding to broker identity.

**Where.** `sealedx/security/keys.py`. Multi-key registry on disk, `broker_public_key_id` stays the binding identifier. Verifiers pull from a published registry (file → URL → registry service over time).

## v0.3 — Confidentiality

### R-7. Confidential-compute broker

**Why.** This is the headline limitation of v0. Lifting the broker into AWS Nitro Enclaves / GCP Confidential Space / Azure Confidential VMs, with remote attestation and sealed prompt bundles, is what makes the trust model genuinely strong.

**Where.** Two pieces.

1. **Sealed prompt bundles.** `sealedx vendor seal` encrypts the prompt to the broker's attestation key. The encrypted blob travels with the package; the plaintext prompt is decrypted only inside the enclave. New module `sealedx/packaging/sealing.py`.
2. **Attested broker runtime.** A small "enclave entrypoint" that exposes `execute()` over a local channel, holds the decryption key, holds the signing key, and is measured. Customers get an attestation document with each receipt.

This is the largest piece of work on the roadmap. The v0 protocol is designed to absorb it without changes — receipts gain optional `attestation_document` and `enclave_image_digest` fields under a minor version bump.

### R-8. Provider-native delegated execution

**Why.** When providers ship a "run this opaque blob, charge it to grant X" primitive (Bedrock-style customer-managed model invocations + opaque prompts; or signed-payload Anthropic/OpenAI features), the broker collapses to a thin adapter. The protocol survives.

**Where.** New adapter pattern in `sealedx/providers/base.py` for "opaque execution." Existing adapters keep their shape.

### R-9. Output-channel exfiltration controls

**Why.** Today a determined customer can coax the model into echoing the prompt. Mitigations: regex/embedding-overlap classifier on output vs prompt; provider-side "do not echo system prompt" tools; output-schema enforcement.

**Where.** Policy hooks under `sealedx/broker/runtime.py`. The hook framework is already wired; v0.3 ships default hooks.

## v1.0 — Marketplace and operations

### R-10. Vendor verification

KYC for high-risk packages. Domain-bound vendor identities. Verifiable claims.

### R-11. Abuse and content controls

Default classifiers, package-class allowlists, report-and-takedown.

### R-12. Reconciliation tooling

`sealedx reconcile` consumes receipts and a provider invoice; reports discrepancies.

### R-13. Tracing

OpenTelemetry spans for the execution path. Hashes of artifacts as span attributes. Sensitive content never appears in spans.

### R-14. Encrypted local package storage

For environments where on-disk plaintext prompts are a non-starter even in v0 mode. Symmetric encryption keyed by an OS keystore (Keychain on macOS, libsecret on Linux). Optional opt-in.

### R-15. Local LLM adapter

For air-gapped or on-prem use. Wraps `llama.cpp`-style local servers behind the same `ProviderAdapter` interface.

### R-16. Policy hook examples

PII detector, regex content filter, model-response classifier. Shipped as opt-in plugins so default v0 stays minimal.

### R-17. Receipt-driven invoicing for vendors

Programmatic invoicing built off the vendor-side receipts (R-2) + transparency log (R-3).

## Cross-cutting items not tied to a milestone

- **Replace canonical JSON with RFC 8785** (JCS). Non-breaking if the byte-equivalent is preserved on existing inputs; verify with test vectors.
- **mypy strict on the public API.** v0 ships type hints; strict mode is straightforward.
- **Multi-platform packaging.** PyPI publish, brew formula, Docker image. None of these change behavior.
- **Reference broker hosted by AITrekker** — single instance with a published key, opt-in for users who want a hosted path.

## Items deliberately *not* on the roadmap

- Payments / billing / Stripe integration. Not the right layer.
- A UI dashboard. The CLI is the right surface for this protocol; brokers integrate with marketplaces via the API server (R-5).
- Replacing MCP, agent frameworks, or provider SDKs. `sealedx` composes with them.
