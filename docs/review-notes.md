# Review Notes

A reviewer pass over the v0.1 prototype. The goal is to identify overclaim, doc/code drift, missing tests, and risks before sharing publicly.

## Verdict

**Ready to share.** The protocol shape is coherent, the implementation is honest about its limitations, and the threat model does not overclaim. There is genuine signal here for a platform-engineering reader. Outstanding items below are tracked roadmap or acceptable v0 trade-offs, not blockers.

## What's strong

- **Clear protocol vs. implementation split.** Package, grant, receipt are wire-stable; the broker runtime, storage backend, and adapter layer are all swappable. Lifting into a confidential-compute environment does not require touching data shapes.
- **Honest threat model.** [`docs/threat-model.md`](threat-model.md) names what v0 does and does not defend against. The README repeats the limits up front rather than burying them. This is the load-bearing piece for credibility.
- **Reference adapter is the mock.** The mock provider is the canonical adapter; real adapters are opt-in. CI works with no API credentials. Determinism makes signing tests possible.
- **Signed receipts that actually verify.** Sign and verify use the same canonical bytes — no datetime-formatting drift between issuer and verifier (v0.1 fixed this once during the build; tests now lock the roundtrip).
- **Failure paths are first-class.** Every failure path emits a signed receipt with a typed status (`invalid_input`, `grant_expired`, `budget_exceeded`, `policy_denied`, etc.). Auditors can reconcile from receipts alone.
- **Redaction.** Tests assert that prompt bytes do not appear in INFO-level logs across the full pipeline.
- **Documentation reads at the right level.** PRD, architecture, threat model, protocol, adapter contract, limitations, roadmap — six docs that read like a real proposal, not a tutorial.

## Confirmed claims (verified)

| Claim | How verified |
|---|---|
| Receipt sign/verify roundtrips | `tests/unit/test_receipt_signing.py::test_sign_verify_roundtrip` and `tests/integration/test_broker_e2e.py::test_e2e_receipt_verifies` |
| Tampering with `estimated_cost_usd` breaks verification | `tests/unit/test_receipt_signing.py::test_tampered_field_breaks_signature` |
| Tampering with `policy_flags` breaks verification | `tests/unit/test_receipt_signing.py::test_signature_is_over_all_signed_fields` |
| `package show` does not print prompt bytes | `tests/integration/test_cli.py::test_package_show_does_not_print_prompt` |
| Full broker pipeline emits no prompt at INFO level | `tests/integration/test_broker_e2e.py::test_no_prompt_in_logs` |
| Expired / revoked / over-budget grants emit typed failure receipts | `tests/integration/test_broker_e2e.py::test_*` |
| Mock provider is deterministic | `tests/unit/test_mock_provider.py::test_mock_is_deterministic` |
| End-to-end demo runs in under 10 seconds with no API keys | `scripts/demo.sh` |
| All hashes re-derive on `receipt verify` | demo output and integration test |

## Known limitations (deliberate, documented)

These are restated here so a reader does not mistake them for oversights.

- **No confidentiality against a malicious broker.** The prompt lives on disk at mode 0600; that is filesystem-permission strength, not cryptographic strength. Confidential compute is the v0.3 answer.
- **No transparency log.** Receipts are local files. A broker could refuse to surface or delete a receipt; there is no third-party witness. Sigsum-style log is v0.2.
- **No customer-signed grants.** Grants live on the broker. v0.2 makes them offline tokens signed by the customer's key.
- **Provider keys are environment variables.** Read at execute time, never persisted, but the broker process sees them. Production needs short-lived tokens (OAuth / customer-managed key release).
- **Cost table is hard-coded and dated** (`AS_OF=2026-05-15`). Receipts mark `cost_estimated:<as_of>` so consumers know. Production sources rates from the provider's billing API.
- **No rate limiting, no retry layer in the broker.** Adapters retry per-provider where appropriate. Concurrent execute calls against the same grant could race the budget check; the last writer wins. Acceptable for a CLI prototype.
- **Inference-output prompt extraction is not defended.** Output-schema validation raises the cost of casual extraction; a determined attempt can still get a model to echo the prompt. v0.3 ships output-channel exfiltration controls.
- **No vendor verification or abuse controls.** v0 has no marketplace; v1.0 adds KYC, classifiers, report-and-takedown.

