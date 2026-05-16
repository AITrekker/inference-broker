# Product Requirements Document — Sealed Workflow Execution (`sealedx`)

**Status:** Draft v0.1 · **Author:** AITrekker · **Last updated:** 2026-05-15

---

## 1. Problem statement

The AI developer ecosystem has standardized two layers in the last 18 months:

1. **Connectivity** — MCP, OpenAI Apps/Agents, Anthropic computer use, agent frameworks (LangGraph, CrewAI, etc.) standardize how a model gets access to tools, files, and context.
2. **Inference** — Bedrock, Vertex, Azure AI, and provider-native APIs standardize how an enterprise pays for, governs, and audits model calls under its own account.

A primitive sitting between these two layers is missing: **delegated execution of a private workflow against a customer-owned inference account**.

Concretely, three parties want to compose, but cannot today:

- A **workflow vendor** owns proprietary IP — prompt logic, decomposition strategy, evaluator rubrics, routing policy. This is their product and their moat.
- An **enterprise customer** owns the inference contract — they have an approved provider (OpenAI/Anthropic/Bedrock/Vertex), a budget, a model allowlist, a retention policy, and a compliance posture. They cannot hand long-lived API keys to third parties.
- A **broker** wants to execute the vendor's workflow on the customer's behalf, against the customer's provider account, without either party having to surrender their secret to the other.

Today this collapses into one of three unsatisfying options:

| Option | What goes wrong |
|---|---|
| Vendor hosts the workflow and pays for inference | Vendor takes on cost, billing, abuse, and capacity risk. Customer loses governance. |
| Customer self-hosts the workflow | Vendor must ship plaintext prompts and orchestration logic. IP is gone on day one. |
| Customer gives vendor a long-lived API key | Customer loses spend control, model choice, retention control, and audit. Compliance teams reject this. |

There is no fourth option — yet. This project prototypes one.

## 2. Target users

**Primary**

- **Workflow vendors** — small AI shops building vertical workflows (eval suites, content planners, code review agents, schema synthesizers) who want to sell into enterprises without shipping their prompts.
- **Enterprise platform engineers** — the team that owns the AI inference contract, model allowlist, and governance posture. They evaluate every third-party tool against "does this require a long-lived API key?" — the answer is currently always yes.
- **Broker operators** — neutral execution platforms (cloud marketplaces, agent registries, MCP hosts) that want to mediate vendor↔customer flows.

**Secondary**

- **Researchers** building private evaluation harnesses where the eval rubric itself is sensitive.
- **Marketplace operators** (Anthropic Apps, OpenAI GPT Store-style products, Hugging Face Spaces, agent registries) considering how to support paid third-party workflows that run against the user's own inference account.

## 3. Non-goals

This v0 prototype explicitly **does not** attempt to:

- Provide cryptographic confidentiality of prompts at runtime against a malicious broker, malicious host OS, or memory inspection. (Production roadmap → confidential compute + remote attestation.)
- Provide a hosted SaaS, a UI dashboard, OAuth, real billing, multi-tenant isolation, or KMS integration.
- Replace MCP, agent frameworks, or model provider SDKs. `sealedx` composes with them; it does not subsume them.
- Solve prompt extraction via the model's own output. (Out of scope — see §8.)
- Ship a marketplace, payments, or vendor verification flow.
- Provide a long-lived credential vault. v0 reads provider keys from environment variables and is honest about that.

## 4. Use cases

**UC-1 — Private prompt-as-product.** A vendor sells `immersive-video-planner` (a structured-output prompt that produces a scene plan). The customer runs it on their Anthropic account; the prompt is never displayed to the customer's CLI users, and the customer's API key is never displayed to the vendor.

**UC-2 — Confidential evaluation rubric.** A research team has a multi-criterion grading rubric that they want to keep private. Other teams want to evaluate their own model outputs against it. `sealedx` lets them run the rubric on the evaluating team's inference account without revealing the rubric prompt.

**UC-3 — Compliance-friendly third-party tooling.** An enterprise security team wants to allow Marketing to use a third-party "campaign brief generator." Today they refuse because the vendor wants an OpenAI key. With `sealedx`, the customer issues a short-lived, budget-bounded grant for `gpt-4.1-mini` capped at $5 / 1 hour. The vendor never sees the key.

