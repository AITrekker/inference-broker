"""Redacting logger and safe-error helpers.

The broker, packaging, grants, and adapters log via :func:`get_logger`. INFO-level
output never contains prompt, key, or full input/output bytes. The unsafe-debug
mode is gated by the ``SEALEDX_UNSAFE_DEBUG_PROMPT`` env var (set by the CLI flag
``--unsafe-debug-prompt``) and is intentionally noisy when on.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any

_REDACTION_KEYS = {
    "api_key",
    "apikey",
    "openai_api_key",
    "anthropic_api_key",
    "hf_token",
    "authorization",
    "authentication",
    "secret",
    "token",
    "prompt",
    "input",
    "output",
}

_REDACTED = "<redacted>"

# Loose regex that catches OpenAI-style and Anthropic-style key prefixes.
# False positives would still be redacted, which is the safe direction.
_KEY_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"hf_[A-Za-z0-9]{16,}"),
]


def _scrub_str(text: str) -> str:
    for pat in _KEY_PATTERNS:
        text = pat.sub(_REDACTED, text)
    return text


def redact(value: Any, *, key: str | None = None) -> Any:
    """Redact a value for safe logging.

    - dicts are walked, with redaction applied per-key
    - strings are scrubbed of key-shaped substrings
    - other types pass through

    If ``key`` matches a known sensitive name (api_key, prompt, etc.) the value
    is replaced wholesale by ``<redacted>``.
    """
    if key is not None and key.lower() in _REDACTION_KEYS:
        return _REDACTED
    if isinstance(value, dict):
        return {k: redact(v, key=k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _scrub_str(value)
    return value


def redact_error_message(message: str) -> str:
    """Redact an error message for surfacing to the customer."""
    return _scrub_str(message)


_CONFIGURED = False


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level_name = os.environ.get("SEALEDX_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger("sealedx")
    root.handlers = [handler]
    root.setLevel(level)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    if not name.startswith("sealedx"):
        name = f"sealedx.{name}"
    return logging.getLogger(name)


def unsafe_debug_prompt_enabled() -> bool:
    return os.environ.get("SEALEDX_UNSAFE_DEBUG_PROMPT", "").lower() in {"1", "true", "yes"}