## Doc/code consistency check

Cross-referenced the README, PRD, architecture, threat model, protocol, and provider-adapter docs against the implementation. No drift found. Specifically verified:

- Receipt schema in `docs/protocol.md` §5 matches `sealedx/receipts/models.py` field-for-field.
- Receipt status enum in `docs/prd.md` §10 matches `sealedx/receipts/models.py::ReceiptStatus` (with the addition of `grant_exhausted` and `grant_revoked` which the PRD doesn't enumerate but are non-conflicting refinements).
- CLI surface in `docs/prd.md` §11 matches the implemented Typer app (vendor/customer/broker/package/grant/receipt subcommands).
- Mock-provider contract in `docs/provider-adapters.md` matches `sealedx/providers/mock.py` (fixture lookup by input fingerprint, schema-typed defaults fallback, deterministic costs).
- Cost table `AS_OF` (2026-05-15) is consistently stamped into receipts via `policy_flags`.

## Test coverage assessment

58 tests pass; lint clean.

**Well-covered:**

- Canonical JSON serialization (locked-down byte-stable behavior)
- Hashing (namespacing, JSON canonicalization)
- Packaging (content addressing, schema validity, on-disk roundtrip)
- Grants (creation, expiry, exhaustion, revocation, charge accounting)
- Schema validation (positive + negative cases)
- Mock provider (determinism, fixture matching)
- Receipt sign/verify (roundtrip + two distinct tamper detections)
- Redaction (sensitive keys, key-shaped strings, lists/nested dicts)
- End-to-end broker pipeline (success + every failure status)
- CLI smoke (full vendor→customer→broker flow + prompt non-disclosure)

**Acceptable gaps for v0.1:**

- OpenAI and Anthropic adapters are not exercised in CI (they require live credentials). The contract that they implement is exercised via the mock. Adding mocked-HTTP adapter tests is a small, valuable v0.2 follow-up.
- Concurrency: no test for two parallel `broker execute` calls racing the budget check. Acceptable for a CLI prototype; relevant when v0.2 ships the FastAPI server.
- mypy is not yet wired into `scripts/test.sh`. Type hints are present throughout; a `mypy --strict` pass is a v0.2 follow-up.

## Suggested follow-ups (not blockers)

These are nominated for v0.2 but explicitly not required for v0.1:

1. **Adapter HTTP-mock tests.** `responses`-style fixtures for OpenAI and Anthropic so the contract is enforced in CI even without keys.
2. **Concurrency note.** Add a one-paragraph caveat in `docs/limitations.md` about parallel `broker execute` calls racing budget checks until the FastAPI server lands. (Already mentioned briefly; could be sharper.)
3. **mypy in CI.** `mypy --strict` against `sealedx/` and `tests/`.
4. **CI workflow.** `.github/workflows/ci.yml` running `scripts/test.sh` on push and PR. Trivial; deferred to keep the v0.1 commit series focused.
5. **Receipt JSON Schema.** Publishing a JSON Schema for the receipt would let third-party verifiers validate shape before signature.

## What this project should *not* claim

Reviewer's check on the public framing — verified all of these are absent or qualified:

- ❌ "Confidential" or "private" without a "in v0, against casual adversaries" qualifier — README and threat model both lead with the broker-trust caveat. ✓
- ❌ "Production-ready" — explicit non-claim in `docs/limitations.md` and the README. ✓
- ❌ "Final protocol" — versioning policy in `docs/protocol.md` §7 makes the upgrade path explicit. ✓
- ❌ "Defends against malicious broker" — `docs/threat-model.md` T2/T8/T16 explicitly state the opposite. ✓

## Final assessment

The project does what its README says it does. It does not pretend to do more. A senior platform engineer reading the repo top-to-bottom should come away with the impression that the author understands the platform gap, can reduce it to a concrete protocol, can build cleanly, and is honest about security boundaries. The bar in PRD §20 is met.

Ready to share publicly.