**UC-4 — Auditable cross-provider execution.** A platform team requires that every external workflow execution emit a tamper-evident receipt — what prompt hash ran, against what model, for how many tokens, at what cost — so that they can reconcile vendor invoices and provider bills.

## 5. User stories

- **US-1 (vendor):** As a workflow vendor, I can package my prompt, input schema, and output schema into a content-addressed `WorkflowPackage` so that customers can reference it by ID and version without me revealing the prompt.
- **US-2 (vendor):** As a workflow vendor, I can declare provider/model requirements and licensing terms on the package so that brokers can refuse to execute it against incompatible grants.
- **US-3 (customer):** As a customer, I can issue a bounded `ExecutionGrant` that pins provider, model, budget, and expiry, so that I know the worst-case cost and time exposure of any execution under it.
- **US-4 (customer):** As a customer, I can submit input to a broker and receive validated output plus a signed receipt without the prompt ever being shown in my terminal.
- **US-5 (broker):** As a broker, I can verify that a grant covers a package's stated requirements before executing, and I can refuse if the budget or expiry is exceeded.
- **US-6 (anyone):** As any party, I can verify a receipt's signature and re-derive its hashes to prove that a specific execution happened with specific bytes.
- **US-7 (auditor):** As a customer auditor, I can read receipts to reconcile spend without ever seeing the vendor's prompt.
- **US-8 (vendor auditor):** As a vendor, I can receive a usage receipt that proves my package was executed N times for M tokens, without containing the customer's API key.

## 6. Functional requirements

**FR-1 — Workflow packaging.** `sealedx vendor package` accepts a prompt file, an input JSON Schema, an output JSON Schema, optional metadata (name, version, license, provider/model requirements). It produces a `WorkflowPackage` JSON document containing content-addressed hashes (SHA-256) of each artifact. The prompt file is stored encrypted-at-rest is **not** required for v0 but the prompt is never written to stdout by any normal command.

**FR-2 — Execution grants.** `sealedx customer grant` produces an `ExecutionGrant` carrying provider, model, budget (USD), expiry, optional model allowlist, and an opaque grant ID. Provider credentials are read from the local environment at execution time, never embedded in the grant document.

**FR-3 — Broker execution.** `sealedx broker execute --package-id ... --grant-id ... --input ...` orchestrates the flow: load package, validate input against input schema, select provider via grant, call the provider adapter, validate output against output schema, write the result file, write a signed receipt. Any error path emits a receipt with `status` reflecting the failure.

**FR-4 — Provider adapters.** A clean adapter `Protocol` with at least one mock and one real adapter. Mock is deterministic and fixture-driven. Real adapters (OpenAI, Anthropic) are gated on env credentials and never required for tests.

**FR-5 — Signed receipts.** Receipts are signed with Ed25519 (pynacl). `sealedx receipt verify <path>` re-derives all hashes that can be checked locally and verifies the signature. Tampered fields fail verification.

**FR-6 — Schema validation.** Inputs and outputs are validated against JSON Schema. Schema mismatches fail closed with a structured error and an `invalid_input` / `invalid_output` receipt.

**FR-7 — Cost accounting.** When a provider response includes usage tokens, the broker estimates USD cost using a per-model cost table and enforces the grant budget. If usage is unavailable, the receipt records `null` and the policy flag `usage_unavailable` is set.

**FR-8 — Safe logging.** The broker has a redacting logger. It never emits prompt bodies, API keys, or full input/output text at INFO level. DEBUG-level prompt logging requires an explicit `--unsafe-debug-prompt` flag and prints a warning.

**FR-9 — CLI surface.**
```
sealedx vendor package    --name --prompt --input-schema --output-schema [--version] [--license] [--require-provider] [--require-model]
sealedx customer grant    --provider --model --budget-usd --expires-in [--allow-models]
sealedx broker  execute   --package-id --grant-id --input [--out]
sealedx receipt verify    <path>
sealedx package list
sealedx grant   list
```

**FR-10 — Local persistence.** Packages, grants, and receipts persist as JSON under `$SEALEDX_HOME` (default `~/.sealedx/`). Atomic writes; UTC timestamps; UUIDs for IDs.

## 7. Non-functional requirements

