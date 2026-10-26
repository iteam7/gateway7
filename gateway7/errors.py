"""Errors whose public representations contain no upstream or input details."""

from enum import StrEnum


class StartupError(RuntimeError):
    """Raised only with a core-authored, sanitized configuration diagnostic."""


class ProviderErrorReason(StrEnum):
    """Fixed diagnostic categories; never upstream text or client-facing codes."""

    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    TRANSPORT = "transport"
    INVALID_RESPONSE = "invalid_response"
    REJECTED = "rejected"
    UNKNOWN = "unknown"

    @classmethod
    def normalize(cls, value: object) -> "ProviderErrorReason":
        if isinstance(value, cls):
            return value
        # Do not stringify, hash or otherwise expose arbitrary exception data.
        if type(value) is str:
            try:
                return cls(value)
            except ValueError:
                pass
        return cls.UNKNOWN


class ProviderError(Exception):
    def __init__(
        self, reason: object = ProviderErrorReason.UNKNOWN, *, usage: object = None
    ) -> None:
        self.reason = ProviderErrorReason.normalize(reason)
        # Keep only independently validated numeric accounting. The immutable
        # pair cannot retain upstream metadata or share a mutable response dict.
        self._usage: tuple[int, int] | None = None
        if isinstance(usage, dict):
            input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
            if (
                type(input_tokens) is int
                and type(output_tokens) is int
                and 0 <= input_tokens <= 2**63 - 1
                and 0 <= output_tokens <= 2**63 - 1
            ):
                self._usage = (input_tokens, output_tokens)
        super().__init__("Provider request failed")

    @property
    def usage(self) -> dict[str, int] | None:
        if self._usage is None:
            return None
        return {"input_tokens": self._usage[0], "output_tokens": self._usage[1]}


class GatewayError(Exception):
    _ERRORS = {
        "unauthorized": (401, "Missing or invalid gateway bearer token"),
        "model_forbidden": (403, "Requested model is not allowed for this client"),
        "not_found": (404, "Requested endpoint does not exist"),
        "method_not_allowed": (405, "HTTP method is not allowed for this endpoint"),
        "policy_denied": (403, "Request denied by policy"),
        "plugin_error": (500, "Plugin processing failed"),
        "timeout": (504, "Request deadline exceeded"),
        "provider_error": (502, "Provider request failed"),
        "invalid_request": (422, "Invalid chat request"),
        "body_too_large": (413, "Request body is too large"),
        "unavailable": (503, "Gateway is not ready"),
        "overloaded": (503, "Gateway active request capacity is full"),
        "internal_error": (500, "Request processing failed"),
    }

    def __init__(self, code: str) -> None:
        # Unknown strings cannot become response content, including Deny.code.
        self.code = code if code in self._ERRORS else "internal_error"
        self.status_code, self.message = self._ERRORS[self.code]
        super().__init__(self.message)

    def body(self, request_id: str) -> dict[str, object]:
        return {
            "error": {"code": self.code, "message": self.message},
            "request_id": request_id,
        }
