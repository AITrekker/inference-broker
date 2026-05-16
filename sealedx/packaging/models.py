"""Pydantic model for a workflow package.

Wire shape is normative: see docs/protocol.md §1. The prompt body is **never** part of
this document — only its hash is. The body lives next to the package on disk.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

PROTOCOL_VERSION = "0.1"


class WorkflowPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: str = PROTOCOL_VERSION
    package_id: str
    name: str
    version: str
    publisher: str | None = None
    license: str | None = None

    prompt_hash: str
    input_schema_hash: str
    output_schema_hash: str

    required_provider: str | None = None
    required_models: list[str] | None = None

    created_at: datetime

    def to_public_dict(self) -> dict[str, Any]:
        """A customer-safe view of the package. Hashes only — never the prompt body."""
        return self.model_dump(mode="json")


class PackageReferences(BaseModel):
    """Local-only paths to the artifacts. Not persisted in the package document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_path: str
    input_schema_path: str
    output_schema_path: str
