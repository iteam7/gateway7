"""Per-application Prometheus metrics with bounded, content-free labels."""

from enum import StrEnum

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from gateway7.errors import ProviderErrorReason


class HTTPRequestOutcome(StrEnum):
    """Terminal request results, independent of the status already sent on the wire."""

    SUCCESS = "success"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    POLICY_DENIED = "policy_denied"
    PLUGIN_ERROR = "plugin_error"
    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED = "unauthorized"
    MODEL_FORBIDDEN = "model_forbidden"
    BODY_TOO_LARGE = "body_too_large"
    OVERLOADED = "overloaded"
    CLIENT_OVERLOADED = "client_overloaded"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    INTERNAL_ERROR = "internal_error"
    CONFLICT = "conflict"
    OPERATOR_FORBIDDEN = "operator_forbidden"
    BUDGET_EXCEEDED = "budget_exceeded"

    @classmethod
    def normalize(cls, value: object) -> "HTTPRequestOutcome":
        if isinstance(value, cls):
            return value
        if type(value) is str:
            if value == "complete":
                return cls.SUCCESS
            try:
                return cls(value)
            except ValueError:
                pass
        return cls.INTERNAL_ERROR

    @classmethod
    def from_status(cls, status: int | None) -> "HTTPRequestOutcome":
        if status is None:
            return cls.INTERNAL_ERROR
        if 200 <= status < 400:
            return cls.SUCCESS
        return {
            400: cls.INVALID_REQUEST,
            401: cls.UNAUTHORIZED,
            403: cls.POLICY_DENIED,
            404: cls.NOT_FOUND,
            405: cls.METHOD_NOT_ALLOWED,
            409: cls.CONFLICT,
            413: cls.BODY_TOO_LARGE,
            422: cls.INVALID_REQUEST,
            429: cls.RATE_LIMITED,
            499: cls.CANCELLED,
            502: cls.PROVIDER_ERROR,
            503: cls.UNAVAILABLE,
            504: cls.TIMEOUT,
        }.get(status, cls.INTERNAL_ERROR)


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.http_requests = Counter(
            "gateway7_http_requests_total",
            "HTTP requests by the response status actually sent.",
            ("route", "status"),
            registry=self.registry,
        )
        self.http_outcomes = Counter(
            "gateway7_http_request_outcomes_total",
            "Terminal HTTP request outcomes, including streaming failures and requests without a response.",
            ("route", "outcome"),
            registry=self.registry,
        )
        self.http_duration = Histogram(
            "gateway7_http_request_duration_seconds",
            "HTTP request duration.",
            ("route",),
            registry=self.registry,
            buckets=(0.005, 0.025, 0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
        )
        self.http_in_flight = Gauge(
            "gateway7_http_requests_in_flight",
            "HTTP requests currently in progress.",
            registry=self.registry,
        )
        self.active_pipelines = Gauge(
            "gateway7_active_pipelines",
            "Admitted pipeline tasks that have not finished, including cancellation cleanup.",
            registry=self.registry,
        )
        self.admission_rejections = Counter(
            "gateway7_admission_rejections_total",
            "Chat requests rejected because global pipeline or client request capacity is full.",
            registry=self.registry,
        )
        self.rate_limit_rejections = Counter(
            "gateway7_rate_limit_rejections_total",
            "Chat requests rejected because a configured client request-rate bucket is depleted.",
            registry=self.registry,
        )
        self.provider_calls = Counter(
            "gateway7_provider_calls_total",
            "Provider attempts by outcome.",
            ("provider", "outcome"),
            registry=self.registry,
        )
        self.provider_duration = Histogram(
            "gateway7_provider_duration_seconds",
            "Provider attempt duration.",
            ("provider", "outcome"),
            registry=self.registry,
            buckets=(0.01, 0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
        )
        self.provider_errors = Counter(
            "gateway7_provider_errors_total",
            "Failed provider attempts by safe diagnostic reason, excluding cancellation.",
            ("provider", "reason"),
            registry=self.registry,
        )
        self.provider_tokens = Counter(
            "gateway7_provider_tokens_total",
            "Known provider-reported tokens, including denied responses.",
            ("provider", "direction"),
            registry=self.registry,
        )
        self.provider_usage_unknown = Counter(
            "gateway7_provider_usage_unknown_total",
            "Provider attempts without complete valid token usage.",
            ("provider",),
            registry=self.registry,
        )
        self.middleware_steps = Counter(
            "gateway7_middleware_steps_total",
            "Middleware own-work segments by outcome.",
            ("middleware", "phase", "outcome"),
            registry=self.registry,
        )
        self.middleware_duration = Histogram(
            "gateway7_middleware_duration_seconds",
            "Middleware own-work duration, excluding downstream waiting.",
            ("middleware", "phase"),
            registry=self.registry,
            buckets=(0.0001, 0.001, 0.005, 0.01, 0.025, 0.1, 0.5, 1, 2.5, 5, 10),
        )
        self.ready = Gauge(
            "gateway7_ready",
            "Gateway can accept protected client requests.",
            registry=self.registry,
        )
        self.management_database_available = Gauge(
            "gateway7_management_database_available",
            "Last management database ownership and connection check succeeded.",
            registry=self.registry,
        )
        self.exporter_enabled = Gauge(
            "gateway7_exporter_enabled",
            "Configured optional signal exporters.",
            ("exporter",),
            registry=self.registry,
        )
        self.exporter_events = Counter(
            "gateway7_exporter_events_total",
            "Optional exporter delivery results.",
            ("exporter", "outcome"),
            registry=self.registry,
        )
        self.exporter_last_success = Gauge(
            "gateway7_exporter_last_success_timestamp_seconds",
            "Unix time of the last successful optional export.",
            ("exporter",),
            registry=self.registry,
        )
        self.analytics_queue_depth = Gauge(
            "gateway7_analytics_queue_depth",
            "Queued product events awaiting delivery.",
            registry=self.registry,
        )
        for exporter in ("analytics", "telemetry_logs", "telemetry_metrics"):
            self.exporter_enabled.labels(exporter).set(0)
            self.exporter_last_success.labels(exporter).set(0)
            for outcome in ("success", "failure", "dropped"):
                self.exporter_events.labels(exporter, outcome).inc(0)

    def observe_http_outcome(self, route: str, outcome: object) -> None:
        safe_route = (
            route
            if type(route) is str
            and route
            in {
                "chat",
                "openai_chat",
                "openai_responses",
                "health",
                "ready",
                "metrics",
                "models",
                "other",
            }
            else "other"
        )
        self.http_outcomes.labels(safe_route, HTTPRequestOutcome.normalize(outcome).value).inc()

    def observe_provider(
        self,
        provider: str,
        outcome: str,
        duration: float,
        usage: dict[str, int] | None = None,
        *,
        error_reason: object = ProviderErrorReason.UNKNOWN,
    ) -> None:
        self.provider_calls.labels(provider, outcome).inc()
        self.provider_duration.labels(provider, outcome).observe(max(0, duration))
        if outcome == "provider_error":
            reason = ProviderErrorReason.normalize(error_reason)
            self.provider_errors.labels(provider, reason.value).inc()
        known = {
            direction: usage[direction + "_tokens"]
            for direction in ("input", "output")
            if isinstance(usage, dict)
            and type(usage.get(direction + "_tokens")) is int
            and 0 <= usage[direction + "_tokens"] <= 2**63 - 1
        }
        if len(known) != 2:
            self.provider_usage_unknown.labels(provider).inc()
        for direction, count in known.items():
            self.provider_tokens.labels(provider, direction).inc(count)

    def observe_middleware(self, name: str, phase: str, outcome: str, duration: float) -> None:
        self.middleware_steps.labels(name, phase, outcome).inc()
        self.middleware_duration.labels(name, phase).observe(max(0, duration))
