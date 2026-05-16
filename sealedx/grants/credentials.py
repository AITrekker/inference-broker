"""Resolve provider credentials from environment at execution time. Never persisted."""

from __future__ import annotations

import os

from sealedx.broker.errors import CredentialMissingError

_PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "huggingface": "HF_TOKEN",
}


def credential_env_var(provider: str) -> str | None:
    return _PROVIDER_ENV.get(provider)


def resolve_credential(provider: str) -> str:
    env_var = credential_env_var(provider)
    if env_var is None:
        # mock and any future credential-less providers
        return ""
    value = os.environ.get(env_var, "")
    if not value:
        raise CredentialMissingError(env_var)
    return value
