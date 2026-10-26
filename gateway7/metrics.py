"""Per-application Prometheus metrics with bounded, content-free labels."""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.http_requests = Counter(
            "gateway7_http_requests_total",
            "Completed HTTP requests.",
            ("route", "status"),
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
            "Chat requests rejected because active pipeline capacity is full.",
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

    def observe_provider(
        self,
        provider: str,
        outcome: str,
        duration: float,
        usage: dict[str, int] | None = None,
    ) -> None:
        self.provider_calls.labels(provider, outcome).inc()
        self.provider_duration.labels(provider, outcome).observe(max(0, duration))
        if usage is None or any(
            type(usage.get(name)) is not int or not 0 <= usage[name] <= 2**63 - 1
            for name in ("input_tokens", "output_tokens")
        ):
            self.provider_usage_unknown.labels(provider).inc()
            return
        self.provider_tokens.labels(provider, "input").inc(usage["input_tokens"])
        self.provider_tokens.labels(provider, "output").inc(usage["output_tokens"])

    def observe_middleware(self, name: str, phase: str, outcome: str, duration: float) -> None:
        self.middleware_steps.labels(name, phase, outcome).inc()
        self.middleware_duration.labels(name, phase).observe(max(0, duration))