- **Determinism in tests.** No test depends on a live external API. Mock provider returns reproducible structured outputs given the same input + seed.
- **Read-time validation.** Every artifact loaded from disk is re-validated against its Pydantic model.
- **Type safety.** `mypy --strict`-clean public API; type hints on all functions.
- **Lint.** `ruff` clean.
- **Footprint.** Zero required services, no daemon, runs fully on a laptop. Local JSON state only.
- **Performance.** Not a goal at v0. Single-execution latency is dominated by the provider call. Local validation overhead must stay under 50 ms for the example workflows.
- **Cross-platform.** macOS + Linux. No Windows-specific paths.
- **Reproducibility.** Two runs of the demo on different machines, with the same package + input + mock provider seed, produce byte-identical result and receipt content (modulo timestamps and signature).

## 8. Security and trust requirements

The v0 threat model is intentionally narrow and **honest**. Detailed table is in `docs/threat-model.md`; this section states the principles.

**v0 is a trust-based broker.** A customer who runs the broker locally **could** read the prompt off disk after loading. Production strength requires confidential compute + attestation; v0 does not pretend otherwise. The point of v0 is to standardize the *protocol* — package, grant, receipt — so that the protocol can later be lifted into a confidential-compute environment without re-designing the data model.

**v0 must defend against (within ordinary, non-malicious operation):**

- T-1: A customer reading the prompt via ordinary CLI output. → No customer-facing command renders the prompt; only its hash.
- T-2: A vendor seeing the customer's API key via workflow output, error messages, or receipts. → Keys never enter packages, grants, or receipts; only env-resident.
- T-3: Accidental leakage in logs (prompt body, key, full input) at INFO level. → Redacting logger; explicit unsafe flag required for raw prompt logging.
- T-4: Tampered receipts. → Ed25519 signature over canonical JSON serialization; verification re-derives hashes.
- T-5: Misreporting of provider/model/cost. → Receipt fields come from the adapter response, not the grant request, and are signed.
- T-6: Schema drift. → Hashes of input/output schemas are part of the receipt; verification can confirm the schemas in use.
- T-7: Replay of an expired grant. → Broker checks expiry and budget at execution time; receipt records the grant's effective state.

**v0 explicitly does not defend against** (`docs/limitations.md` enumerates):

- A malicious broker operator with disk and memory access.
- A malicious host machine.
- A determined customer running their own copy of the broker with prompt access.
- Inference-output-based prompt extraction (the model can be coaxed into echoing the prompt).
- Provider-side access to plaintext prompts (the provider always sees the prompt).
- Side-channel timing or token-count leakage.
- Sybil/abuse at the marketplace layer (no vendor verification in v0).

## 9. Threat model summary

Full table — threat / v0 mitigation / production mitigation / residual risk — lives in `docs/threat-model.md`. The short version:

| Adversary | v0 stance |
|---|---|
| Casual customer | Defended (prompt never displayed; redaction). |
| Casual vendor | Defended (key never travels in any package/grant/receipt). |
| Determined customer with shell access on broker host | Not defended — this is what confidential compute solves. |
| Malicious broker operator | Not defended — explicit limitation; production needs attestation + sealed bundles. |
| Network observer | Defended only insofar as the provider SDK uses TLS. No additional in-transit confidentiality from `sealedx` itself in v0. |
| Receipt forger | Defended (Ed25519 signature; tampering breaks verification). |

## 10. Data model

Authoritative shapes are Pydantic models in `sealedx/`. Summary:

**WorkflowPackage**
```text
package_id: str  # "pkg_<uuid>"
name: str
version: str  # semver
prompt_hash: str  # "sha256:<hex>"
input_schema_hash: str
output_schema_hash: str
prompt_path: str  # local-only; never serialized in customer-visible commands
input_schema_path: str
output_schema_path: str
created_at: datetime  # UTC
license: str | None
required_provider: str | None
required_models: list[str] | None
publisher: str | None
```

**ExecutionGrant**
```text
grant_id: str  # "grant_<uuid>"
provider: Literal["mock", "openai", "anthropic", "huggingface"]
model: str
budget_usd: Decimal
spent_usd: Decimal
expires_at: datetime  # UTC
allowed_models: list[str] | None
created_at: datetime
status: Literal["active", "expired", "exhausted", "revoked"]
```

