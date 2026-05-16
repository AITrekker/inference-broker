# Threat Model

This document describes what `sealedx` v0 protects against, what it does not, and what a production deployment would need to add. The honesty of this section is the credibility of the project — please flag anything that reads as overclaim.

## Assets

| ID | Asset | Owner | Sensitivity |
|---|---|---|---|
| A1 | Workflow prompt | Vendor | High — IP. |
| A2 | Workflow input/output schemas | Vendor | Low — published with package metadata. |
| A3 | Provider API key (OpenAI/Anthropic/HF) | Customer | High — billable, long-lived. |
| A4 | Grant document (provider, model, budget, expiry) | Customer | Medium — does not contain the API key. |
| A5 | Customer input data | Customer | Variable — depends on workflow. |
| A6 | Workflow output | Customer | Variable. |
| A7 | Execution receipt | Both | Medium — used for billing reconciliation and audit. |
| A8 | Broker signing key | Broker | High — forging receipts. |

## Trust boundaries

```
[ Vendor host ] -- (publish package) --> [ Broker host ] <-- (input + grant ref) -- [ Customer host ]
                                              |
                                              v
                                       [ Provider API ]
```

In v0 the broker host is a **shared trust boundary** — both vendor and customer place trust in whoever runs the broker. Production replaces this with confidential compute + remote attestation so that neither vendor nor customer needs to trust the broker operator beyond "it is running this signed enclave image."

## Adversaries

- **AC — Casual customer.** Runs the CLI, reads stdout/stderr, reads receipts. Does not poke at process memory or filesystem state.
- **AV — Casual vendor.** Receives usage receipts. Does not have access to the broker host.
- **DC — Determined customer.** Has shell access on the broker host (e.g. they self-host the broker). Reads disk and memory.
- **MB — Malicious broker operator.** Modifies the broker code or runtime, exfiltrates prompts and keys.
- **MH — Malicious host.** Hypervisor / cloud admin / sysadmin with arbitrary access to the broker process.
- **RP — Receipt forger.** Wants to fabricate a receipt or alter an existing one.
- **NO — Network observer.** Passive on the wire between broker and provider.
- **MP — Malicious provider.** Logs, retains, or exfiltrates prompts that pass through it.
- **AB — Abuser.** Publishes a malicious package or issues a malicious workflow.

## Threats and mitigations

