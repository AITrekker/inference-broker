"""Typed exceptions for the broker pipeline. None of these may carry prompt or key bytes."""

from __future__ import annotations


class SealedxError(Exception):
    """Base class for all sealedx errors. ``message`` is safe to surface to the customer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PackageNotFoundError(SealedxError):
    def __init__(self, package_id: str) -> None:
        super().__init__("package_not_found", f"package {package_id} not found")


class GrantNotFoundError(SealedxError):
    def __init__(self, grant_id: str) -> None:
        super().__init__("grant_not_found", f"grant {grant_id} not found")


class GrantExpiredError(SealedxError):
    def __init__(self, grant_id: str) -> None:
        super().__init__("grant_expired", f"grant {grant_id} has expired")


class GrantExhaustedError(SealedxError):
    def __init__(self, grant_id: str) -> None:
        super().__init__("grant_exhausted", f"grant {grant_id} budget exhausted")


class GrantRevokedError(SealedxError):
    def __init__(self, grant_id: str) -> None:
        super().__init__("grant_revoked", f"grant {grant_id} has been revoked")


class BudgetExceededError(SealedxError):
    def __init__(self, grant_id: str) -> None:
        super().__init__(
            "budget_exceeded",
            f"grant {grant_id} budget would be exceeded by this call",
        )


class GrantPackageMismatchError(SealedxError):
    def __init__(self, message: str) -> None:
        super().__init__("policy_denied", message)


class ProviderError(SealedxError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message)


class CredentialMissingError(SealedxError):
    def __init__(self, env_var: str) -> None:
        super().__init__(
            "credential_missing",
            f"required environment variable {env_var} is not set",
        )