Provider credentials are **not** part of the grant. They are resolved at execute-time from `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `HF_TOKEN` environment variables.

**ExecutionRequest** (in-memory only)
```text
package_id, grant_id, input: dict[str, Any], request_id, requested_at
```

**ExecutionResult**
```text
result_id: str
output: dict[str, Any]
output_hash: str  # over canonical JSON
status: Literal["succeeded", "invalid_input", "invalid_output", "budget_exceeded",
                "grant_expired", "provider_error", "policy_denied"]
error: str | None  # redacted, no prompt or key
```

**ExecutionReceipt** — see protocol doc; canonical form below.

## 11. CLI requirements

- All commands must complete deterministically with the mock provider — no network, no env vars required.
- No command renders prompt bytes by default. `package show` shows hashes, name, version, requirements, license — never the prompt body.
- All commands emit machine-parseable JSON when given `--json`. Default output is human-friendly text with the same fields.
- Errors exit non-zero and print a single-line redacted error plus a hint where to find the failure receipt.
- `--quiet` suppresses non-error output. `--verbose` enables INFO logs (still redacted). `--unsafe-debug-prompt` is the only switch that may render the prompt to stderr; it prints a warning.

## 12. API / broker requirements

v0 ships only the CLI. The broker runtime is exposed as a Python module (`sealedx.broker.execute(package_id, grant_id, input)`) so that a future FastAPI front end can wrap it without re-implementing logic. Splitting the runtime from the CLI is an explicit design constraint to keep that future move cheap.

## 13. Provider adapter requirements

- Adapters implement a single `Protocol`:

```python
class ProviderAdapter(Protocol):
    name: str
    def supports(self, model: str) -> bool: ...
    def complete(self, request: ProviderRequest) -> ProviderResponse: ...
    def estimate_cost_usd(self, tokens_in: int, tokens_out: int, model: str) -> Decimal: ...
