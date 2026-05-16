# Limitations

Reading this document should *increase* your confidence in the rest of the project. Listing weaknesses honestly is the point.

## What v0 is not

`sealedx` v0 is a **trust-based broker prototype**. It standardizes the protocol — package, grant, receipt — and ships a working reference implementation. It is **not** a confidential-compute system, and it does not attempt to be one.

If the broker host is compromised, the prompt is exposed. If the customer self-hosts the broker, the prompt is on their disk. Stating this clearly is the v0 posture.

## Specific limitations

### Confidentiality

- **Broker disk access defeats prompt confidentiality.** The prompt is written to `~/.sealedx/packages/<id>/prompt.md` mode 0600. Any process running as the broker user can read it.
- **Memory inspection defeats prompt confidentiality.** No memory protection.
- **The provider always sees the prompt.** Provider-side prompt retention, training-on-data, and logging are all out of scope.
- **The model can be coaxed into echoing the prompt.** Output-schema validation raises the cost of casual extraction; it does not prevent a determined attempt.

### Authentication and authorization

- **No vendor verification.** Anyone can publish a package. Production needs vendor identity, KYC for high-risk packages, and report-and-takedown.
- **No customer authentication.** Grants are local artifacts; there is no notion of a customer account or session in v0.
- **No grant-binding to broker instances.** A grant on broker A could in principle be replayed on broker B if both share the customer's environment. Production answer: customer-signed grants with a target-broker claim.

### Key custody

- **Broker signing key is a file.** Mode 0600, but no HSM, no rotation, no revocation list. If the key leaks, an attacker can forge receipts indefinitely until the key is manually rotated.
- **Provider keys are environment variables.** Read at execute-time, never persisted, but: the broker process reads them, and a compromised broker process can exfiltrate them. Production needs short-lived tokens (OAuth, customer-managed key release) instead of long-lived API keys.

### Auditability

- **Receipts are local files.** No transparency log. A broker could in principle issue, delete, or refuse to surface receipts. Production needs a public, append-only log with witness cosignatures (Sigsum / Rekor-class).
- **No vendor-side receipts in v0.** Defined in `docs/protocol.md` §6 but not implemented. Vendor billing reconciliation is therefore manual in v0.
- **No reconciliation tooling.** The receipts contain enough to reconcile against provider invoices, but `sealedx` does not ship a reconciliation command in v0.

### Operational

- **Single-process, JSON-on-disk.** No daemon, no DB, no concurrency story. Two `sealedx broker execute` invocations in parallel against the same grant could race the budget check; the last writer wins. Acceptable for a CLI prototype, not for a multi-tenant service.
- **No streaming.** Request/response only. Streaming receipts are a non-trivial protocol design problem; deferred.
- **No retry layer in the broker.** Adapters retry per-provider. If an adapter does not retry, the broker does not either.
- **No rate limiting.** Provider rate-limit errors surface as `provider_error` receipts and that's it.

### Schema and policy

- **JSON Schema only.** No Pydantic-source-of-truth schema, no Protobuf, no Avro. Workable for v0; constraining for sophisticated workflows.
- **Output validation is best-effort.** Some providers' structured-output modes return text that passes JSON parse but does not match the declared schema. The broker rejects with `invalid_output` in that case; this is not the most graceful UX.
- **No content classifier hooks installed.** The framework is in place (`sealedx/broker/runtime.py` calls policy hooks), but no default hooks ship.

### Cost accounting

- **Cost table is hard-coded and dated.** Receipts mark `cost_estimated:<as_of>` so consumers know. Production should pull rates from the provider's billing API.
- **`tokens_in` / `tokens_out` come from the provider.** If the provider misreports, the broker faithfully misreports.

### Cryptographic

- **One signature algorithm (Ed25519).** No agility. Algorithm change requires a major protocol bump.
- **Canonical JSON is custom.** It follows widely-used conventions (sorted keys, no whitespace, ensure_ascii=False) but is not RFC 8785 compliant. Test vectors lock the current behavior. Migration to RFC 8785 is a non-breaking option later.

### Marketplace and abuse

- **No marketplace.** Packages are local artifacts. Distribution mechanics — discovery, ratings, reporting, takedowns — are all out of scope.
- **No abuse signals.** A malicious package could attempt to exfiltrate input via the model's output. `policy_flags` is the place where future abuse signals would surface; v0 does not surface any.

## What this project deliberately does *not* claim

- It does not claim to make prompts confidential against a malicious broker. (Production roadmap.)
- It does not claim to prevent prompt extraction via the model. (Open research.)
- It does not claim provider-side privacy. (That is a provider feature.)
- It does not claim to be production-ready. (It is not.)
- It does not claim to be a final protocol design. (It is a credible v0 that will evolve.)

If a reader of this document concludes "this person knows what they didn't build, and why" — that is the goal.
