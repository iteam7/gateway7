"""Errors whose public representations contain no upstream or input details."""


class StartupError(RuntimeError):
    """Raised only with a core-authored, sanitized configuration diagnostic."""


class ProviderError(Exception):
    def __init__(self) -> None:
        super().__init__("Provider request failed")


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