```

- `ProviderRequest` carries `model`, `prompt`, `input` (the validated user input dict), and an optional `response_schema`.
- `ProviderResponse` carries `output_text`, `parsed_output` (already JSON-decoded if structured), `tokens_in`, `tokens_out`, `provider_request_id`, optional `raw_provider_metadata`.
- Mock adapter is the canonical reference. It is **fixture-driven**: a `mock_responses/<package_name>.json` file maps input fingerprints to canned outputs. If no fixture exists, it returns a deterministic placeholder that satisfies the output schema (filled with schema-typed default values).
- Real adapters (OpenAI, Anthropic) are conditional imports, gated on env credentials. They are not imported during tests unless the test explicitly opts in.

## 14. Execution receipt requirements

- Receipt is a single JSON object signed with Ed25519 over a **canonical** serialization (sorted keys, no whitespace) of all fields except `broker_signature` itself.
- Signature is base64-encoded; the broker's public key is published via `broker_public_key_id` and checked into `examples/broker-keys/` for the demo.
- Verification re-derives `prompt_hash`, `input_hash`, `output_hash` from the artifacts on disk where available, and checks the signature.
- Receipts are append-only on disk. The CLI never updates a receipt in place.

Canonical receipt shape is in `docs/protocol.md`.

## 15. Testing requirements

- **Unit:** package creation, prompt hashing, input/output schema validation (positive + negative), grant create/expire/exhaust, mock provider determinism, receipt sign/verify roundtrip + tamper detection, log redaction (no prompt or key bytes appear in captured logs).
- **Integration:** end-to-end execution with mock provider, expired grant rejection, budget exceeded rejection, invalid input rejection, invalid output rejection, receipt verification CLI command.
- **No live API.** Tests must pass with empty `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`.
- **Coverage target:** ≥ 85% lines in `sealedx/` excluding adapter modules that require live credentials.

## 16. Demo requirements

`scripts/demo.sh`, run from a fresh clone with no API keys, must:

1. Package the `immersive-video-planner` workflow.
2. Issue an execution grant against the mock provider.
3. Execute the workflow with `examples/immersive-video-planner/input.json`.
4. Print the resulting `result.json` (a structured scene plan).
5. Print the receipt (no prompt bytes; only hashes and signature).
6. Verify the receipt signature.
7. Demonstrate one negative case (invalid input → rejected receipt).

The demo must run end-to-end in under 10 seconds on a laptop.

## 17. Open questions

- **OQ-1.** Should grants be issued by signing a customer-held key, so that the broker is fully stateless w.r.t. grant validity? (Likely yes in v0.2 — defer.)
- **OQ-2.** How should `required_models` interact with capability-class equivalence (e.g., "any sonnet-4.x")? Naive list match for v0; capability tags later.
- **OQ-3.** Where does the tamper-evident log live? In v0 it does not — receipts are append-only files only. Production answer is a transparency log (Sigsum-style); roadmapped.
- **OQ-4.** Vendor-side usage receipt: should the broker derive a separate redacted receipt addressed to the vendor that omits customer-identifying fields? Yes; design is sketched in `docs/protocol.md` but implementation is a v0.2 stretch.
- **OQ-5.** Should we ship a default model→cost table? Yes for the demo; mark it conspicuously as out-of-date in docs.

## 18. MVP scope

In scope for v0.1:

- Workflow package model + `vendor package` CLI
- Execution grant model + `customer grant` CLI
- Broker runtime + `broker execute` CLI
- Mock provider adapter (required) + OpenAI + Anthropic adapters (optional, env-gated)
- Signed receipts + `receipt verify` CLI
- Schema validation (input + output)
- Redacting logger
- Local JSON storage under `~/.sealedx/`
- Two example workflows: `immersive-video-planner`, `private-eval`
- Tests (unit + integration), no live API deps
- README, PRD, threat model, architecture, protocol, limitations, roadmap docs
- Mermaid sequence + component diagrams
- Demo script

Explicitly **out of scope for v0.1** (see §3).

## 19. Future roadmap

Selected items, in rough priority order. Full list in `docs/roadmap.md`.

1. **Confidential-compute broker** — port runtime to AWS Nitro Enclaves / GCP Confidential Space / Azure Confidential VMs. Vendors ship sealed prompt bundles encrypted to the enclave's attestation key.
2. **Customer-signed grants** — grants become offline tokens signed by the customer's key, removing broker-side grant state.
3. **Provider-native delegated execution** — when providers ship a "run this opaque blob, charge it to grant X" primitive, the broker collapses to a thin adapter.
4. **Hugging Face + local-LLM adapters.**
5. **FastAPI broker service** so a CLI is not the only client.
6. **Receipt transparency log** (Sigsum or Rekor-style) — public, append-only, witness-cosigned.
7. **Policy hooks** — allowlist/blocklist, content classifiers, PII detectors invoked at the broker boundary.
8. **Vendor verification + abuse controls** — KYC for high-risk packages; report-and-takedown for marketplace integration.
9. **Receipt-driven invoice reconciliation** — vendor invoices and provider bills both prove against the receipt log.

## 20. Hiring / credibility positioning

The audience for this prototype is platform-engineering and AI-infrastructure leaders at:

- **Anthropic** — Apps/MCP/Computer-Use teams; trust & safety platform; Bedrock partnership eng.
- **OpenAI** — Apps/Agents/Realtime; enterprise platform; safety systems.
- **Hugging Face** — Inference Endpoints; Spaces; enterprise.
- **AWS Bedrock**, **Google Vertex AI**, **Azure AI Foundry** — managed-inference primitives, governance, agent runtimes.
- **Agent infrastructure startups** — LangChain, LlamaIndex, Crew, Vercel AI, Replit, Together, Fireworks, Modal.

What this project is meant to demonstrate to that audience:

- **Identification of a real platform gap.** The vendor↔customer↔broker triangle is a missing primitive between MCP-style connectivity and provider-native inference. Articulated cleanly with a threat model.
- **Protocol thinking.** Concrete, auditable data model — package, grant, receipt — that survives the move from a trust-based broker to a confidential-compute broker without re-design.
- **Disciplined v0.** Mock provider as the contract, real adapters as opt-in, no live-API tests, no overclaiming of confidentiality. Honesty about limitations is a feature, not a footnote.
- **Production instincts.** Type hints, Pydantic models, redacting logger, atomic file writes, append-only receipts, content-addressed packaging, Ed25519 signatures, deterministic demo. The shape of code that survives review by a security-conscious senior engineer.
- **Communication at principal-engineer level.** Docs that read like a real proposal, not a tutorial.

This document and the repo as a whole are written with that bar in mind. Feedback from the named teams is genuinely invited.
