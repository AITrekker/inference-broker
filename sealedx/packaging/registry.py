"""Load/list workflow packages from the local store."""

from __future__ import annotations

from pathlib import Path

from sealedx.broker.errors import PackageNotFoundError
from sealedx.packaging.models import PackageReferences, WorkflowPackage
from sealedx.storage.paths import package_dir, packages_dir, read_json


def load_package(package_id: str) -> WorkflowPackage:
    doc_path = packages_dir() / f"{package_id}.json"
    if not doc_path.exists():
        raise PackageNotFoundError(package_id)
    return WorkflowPackage.model_validate(read_json(doc_path))


def package_references(package_id: str) -> PackageReferences:
    pkg_dir = package_dir(package_id)
    return PackageReferences(
        prompt_path=str(pkg_dir / "prompt.md"),
        input_schema_path=str(pkg_dir / "input.schema.json"),
        output_schema_path=str(pkg_dir / "output.schema.json"),
    )


def read_prompt(package_id: str) -> str:
    return Path(package_references(package_id).prompt_path).read_text(encoding="utf-8")


def read_input_schema(package_id: str) -> dict:
    return read_json(Path(package_references(package_id).input_schema_path))


def read_output_schema(package_id: str) -> dict:
    return read_json(Path(package_references(package_id).output_schema_path))


def list_packages() -> list[WorkflowPackage]:
    out: list[WorkflowPackage] = []
    for path in sorted(packages_dir().glob("pkg_*.json")):
        try:
            out.append(WorkflowPackage.model_validate(read_json(path)))
        except Exception:  # noqa: BLE001 — list is best-effort
            continue
    return out
