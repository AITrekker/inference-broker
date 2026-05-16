"""Ed25519 keypair management for the broker.

v0 keeps the broker's signing key as a 32-byte seed in a file at mode 0600. There is no
rotation, no HSM, no revocation — see docs/limitations.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from nacl.signing import SigningKey, VerifyKey

DEFAULT_KEY_ID = "broker-dev-key-1"


@dataclass(frozen=True)
class BrokerKeypair:
    key_id: str
    signing_key: SigningKey
    verify_key: VerifyKey


def _key_id() -> str:
    return os.environ.get("SEALEDX_BROKER_KEY_ID", DEFAULT_KEY_ID)


def load_or_create_broker_keypair(keys_dir: Path) -> BrokerKeypair:
    keys_dir.mkdir(parents=True, exist_ok=True)
    seed_path = keys_dir / "broker_ed25519.seed"
    pub_path = keys_dir / "broker_ed25519.pub"

    if seed_path.exists():
        seed = seed_path.read_bytes()
        if len(seed) != 32:
            raise ValueError(f"broker key seed at {seed_path} is not 32 bytes")
        signing = SigningKey(seed)
    else:
        signing = SigningKey.generate()
        seed_path.write_bytes(signing.encode())
        os.chmod(seed_path, 0o600)
        pub_path.write_bytes(bytes(signing.verify_key))
        os.chmod(pub_path, 0o644)

    return BrokerKeypair(
        key_id=_key_id(),
        signing_key=signing,
        verify_key=signing.verify_key,
    )


def public_key_path(keys_dir: Path) -> Path:
    return keys_dir / "broker_ed25519.pub"


def load_verify_key(keys_dir: Path) -> tuple[str, VerifyKey]:
    """Load the broker's public key. Used by the verifier."""
    pub = public_key_path(keys_dir)
    if not pub.exists():
        raise FileNotFoundError(
            f"broker public key not found at {pub}. Run `sealedx broker execute` once "
            "to initialize, or copy a published broker public key into this path."
        )
    return _key_id(), VerifyKey(pub.read_bytes())
