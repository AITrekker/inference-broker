#!/usr/bin/env bash
# Run the full test suite. No external API credentials required.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install --quiet --upgrade pip
pip install --quiet -e ".[dev]"

ruff check sealedx tests
pytest "$@"
