"""Optional, bounded server-side product events for an environment's OpenPanel project.

Only the typed task envelope is sent. A caller cannot label traffic or add properties.
Delivery is best effort: a full queue or an unavailable backend never delays a response.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from gateway7.errors import StartupError
from gateway7.telemetry import outcome_for

logger = logging.getLogger("gateway7")

Source = Literal["web", "usability-test", "smoke"]
Environment = Literal["staging", "production"]
Route = Literal["chat", "openai_chat", "openai_responses"]
Outcome = Literal["ok", "client_error", "cancelled", "server_error"]
CHAT_ROUTES = frozenset({"chat", "openai_chat", "openai_responses"})
QUEUE_CAPACITY = 256
EXPORT_TIMEOUT_SECONDS = 1.0
SHUTDOWN_TIMEOUT_SECONDS = 2.0
PARTICIPANT_CODE_PATTERN = r"^P-(?:0[1-9]|[1-9][0-9]{1,5})$"


def _valid_participant_scope(code: str | None, environment: str, source: str) -> bool:
    return code is None or (
        environment == "staging"
        and source == "usability-test"
        and re.fullmatch(PARTICIPANT_CODE_PATTERN, code) is not None
    )


class TaskEvent(BaseModel):
    """The complete allowlist; no content or caller-supplied property bag exists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["chat_started", "chat_completed"]
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    route: Route
    environment: Environment
    source: Source
    participant_code: str | None = Field(default=None, pattern=PARTICIPANT_CODE_PATTERN)
    occurred_at: AwareDatetime
    status: int | None = Field(default=None, ge=100, le=599)
    outcome: Outcome | None = None
    duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def completion_fields_match_event(self) -> TaskEvent:
        if not _valid_participant_scope(self.participant_code, self.environment, self.source):
            raise ValueError("Participant codes require staging usability-test events")
        if self.occurred_at.utcoffset() != timedelta(0):
            raise ValueError("Event time must use UTC")
        fields = (self.status, self.outcome, self.duration_ms)
        if self.name == "chat_completed" and any(value is None for value in fields):
            raise ValueError("A completion requires status, outcome and duration")
        if self.name == "chat_started" and any(value is not None for value in fields):
            raise ValueError("A start has no completion fields")
        return self

    def openpanel_payload(self) -> dict[str, object]:
        properties = self.model_dump(mode="json", exclude={"name"}, exclude_none=True)
        # OpenPanel's track API reads an event's original time from __timestamp,
        # rather than from a top-level timestamp field (the SDK uses the same key).
        properties["__timestamp"] = properties["occurred_at"]
        return {
            "type": "track",
            "payload": {
                "name": self.name,
                "profileId": self.request_id,
                "properties": properties,
            },
        }


def _enabled(environ: Mapping[str, str]) -> bool:
    value = environ.get("ANALYTICS_ENABLED", "").strip().lower()
    if value in ("", "0", "false", "no", "off"):
        return False
    if value in ("1", "true", "yes", "on"):
        return True
    raise StartupError("ANALYTICS_ENABLED must be true or false")


