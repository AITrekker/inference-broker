"""JSON Schema validation wrappers used by packaging and the broker."""

from __future__ import annotations

from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

from sealedx.broker.errors import SealedxError


class SchemaValidationError(SealedxError):
    """Raised when input or output does not conform to its declared JSON Schema."""

    def __init__(self, code: str, message: str, errors: list[str]) -> None:
        super().__init__(code=code, message=message)
        self.errors = errors


def validate(instance: Any, schema: dict[str, Any], *, kind: str) -> None:
    """Validate ``instance`` against ``schema``.

    ``kind`` is one of ``"input"`` or ``"output"`` and selects the error code:
    ``invalid_input`` or ``invalid_output``. Error messages enumerate the failing
    paths but never include the offending values, since those may be sensitive.
    """
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if not errors:
        return

    paths = []
    for err in errors:
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        paths.append(f"{loc}: {err.message}")

    code = "invalid_input" if kind == "input" else "invalid_output"
    raise SchemaValidationError(
        code=code,
        message=f"{kind} failed schema validation ({len(errors)} error(s))",
        errors=paths,
    )


def is_valid_schema(schema: dict[str, Any]) -> tuple[bool, str | None]:
    """Lightweight schema-of-schemas check used at packaging time."""
    try:
        Draft202012Validator.check_schema(schema)
        return True, None
    except jsonschema.SchemaError as e:
        return False, str(e)
