"""Optional OTLP export of the per-request log line and the request-duration histogram.

Collection is off unless ``TELEMETRY_ENABLED`` is true. When it is on, the gateway pushes
one structured log record and one histogram observation for each API request to the
OTLP/HTTP endpoint named by the standard ``OTEL_EXPORTER_OTLP_*`` variables. Both carry
only the opaque request identifier, fixed route and outcome names, the HTTP status, the
gateway's fixed error code and the duration: never request or response content, client
names, model names, tokens, keys or addresses.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any

from gateway7.errors import StartupError

logger = logging.getLogger("gateway7")

#: Routes whose requests are recorded. Health checks and scrapes are excluded so
#: that probes do not dilute the request signal or fill the log stream.
RECORDED_ROUTES = frozenset({"chat", "openai_chat", "openai_responses", "models", "other"})

#: The histogram's explicit bucket boundaries, in milliseconds. They match the
#: Prometheus HTTP histogram's boundaries so both views interpolate alike.
DURATION_BUCKETS_MS = (5, 25, 100, 500, 1000, 2500, 5000, 10000, 30000, 60000, 120000, 300000)

ENVIRONMENTS = frozenset({"staging", "production"})
METRIC_EXPORT_INTERVAL_MS = 10_000
LOG_SCHEDULE_DELAY_MS = 1_000
EXPORT_TIMEOUT_SECONDS = 5.0

REQUEST_LOG_BODY = "gateway request"
DURATION_METRIC = "gateway7_request_duration_ms"


def outcome_for(status: int) -> str:
    """Map an HTTP status to the fixed outcome label used by the log line and histogram."""
    if status == 499:
        return "cancelled"
    if status >= 500:
        return "server_error"
    if status >= 400:
        return "client_error"
    return "ok"


def _enabled(environ: Mapping[str, str]) -> bool:
    value = environ.get("TELEMETRY_ENABLED", "").strip().lower()
    if value in ("", "0", "false", "no", "off"):
        return False
    if value in ("1", "true", "yes", "on"):
        return True
    raise StartupError("TELEMETRY_ENABLED must be true or false")


class Telemetry:
    """Per-application exporter state; a disabled instance records nothing."""

    def __init__(
        self,
        *,
        logger_provider: Any = None,
        meter_provider: Any = None,
        environment: str | None = None,
    ) -> None:
        self.environment = environment
        self._logger_provider = logger_provider
        self._meter_provider = meter_provider
        self._logger: Any = None
        self._histogram: Any = None
        if logger_provider is not None and meter_provider is not None:
            self._logger = logger_provider.get_logger("gateway7")
            meter = meter_provider.get_meter("gateway7")
            self._histogram = meter.create_histogram(
                DURATION_METRIC,
                unit="ms",
                description="Gateway API request duration from receipt to response completion.",
                explicit_bucket_boundaries_advisory=list(DURATION_BUCKETS_MS),
            )

    @property
    def enabled(self) -> bool:
        return self._logger is not None

    @classmethod
    def disabled(cls) -> Telemetry:
        return cls()

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> Telemetry:
        """Build the exporters from process variables, or a disabled instance."""
        env = os.environ if environ is None else environ
        if not _enabled(env):
            return cls.disabled()
        environment = env.get("GATEWAY7_ENVIRONMENT", "")
        if environment not in ENVIRONMENTS:
            raise StartupError("GATEWAY7_ENVIRONMENT must be staging or production")
        for signal in ("LOGS", "METRICS"):
            if not (
                env.get("OTEL_EXPORTER_OTLP_ENDPOINT")
                or env.get(f"OTEL_EXPORTER_OTLP_{signal}_ENDPOINT")
            ):
                raise StartupError("OTEL_EXPORTER_OTLP_ENDPOINT is required for telemetry")

        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.metrics import Histogram, MeterProvider
        from opentelemetry.sdk.metrics.export import (
            AggregationTemporality,
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.resources import Resource

        # Resource.create runs ambient detectors, including OTEL_RESOURCE_ATTRIBUTES,
        # which can attach arbitrary private text to every exported signal.
        resource = Resource(
            {"service.name": "gateway7", "deployment.environment.name": environment}
        )
        # The exporters read the endpoint and the credential header from the standard
        # OTEL_EXPORTER_OTLP_* variables, so neither value passes through this module.
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(timeout=EXPORT_TIMEOUT_SECONDS),
                schedule_delay_millis=_interval(
                    env, "OTEL_BLRP_SCHEDULE_DELAY", LOG_SCHEDULE_DELAY_MS
                ),
            )
        )
        reader = PeriodicExportingMetricReader(
            # Delta temporality makes each exported point the interval's own
            # observations, so the SLI query's five-minute sum includes the first
            # request of a new series and survives a gateway restart.
            OTLPMetricExporter(
                timeout=EXPORT_TIMEOUT_SECONDS,
                preferred_temporality={Histogram: AggregationTemporality.DELTA},
            ),
            export_interval_millis=_interval(
                env, "OTEL_METRIC_EXPORT_INTERVAL", METRIC_EXPORT_INTERVAL_MS
            ),
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        return cls(
            logger_provider=logger_provider,
            meter_provider=meter_provider,
            environment=environment,
        )

    def record(
        self,
        *,
        request_id: str,
        route: str,
        status: int,
        error_code: str | None,
        duration_ms: float,
    ) -> None:
        """Record one request's log point and histogram observation from one measurement."""
        if not self.enabled or route not in RECORDED_ROUTES:
            return
        outcome = outcome_for(status)
        duration_ms = max(0.0, duration_ms)
        try:
            from opentelemetry._logs import SeverityNumber

            self._histogram.record(duration_ms, {"route": route, "outcome": outcome})
            self._logger.emit(
                body=REQUEST_LOG_BODY,
                severity_number=SeverityNumber.INFO if outcome == "ok" else SeverityNumber.WARN,
                severity_text="INFO" if outcome == "ok" else "WARN",
                attributes={
                    "request_id": request_id,
                    "route": route,
                    "outcome": outcome,
                    "status": status,
                    "error_code": error_code or "none",
                    "duration_ms": round(duration_ms, 3),
                },
            )
        except Exception:
            # Telemetry must never change a response; the local log line remains.
            logger.warning("request_id=%s outcome=telemetry_error component=telemetry", request_id)

    def shutdown(self) -> None:
        """Flush pending points and stop the exporter threads."""
        for provider in (self._logger_provider, self._meter_provider):
            if provider is None:
                continue
            try:
                provider.shutdown()
            except Exception:
                logger.warning("request_id=- outcome=shutdown_error component=telemetry")
        self._logger = None
        self._histogram = None


def _interval(environ: Mapping[str, str], name: str, default: int) -> int:
    value = environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        raise StartupError(f"{name} must be a whole number of milliseconds") from None
    if parsed <= 0:
        raise StartupError(f"{name} must be a whole number of milliseconds")
    return parsed