| # | Threat | Adversary | v0 mitigation | Production mitigation | Residual risk in v0 |
|---|---|---|---|---|---|
| T1 | Customer reads vendor prompt via ordinary CLI output | AC | No customer-facing CLI command renders the prompt; `package show` returns hashes only. Logger redacts prompt at INFO level. | Same. | None for AC. |
| T2 | Customer reads vendor prompt off the broker disk | DC | Prompt files written mode 0600, but readable by anyone who can run the broker as the broker user. **Not mitigated**; explicitly acknowledged. | Confidential-compute enclave with sealed prompt bundles; prompt is decrypted only inside the enclave. | High. This is the main reason v0 is "trust-based broker." |
| T3 | Vendor exfiltrates customer API key via package contents or workflow output | AV | Keys never enter packages, grants, or receipts. Adapters read keys from env at call time. Receipts contain provider name, model, and token counts — never key bytes. | Same; plus provider-native delegated execution where the vendor never holds anything resembling a key. | Low. Output-channel exfiltration via the model itself is the one residual path; mitigated only by output-schema validation. |
| T4 | Accidental log leakage of prompt or key | AC, AV | Redacting logger; `--unsafe-debug-prompt` is the only flag that may render prompt bytes, and prints a warning. Tests assert no prompt bytes appear in captured logs. | Same; plus structured-log SIEM ingestion with redaction sinks. | Low. |
| T5 | Receipt forgery / tampering | RP | Ed25519 signature over canonical JSON. `receipt verify` re-derives prompt/input/output hashes from on-disk artifacts when present. | Same; plus public transparency log so any receipt can be witness-cosigned and globally verified. | Low — assumes broker signing key is not compromised (T8). |
| T6 | Broker misreports provider, model, or cost in receipts | DC, MB | Receipt fields come from the adapter's response object, not the grant request. Provider name and model are signed. | Same; plus provider-native attested execution receipts that the broker passes through. | Medium under MB — a malicious broker could lie about model or cost; only catchable by reconciling against the customer's provider invoice. |
| T7 | Replay of expired or exhausted grant | AC | Broker checks `expires_at` and `spent_usd >= budget_usd` at execution time. Charge is committed before the receipt is signed. | Same; plus customer-signed grants with serial numbers that the broker submits to a transparency log. | Low. |
| T8 | Broker signing key compromise | MB, MH | Generated on first use; mode 0600. Key is per-broker-instance and identified by `broker_public_key_id`. | HSM / KMS-backed key, or key produced inside an attested enclave and never exported. | High under MH — there is no key custody story in v0 beyond filesystem permissions. |
| T9 | Determined customer extracts prompt by getting the model to echo it | DC, AC | **Not mitigated.** Output-schema validation rejects free-form text where structured output is expected, which raises the cost of casual extraction but does not prevent a determined attempt. | Output classifier / regex filter for high-mutual-information overlap with prompt; provider-side tool that refuses to echo the system prompt. | High where the prompt is high-value and the model is cooperative. |
| T10 | Provider-side prompt retention | MP | **Not mitigated.** The provider always sees the prompt. | Provider-side enclave inference, or BYOK + customer-controlled retention policy. | Medium — depends on provider. |
| T11 | Network observer sees prompt | NO | TLS via provider SDK. No additional in-transit confidentiality from `sealedx`. | Same; certificate pinning optional. | Low — assumes TLS. |
| T12 | Side-channel timing / token-count leakage | DC | **Not mitigated.** Token counts are recorded in receipts by design. | Coarse-grained billing aggregation; token-count rounding. | Low for most workloads. |
| T13 | Schema drift between package and execution | AC | `input_schema_hash` and `output_schema_hash` are part of the package and the receipt. Verification re-hashes. | Same. | Low. |
| T14 | Malicious workflow package (prompt injection, abuse) | AB | **Not mitigated.** v0 has no vendor verification. | Vendor KYC, content scanning, package-class allowlists, runtime classifiers, report-and-takedown. | High in any open marketplace; deferred. |
| T15 | Malicious customer input (jailbreak, exfiltration attempt) | AC | Output schema validation rejects non-conforming output, which catches some exfiltration attempts. | Provider-side and broker-side classifiers; rate limits per grant. | Medium. |
| T16 | Broker host compromise (RAM scrape, disk exfil) | MH, MB | **Not mitigated.** | Confidential VM with measured boot + remote attestation, sealed prompt bundles. | Critical without confidential compute. This is the core reason production needs CC. |
| T17 | Replay of receipt as evidence of an execution that did not happen | RP, MB | Receipts contain UUID `execution_id`, `started_at`, `completed_at`, prompt/input/output hashes. Verification is local. | Public transparency log of receipt hashes; verifiers check inclusion. | Medium — locally a receipt can prove "the broker key signed this" but not "this is unique" without a log. |
| T18 | Customer learns vendor's identity / pricing through error messages | AC | Errors are converted to typed `SealedxError` with redacted messages; underlying causes go to local logs only. | Same. | Low. |
| T19 | Vendor learns customer's identity through usage receipts | AV | v0 currently emits one receipt and stores it locally on the broker host; no automatic fan-out to vendor. The roadmapped vendor-side receipt deliberately omits customer identifying fields. | Same; deliver via a privacy-preserving aggregation channel. | N/A in v0 because vendor receipts are not yet implemented. |

## Threats explicitly out of scope for v0

T2, T9, T10, T14, T16, T17 each have residual risk that v0 does **not** attempt to close. They are the primary content of the production roadmap. Stating them clearly is the point of this document.

## Cryptographic choices

- **Hash:** SHA-256 over canonical JSON serialization (sorted keys, no whitespace, UTF-8).
- **Signature:** Ed25519 (RFC 8032, via `pynacl`).
- **Encoding:** base64 (standard, padded) for signature; lowercase hex for hashes; hashes are namespaced as `sha256:<hex>` to enable algorithm migration.
- **Key generation:** on first broker use, via `nacl.signing.SigningKey.generate()`. Keys persist as raw 32-byte seeds at mode 0600.

These are conservative defaults — Ed25519 specifically because deterministic signatures simplify reproducibility tests. There is no key rotation in v0; the broker has one keypair, identified by `broker_public_key_id`. Rotation is a v0.2 item.

## Verification model

A receipt is verified by:

1. Loading the receipt JSON.
2. Removing the `broker_signature` field.
3. Canonicalizing the remaining object (sorted keys, no whitespace).
4. Looking up the broker's public key by `broker_public_key_id` (in v0, from the local keys directory).
5. Verifying the Ed25519 signature against the canonical bytes.
6. Optionally re-deriving `prompt_hash`, `input_schema_hash`, `output_schema_hash`, `input_hash`, `output_hash` from on-disk artifacts and comparing.

A successful verification proves: "This broker key signed this exact set of fields." Whether the broker key is trusted, and whether the receipt is unique (not a replay), is out of scope for local verification — those are roadmap items (transparency log + key-binding).

## What "production" means here

References to "production" in this document and the README assume at least:

1. Confidential-compute execution environment with remote attestation.
2. Sealed prompt bundles encrypted to the enclave's attestation key.
3. Customer-signed grants delivered as bearer tokens, validated offline by the broker.
4. Provider-native delegated execution if/when providers ship it.
5. Tamper-evident receipt log with public witnesses.
6. KMS or HSM-backed broker signing keys with rotation.
7. Vendor verification and abuse controls at the marketplace layer.

`sealedx` v0 is a faithful prototype of items (3) and (5)'s data model and a placeholder for (1), (2), (6). It is not production.
