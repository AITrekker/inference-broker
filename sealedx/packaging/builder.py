"""Build a :class:`WorkflowPackage` from on-disk artifacts."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sealedx.packaging.models import WorkflowPackage
from sealedx.schemas.validate import is_valid_schema
from sealedx.security.hashing import hash_canonical_json, hash_text
from sealedx.storage.paths import atomic_write_json, atomic_write_text, package_dir


def _new_package_id() -> str:
    return "pkg_" + uuid.uuid4().hex


def package(
    *,
    name: str,
    version: str,
    prompt_path: Path,
    input_schema_path: Path,
    output_schema_path: Path,
    publisher: str | None = None,
    license: str | None = None,
    required_provider: str | None = None,
    required_models: list[str] | None = None,
) -> WorkflowPackage:
    """Hash artifacts, copy them into ``$SEALEDX_HOME/packages/<id>/``, write the package doc."""

    prompt_text = prompt_path.read_text(encoding="utf-8")
    input_schema = json.loads(input_schema_path.read_text(encoding="utf-8"))
    output_schema = json.loads(output_schema_path.read_text(encoding="utf-8"))

    ok, err = is_valid_schema(input_schema)
    if not ok:
        raise ValueError(f"input schema is not a valid JSON Schema: {err}")
    ok, err = is_valid_schema(output_schema)
    if not ok:
        raise ValueError(f"output schema is not a valid JSON Schema: {err}")

    package_id = _new_package_id()
    pkg_dir = package_dir(package_id)

    pkg = WorkflowPackage(
        package_id=package_id,
        name=name,
        version=version,
        publisher=publisher,
        license=license,
        prompt_hash=hash_text(prompt_text),
        input_schema_hash=hash_canonical_json(input_schema),
        output_schema_hash=hash_canonical_json(output_schema),
        required_provider=required_provider,
        required_models=required_models,
        created_at=datetime.now(UTC),
    )

    atomic_write_text(pkg_dir / "prompt.md", prompt_text)
    atomic_write_json(pkg_dir / "input.schema.json", input_schema)
    atomic_write_json(pkg_dir / "output.schema.json", output_schema)
    atomic_write_json(pkg_dir.parent / f"{package_id}.json", pkg.model_dump(mode="json"))

    # Also keep a copy of the original artifacts for traceability — mode 0600.
    shutil.copy2(prompt_path, pkg_dir / "prompt.original.md")

    return pkg
