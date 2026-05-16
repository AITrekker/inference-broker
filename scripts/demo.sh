#!/usr/bin/env bash
# End-to-end demo against the mock provider. No external API credentials required.
#
# Walks through:
#   1. Vendor packages a private workflow.
#   2. Customer issues a bounded execution grant.
#   3. Broker executes — input validated, mock provider called, output validated,
#      grant charged, signed receipt issued.
#   4. Output JSON is shown.
#   5. Receipt JSON is shown (no prompt body — only hashes).
#   6. Receipt signature is verified.
#   7. A negative case (invalid input) shows that failure paths still emit a signed receipt.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --quiet --upgrade pip
  pip install --quiet -e ".[dev]"
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Use a clean, ephemeral SEALEDX_HOME so we don't pollute the user's home dir.
SEALEDX_HOME="$(mktemp -d -t sealedx-demo.XXXXXX)"
export SEALEDX_HOME
trap 'rm -rf "$SEALEDX_HOME"' EXIT

bold() { printf '\n\033[1m%s\033[0m\n' "$1"; }

bold "1) Vendor packages a private workflow"
sealedx vendor package \
  --name immersive-video-planner \
  --prompt examples/immersive-video-planner/prompt.md \
  --input-schema examples/immersive-video-planner/input.schema.json \
  --output-schema examples/immersive-video-planner/output.schema.json \
  --version 0.1.0 --publisher AITrekker --license Apache-2.0

PKG_ID="$(sealedx package list | head -1 | awk '{print $1}')"

bold "2) Customer issues a bounded execution grant"
sealedx customer grant \
  --provider mock \
  --model mock-claude-sonnet-4-5 \
  --budget-usd 5 \
  --expires-in 1h

GRANT_ID="$(sealedx grant list | head -1 | awk '{print $1}')"

bold "3) Broker executes the workflow"
sealedx broker execute \
  --package-id "$PKG_ID" \
  --grant-id "$GRANT_ID" \
  --input examples/immersive-video-planner/input.json

EXEC_RECEIPT="$(ls -t "$SEALEDX_HOME"/receipts/*.json | head -1)"
EXEC_RESULT="$(ls -t "$SEALEDX_HOME"/results/*.json | head -1)"

bold "4) Output JSON (first 40 lines)"
head -40 "$EXEC_RESULT"

bold "5) Receipt JSON (note: no prompt body, only hashes)"
cat "$EXEC_RECEIPT"

bold "6) Verify receipt signature"
sealedx receipt verify "$EXEC_RECEIPT"

bold "7) Negative case: invalid input still emits a signed receipt"
BAD_INPUT="$(mktemp -t sealedx-bad-input.XXXXXX.json)"
trap 'rm -rf "$SEALEDX_HOME" "$BAD_INPUT"' EXIT
echo '{"topic": "missing-fields"}' > "$BAD_INPUT"
sealedx broker execute \
  --package-id "$PKG_ID" \
  --grant-id "$GRANT_ID" \
  --input "$BAD_INPUT" || true

BAD_RECEIPT="$(ls -t "$SEALEDX_HOME"/receipts/*.json | head -1)"
echo
echo "Verifying the failure receipt:"
sealedx receipt verify "$BAD_RECEIPT"

bold "Done."