class Analytics:
    """Per-app exporter with one bounded queue and one sequential worker."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        environment: Environment = "staging",
        source: Source = "web",
        participant_code: str | None = None,
    ) -> None:
        if not _valid_participant_scope(participant_code, environment, source):
            raise StartupError("Invalid analytics participant configuration")
        self.environment = environment
        self.source = source
        self.participant_code = participant_code
        self._client = client
        self._queue: asyncio.Queue[TaskEvent] = asyncio.Queue(maxsize=QUEUE_CAPACITY)
        self._worker: asyncio.Task[None] | None = None
        self._accepting = False

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @classmethod
    def disabled(cls) -> Analytics:
        return cls()

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> Analytics:
        """Validate server-owned settings; create no worker and make no request yet."""
        env = os.environ if environ is None else environ
        if not _enabled(env):
            return cls.disabled()
        environment = env.get("GATEWAY7_ENVIRONMENT", "")
        if environment not in ("staging", "production"):
            raise StartupError("GATEWAY7_ENVIRONMENT must be staging or production")
        source = env.get("ANALYTICS_SOURCE", "web")
        if source not in ("web", "usability-test", "smoke"):
            raise StartupError("ANALYTICS_SOURCE must be web, usability-test or smoke")
        if environment == "production" and source != "web":
            raise StartupError("Production analytics requires ANALYTICS_SOURCE=web")
        participant_code = env.get("ANALYTICS_PARTICIPANT_CODE")
        if not _valid_participant_scope(participant_code, environment, source):
            raise StartupError("Invalid analytics participant configuration")
        base_url = env.get("OPENPANEL_API_URL", "").rstrip("/")
        try:
            url = httpx.URL(base_url)
        except (httpx.InvalidURL, ValueError):
            raise StartupError("OPENPANEL_API_URL must be an HTTP or HTTPS API base") from None
        if (
            url.scheme not in ("http", "https")
            or not url.host
            or url.userinfo
            or url.query
            or url.fragment
        ):
            raise StartupError("OPENPANEL_API_URL must be an HTTP or HTTPS API base")
        client_id = env.get("OPENPANEL_CLIENT_ID", "")
        secret = env.get("OPENPANEL_CLIENT_SECRET", "")
        if not client_id or not secret:
            raise StartupError("OPENPANEL_CLIENT_ID and OPENPANEL_CLIENT_SECRET are required")
        if any(not 33 <= ord(char) <= 126 for char in client_id + secret):
            raise StartupError("OpenPanel credentials must contain visible ASCII without spaces")
        client = httpx.AsyncClient(
            base_url=base_url + "/",
            headers={
                "openpanel-client-id": client_id,
                "openpanel-client-secret": secret,
                "openpanel-sdk-name": "gateway7",
                "User-Agent": "gateway7-analytics",
            },
            timeout=EXPORT_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )
        # Membership above narrows the possible strings at runtime.
        return cls(
            client=client,
            environment=environment,  # type: ignore[arg-type]
            source=source,  # type: ignore[arg-type]
            participant_code=participant_code,
        )

    async def start(self) -> None:
        if self.enabled and self._worker is None:
            self._accepting = True
            self._worker = asyncio.create_task(self._export(), name="gateway7-analytics")

    def started(self, *, request_id: str, route: str) -> None:
        self._record("chat_started", request_id=request_id, route=route)

    def completed(self, *, request_id: str, route: str, status: int, duration_ms: float) -> None:
        self._record(
            "chat_completed",
            request_id=request_id,
            route=route,
            status=status,
            outcome=outcome_for(status),
            duration_ms=duration_ms,
        )

    def _record(
        self,
        name: Literal["chat_started", "chat_completed"],
        *,
        request_id: str,
        route: str,
        status: int | None = None,
        outcome: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        if not self._accepting or route not in CHAT_ROUTES:
            return
        try:
            event = TaskEvent(
                name=name,
                request_id=request_id,
                route=route,  # type: ignore[arg-type]
                environment=self.environment,
                source=self.source,
                participant_code=self.participant_code,
                occurred_at=datetime.now(timezone.utc),
                status=status,
                outcome=outcome,  # type: ignore[arg-type]
                duration_ms=max(0.0, duration_ms)
                if duration_ms is not None and math.isfinite(duration_ms)
                else None,
            )
            self._queue.put_nowait(event)
        except (ValueError, asyncio.QueueFull):
            logger.warning("request_id=- outcome=event_dropped component=analytics")

    async def _export(self) -> None:
        assert self._client is not None
        while True:
            event = await self._queue.get()
            try:
                # Relative path preserves a self-hosted base such as https://host/api/.
                # Stream the response without reading an unbounded backend body.
                async with self._client.stream(
                    "POST", "track", json=event.openpanel_payload()
                ) as response:
                    if response.status_code not in (200, 202):
                        logger.warning("request_id=- outcome=export_failed component=analytics")
            except Exception:
                # Never expose credentials, endpoint, backend text or exception details.
                logger.warning("request_id=- outcome=export_failed component=analytics")
            finally:
                self._queue.task_done()

    async def shutdown(self) -> None:
        """Drain for at most two seconds, then discard pending events and close."""
        self._accepting = False
        try:
            if self._worker is not None:
                try:
                    await asyncio.wait_for(self._queue.join(), timeout=SHUTDOWN_TIMEOUT_SECONDS)
                except TimeoutError:
                    logger.warning("request_id=- outcome=flush_timeout component=analytics")
                finally:
                    self._worker.cancel()
                    await asyncio.gather(self._worker, return_exceptions=True)
                    self._worker = None
        finally:
            client, self._client = self._client, None
            if client is not None:
                try:
                    await asyncio.wait_for(client.aclose(), timeout=EXPORT_TIMEOUT_SECONDS)
                except Exception:
                    logger.warning("request_id=- outcome=shutdown_error component=analytics")
