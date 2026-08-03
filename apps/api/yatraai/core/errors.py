"""Typed application errors mapped to consistent JSON responses."""

from __future__ import annotations

from typing import Any


class YatraError(Exception):
    """Base class. ``code`` is a stable machine-readable identifier."""

    status_code: int = 400
    code: str = "yatra_error"

    def __init__(self, message: str, *, detail: Any = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        if code:
            self.code = code

    def to_dict(self) -> dict:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


class NotFoundError(YatraError):
    status_code = 404
    code = "not_found"


class ValidationFailure(YatraError):
    status_code = 422
    code = "validation_failed"


class AuthenticationError(YatraError):
    status_code = 401
    code = "unauthenticated"


class AuthorizationError(YatraError):
    status_code = 403
    code = "forbidden"


class ConflictError(YatraError):
    status_code = 409
    code = "conflict"


class RateLimitedError(YatraError):
    status_code = 429
    code = "rate_limited"


class ConsentRequiredError(YatraError):
    status_code = 403
    code = "consent_required"


class PlanningInfeasibleError(YatraError):
    """The constraint set admits no valid itinerary - never show a broken plan."""

    status_code = 422
    code = "planning_infeasible"


class ProviderUnavailableError(YatraError):
    """An external provider failed *and* no fallback could satisfy the request."""

    status_code = 503
    code = "provider_unavailable"
