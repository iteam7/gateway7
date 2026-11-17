"""Bounded usage history, exact costs and conservative durable budget reservations.

Only numeric metadata is persisted. Unknown provider usage keeps its reserved
allowance; interrupted calls remain pending rather than silently becoming free.
Prices use integer micro-US dollars per million tokens, rounded upward per call.
"""

import asyncio
import csv
import io
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from gateway7.admin_store import _empty_counts, _valid_client_ids
from gateway7.config import validate_model_id
from gateway7.control_store import _identifier, _page, utc_timestamp
from gateway7.errors import GatewayError, normalized_usage


def _merge_counts(total: dict[str, Any], counts: dict[str, Any]) -> None:
    for name in _empty_counts():
        if name == "outcomes":
            for outcome, value in counts[name].items():
                total[name][outcome] += value
        else:
            total[name] += counts[name]


class BudgetDenied(ValueError):
    """A safe, content-free denial before a provider call starts."""


def _positive(value: Any, *, allow_none: bool = False) -> int | None:
    if value is None and allow_none:
        return None
    if type(value) is not int or not 1 <= value <= 10**24:
        raise ValueError("Budget amounts must be positive bounded integers")
    return value


def validate_prices(prices: Any) -> list[dict[str, Any]]:
    if type(prices) is not list or len(prices) > 512:
        raise ValueError("Invalid model pricing")
    result, seen = [], set()
    for price in prices:
        if type(price) is not dict or set(price) != {
            "model",
            "input_micro_usd_per_million",
            "output_micro_usd_per_million",
        }:
            raise ValueError("Invalid model pricing")
        model = validate_model_id(price["model"])
        if model in seen:
            raise ValueError("Duplicate model price")
        seen.add(model)
        for field in ("input_micro_usd_per_million", "output_micro_usd_per_million"):
            if type(price[field]) is not int or not 0 <= price[field] <= 10**18:
                raise ValueError("Invalid model price")
        result.append(dict(price))
    return result


def validate_rules(rules: Any) -> list[dict[str, Any]]:
    if type(rules) is not list or len(rules) > 1024:
        raise ValueError("Invalid budget rules")
    result, seen = [], set()
    for rule in rules:
        if type(rule) is not dict or set(rule) != {
            "id",
            "client_id",
            "model",
            "period",
            "tokens",
            "micro_usd",
            "mode",
            "enabled",
        }:
            raise ValueError("Invalid budget rule")
        identity = _identifier(rule["id"])
        if identity in seen:
            raise ValueError("Duplicate budget rule")
        seen.add(identity)
        if rule["client_id"] is not None:
            _valid_client_ids([rule["client_id"]])
        if rule["model"] is not None:
            validate_model_id(rule["model"])
        if (
            rule["period"] not in ("day", "month")
            or rule["mode"] not in ("warn", "hard")
            or type(rule["enabled"]) is not bool
        ):
            raise ValueError("Invalid budget rule")
        _positive(rule["tokens"], allow_none=True)
        _positive(rule["micro_usd"], allow_none=True)
        if rule["tokens"] is None and rule["micro_usd"] is None:
            raise ValueError("Budget rule requires a token or cost limit")
        result.append(dict(rule))
    return result


def validate_event(event: Any) -> None:
    if type(event) is not dict or event.get("kind") not in ("provider", "http"):
        raise ValueError("Invalid stored accounting event")
    _identifier(event["id"])
    _valid_client_ids([event["client_id"]])
    validate_model_id(event["model"])
    if utc_timestamp(event["started_at"]) != event["started_at"]:
        raise ValueError("Invalid stored accounting timestamp")
    if event.get("key_id") is not None:
        _identifier(event["key_id"])
    if event["kind"] == "http":
        _identifier(event["status"])
    else:
        if event["status"] not in ("pending", "complete", "provider_error", "cancelled"):
            raise ValueError("Invalid stored provider outcome")
        for name in ("input_bound", "output_bound"):
            _positive(event[name], allow_none=True)
        for name in (
            "known_input_tokens",
            "known_output_tokens",
            "charged_cost_micro_usd",
            "duration_ms",
        ):
            value = event.get(name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("Invalid stored accounting count")
        if type(event["charged_tokens"]) is not int or event["charged_tokens"] < 0:
            raise ValueError("Invalid stored accounting count")
        if event["price"] is not None:
            validate_prices([event["price"]])
            if event["price"]["model"] != event["model"]:
                raise ValueError("Invalid stored pricing model")
        for name in ("pricing_revision", "control_revision"):
            if type(event[name]) is not int or event[name] < 0:
                raise ValueError("Invalid stored pricing revision")
        if event["status"] == "pending":
            if (
                event.get("known_input_tokens") is not None
                or event.get("known_output_tokens") is not None
                or event.get("settled_at") is not None
            ):
                raise ValueError("Invalid pending usage reservation")
        else:
            utc_timestamp(event["settled_at"])
        input_count = event.get("known_input_tokens")
        output_count = event.get("known_output_tokens")
        charge_input = event["input_bound"] if input_count is None else input_count
        charge_output = event["output_bound"] if output_count is None else output_count
        if event["charged_tokens"] != (charge_input or 0) + (charge_output or 0):
            raise ValueError("Inconsistent stored token reservation")
        expected_cost = (
            None
            if event["price"] is None or charge_input is None or charge_output is None
            else _cost(charge_input, charge_output, event["price"])
        )
        if event["charged_cost_micro_usd"] != expected_cost:
            raise ValueError("Inconsistent stored cost reservation")


def _configuration(store: Any) -> tuple[int, dict[str, Any]]:
    control = store.read_control()
    accounting = control["data"].get("accounting", {})
    pricing = accounting.get("pricing", {"revision": 0, "prices": []})
    days = accounting.get("retention", {}).get("days", 90)
    if type(days) is not int or not 32 <= days <= 3650:
        raise ValueError("Invalid stored accounting retention")
    return control["revision"], {
        "pricing": {
            "revision": pricing.get("revision", 0),
            "prices": validate_prices(pricing.get("prices", [])),
        },
        "budgets": {"rules": validate_rules(accounting.get("budgets", {}).get("rules", []))},
        "retention": {"days": accounting.get("retention", {}).get("days", 90)},
    }


def _window(period: str, instant: str) -> tuple[str, str]:
    at = datetime.fromisoformat(utc_timestamp(instant))
    start = at.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "day":
        end = start + timedelta(days=1)
    else:
        start = start.replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return utc_timestamp(start.isoformat()), utc_timestamp(end.isoformat())


def _matches(rule: dict[str, Any], event: dict[str, Any]) -> bool:
    return all(rule[name] is None or rule[name] == event[name] for name in ("client_id", "model"))


def _cost(input_tokens: int, output_tokens: int, price: dict[str, Any]) -> int:
    amount = (
        input_tokens * price["input_micro_usd_per_million"]
        + output_tokens * price["output_micro_usd_per_million"]
    )
    return (amount + 999_999) // 1_000_000


def _events(store: Any, **filters: Any):
    offset = 0
    while True:
        page = store.list_usage_events(**filters, offset=offset, limit=500)
        yield from page["items"]
        offset += len(page["items"])
        if offset >= page["total"] or not page["items"]:
            break


def _legacy_rows(
    store: Any, *, start: str, end: str, client_id: str | None = None, model: str | None = None
):
    for table, column in (("legacy_usage", "counts"), ("archived_usage", "value")):
        sql = (
            "SELECT client_id,model,day,"
            + column
            + " FROM {prefix}"
            + table
            + " WHERE day>=? AND day<=?"
        )
        values: list[Any] = [start[:10], end[:10]]
        for name, value in (("client_id", client_id), ("model", model)):
            if value is not None:
                sql += " AND " + name + "=?"
                values.append(value)
        for identity, name, day, encoded in store._control_query(sql, values):
            at = utc_timestamp(day + "T00:00:00Z")
            until = utc_timestamp((datetime.fromisoformat(at) + timedelta(days=1)).isoformat())
            decoded = json.loads(encoded)
            if table == "legacy_usage":
                decoded.update(cost_micro_usd=0, unknown_cost_attempts=decoded["provider_attempts"])
            yield (
                {"client_id": identity, "model": name, "day": day, **decoded},
                at >= start and until <= end,
            )


def _rule_status(store: Any, rule: dict[str, Any], instant: str) -> dict[str, Any]:
    start, end = _window(rule["period"], instant)
    used_tokens = used_cost = reserved_tokens = reserved_cost = unknown_cost = 0
    for event in _events(
        store, start=start, end=end, client_id=rule["client_id"], model=rule["model"]
    ):
        if event.get("kind") != "provider":
            continue
        if (
            event["status"] == "pending"
            or event.get("known_input_tokens") is None
            or event.get("known_output_tokens") is None
        ):
            reserved_tokens += event["charged_tokens"]
            reserved_cost += event.get("charged_cost_micro_usd") or 0
        else:
            used_tokens += event["charged_tokens"]
            used_cost += event.get("charged_cost_micro_usd") or 0
        unknown_cost += event.get("charged_cost_micro_usd") is None
    unknown_usage = sum(
        (event.get("input_bound") is None and event.get("known_input_tokens") is None)
        or (event.get("output_bound") is None and event.get("known_output_tokens") is None)
        for event in _events(
            store, start=start, end=end, client_id=rule["client_id"], model=rule["model"]
        )
        if event.get("kind") == "provider"
    )
    for legacy, included in _legacy_rows(
        store, start=start, end=end, client_id=rule["client_id"], model=rule["model"]
    ):
        if included:
            used_tokens += legacy["known_input_tokens"] + legacy["known_output_tokens"]
            used_cost += legacy["cost_micro_usd"]
            unknown_cost += legacy["unknown_cost_attempts"]
            unknown_usage += (
                legacy["input_usage_unknown_attempts"] + legacy["output_usage_unknown_attempts"]
            )
    tokens = used_tokens + reserved_tokens
    cost = used_cost + reserved_cost
    warning = (rule["tokens"] is not None and tokens * 100 >= rule["tokens"] * 80) or (
        rule["micro_usd"] is not None and cost * 100 >= rule["micro_usd"] * 80
    )
    exhausted = (rule["tokens"] is not None and tokens >= rule["tokens"]) or (
        rule["micro_usd"] is not None and (cost >= rule["micro_usd"] or unknown_cost > 0)
    )
    return {
        **rule,
        "window_start": start,
        "window_end": end,
        "used_tokens": used_tokens,
        "reserved_tokens": reserved_tokens,
        "used_micro_usd": used_cost,
        "reserved_micro_usd": reserved_cost,
        "unknown_cost_attempts": unknown_cost,
        "unknown_usage_attempts": unknown_usage,
        "warning": bool(warning),
        "exhausted": bool(exhausted),
    }


def reserve_locked(
    store: Any,
    client_id: str,
    model: str,
    input_bound: int | None,
    output_bound: int | None,
    *,
    key_id: str | None,
    started_at: str | None,
) -> dict[str, Any]:
    _valid_client_ids([client_id])
    validate_model_id(model)
    _positive(input_bound, allow_none=True)
    _positive(output_bound, allow_none=True)
    if key_id is not None:
        _identifier(key_id)
    started = utc_timestamp(started_at)
    revision, configuration = _configuration(store)
    pricing = configuration["pricing"]
    price = next((row for row in pricing["prices"] if row["model"] == model), None)
    event = {
        "id": uuid.uuid4().hex,
        "kind": "provider",
        "started_at": started,
        "client_id": client_id,
        "model": model,
        "key_id": key_id,
        "status": "pending",
        "input_bound": input_bound,
        "output_bound": output_bound,
        "charged_tokens": (input_bound or 0) + (output_bound or 0),
        "charged_cost_micro_usd": None
        if price is None or input_bound is None or output_bound is None
        else _cost(input_bound, output_bound, price),
        "price": price,
        "pricing_revision": pricing["revision"],
        "control_revision": revision,
        "known_input_tokens": None,
        "known_output_tokens": None,
        "duration_ms": None,
        "settled_at": None,
        "http_outcome": None,
    }
    for rule in configuration["budgets"]["rules"]:
        if not rule["enabled"] or rule["mode"] != "hard" or not _matches(rule, event):
            continue
        if input_bound is None or output_bound is None:
            raise BudgetDenied("Hard budgets require a finite enforceable request bound")
        status = _rule_status(store, rule, started)
        if rule["tokens"] is not None and status.get("unknown_usage_attempts", 0):
            raise BudgetDenied("Hard token budget cannot ignore historical unknown usage")
        if (
            rule["tokens"] is not None
            and status["used_tokens"] + status["reserved_tokens"] + event["charged_tokens"]
            > rule["tokens"]
        ):
            raise BudgetDenied("Token budget has insufficient available allowance")
        if rule["micro_usd"] is not None:
            if event["charged_cost_micro_usd"] is None or status["unknown_cost_attempts"]:
                raise BudgetDenied("Hard cost budget requires known model pricing and usage")
            if (
                status["used_micro_usd"]
                + status["reserved_micro_usd"]
                + event["charged_cost_micro_usd"]
                > rule["micro_usd"]
            ):
                raise BudgetDenied("Cost budget has insufficient available allowance")
    store._put_usage_event(event)
    return event


def settle_locked(
    store: Any,
    attempt_id: str,
    outcome: str,
    usage: dict[str, int] | None,
    *,
    duration_ms: int,
    http_outcome: str | None,
) -> dict[str, Any]:
    _identifier(attempt_id)
    event = store._get_usage_event(attempt_id)
    if event["status"] != "pending":
        return event
    counts = normalized_usage(usage) or {}
    event["status"] = (
        outcome if outcome in ("complete", "provider_error", "cancelled") else "provider_error"
    )
    event["settled_at"] = utc_timestamp()
    event["duration_ms"] = max(0, int(duration_ms))
    event["http_outcome"] = http_outcome
    event["known_input_tokens"] = counts.get("input_tokens")
    event["known_output_tokens"] = counts.get("output_tokens")
    charged_input = counts.get("input_tokens", event["input_bound"] or 0)
    charged_output = counts.get("output_tokens", event["output_bound"] or 0)
    event["charged_tokens"] = charged_input + charged_output
    event["charged_cost_micro_usd"] = (
        None
        if event["price"] is None
        or (event["input_bound"] is None and "input_tokens" not in counts)
        or (event["output_bound"] is None and "output_tokens" not in counts)
        else _cost(charged_input, charged_output, event["price"])
    )
    event["reservation_exceeded"] = (
        event["input_bound"] is not None and charged_input > event["input_bound"]
    ) or (event["output_bound"] is not None and charged_output > event["output_bound"])
    store._put_usage_event(event)
    # Maintain the existing durable daily report, attributing to provider START.
    day = event["started_at"][:10]
    stored = store._control_query(
        "SELECT counts FROM {prefix}usage WHERE client_id=? AND model=? AND day=?",
        (event["client_id"], event["model"], day),
    ).fetchone()
    row = json.loads(stored[0]) if stored else _empty_counts()
    row["provider_attempts"] += 1
    row["outcomes"][event["status"]] += 1
    for direction in ("input", "output"):
        count = counts.get(direction + "_tokens")
        if count is None:
            row[direction + "_usage_unknown_attempts"] += 1
        else:
            row["known_" + direction + "_tokens"] += count
    store._control_query(
        "INSERT INTO {prefix}usage(client_id,model,day,counts) VALUES (?,?,?,?) ON CONFLICT(client_id,model,day) DO UPDATE SET counts=excluded.counts",
        (event["client_id"], event["model"], day, json.dumps(row)),
    )
    return event


def _event_counts(event: dict[str, Any]) -> dict[str, Any]:
    counts = _empty_counts()
    if event.get("kind") != "provider":
        return counts
    counts["provider_attempts"] = 1
    status = event["status"]
    if status != "pending":
        counts["outcomes"][status] = 1
    for direction in ("input", "output"):
        value = event.get("known_" + direction + "_tokens")
        if value is None:
            counts[direction + "_usage_unknown_attempts"] = 1
        else:
            counts["known_" + direction + "_tokens"] = value
    return counts


class AccountingService:
    """Async facade; every SQL operation runs on the app's bounded DB worker."""

    def __init__(self, store: Any, db: Any) -> None:
        self.store, self.db = store, db
        self.authorize: Any = None
        self._exports = 0
        self._maintenance = asyncio.Lock()

    async def policies(self) -> dict[str, Any]:
        revision, configuration = await self.db.call(_configuration, self.store)
        return {"revision": revision, **configuration}

    get_policies = policies

    async def _update(
        self, expected_revision: int, field: str, value: Any, audit: dict[str, Any]
    ) -> dict[str, Any]:
        control = await self.db.call(self.store.read_control)
        data = control["data"]
        accounting = dict(data.get("accounting", {}))
        accounting[field] = value
        data["accounting"] = accounting

        def commit():
            if self.authorize is not None:
                self.authorize()
            return self.store.write_control(expected_revision, data, audit)

        await self.db.call(commit)
        return await self.policies()

    async def update_pricing(
        self, expected_revision: int, prices: Any, audit: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._update(
            expected_revision,
            "pricing",
            {"revision": expected_revision + 1, "prices": validate_prices(prices)},
            audit,
        )

    async def update_budgets(
        self, expected_revision: int, rules: Any, audit: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._update(
            expected_revision, "budgets", {"rules": validate_rules(rules)}, audit
        )

    async def update_retention(
        self, expected_revision: int, days: int, audit: dict[str, Any]
    ) -> dict[str, Any]:
        if type(days) is not int or not 32 <= days <= 3650:
            raise ValueError(
                "Retention must be between 32 and 3650 days to preserve budget windows"
            )
        return await self._update(expected_revision, "retention", {"days": days}, audit)

    async def budget_status(
        self, client_id: str | None = None, model: str | None = None
    ) -> dict[str, Any]:
        def read():
            _, configuration = _configuration(self.store)
            return {
                "items": [
                    _rule_status(self.store, rule, utc_timestamp())
                    for rule in configuration["budgets"]["rules"]
                    if rule["enabled"]
                    and (client_id is None or rule["client_id"] in (None, client_id))
                    and (model is None or rule["model"] in (None, model))
                ]
            }

        return await self.db.call(read)

    def bind(
        self,
        client_id: str,
        model: str,
        *,
        key_id: str | None = None,
        request_id: str | None = None,
        route: str | None = None,
        started_at: str | None = None,
    ):
        reservation: dict[str, Any] | None = None
        started_clock = 0.0

        async def before(request: Any) -> None:
            nonlocal reservation, started_clock
            payload = request.model_dump(mode="json")
            serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            configuration = await self.policies()
            hard = any(
                rule["enabled"]
                and rule["mode"] == "hard"
                and _matches(rule, {"client_id": client_id, "model": model})
                for rule in configuration["budgets"]["rules"]
            )

            # Non-text remote/file/image/audio input has no safe local token bound.
            def unsafe(value: Any) -> bool:
                if isinstance(value, dict):
                    kind = value.get("type", "")
                    if isinstance(kind, str) and any(
                        word in kind
                        for word in ("image", "audio", "video", "file", "computer", "search")
                    ):
                        return True
                    return any(unsafe(child) for child in value.values())
                if isinstance(value, list):
                    return any(unsafe(child) for child in value)
                return False

            unsafe_payload = unsafe(payload)
            if hard and unsafe_payload:
                raise GatewayError("budget_exceeded")
            input_bound: int | None = (
                len(serialized.encode("utf-8")) + 1024 + 32 * len(payload.get("messages", []))
            )
            output_bound = payload.get("max_tokens", payload.get("max_output_tokens"))
            if type(output_bound) is not int or output_bound < 1:
                if hard:
                    raise GatewayError("budget_exceeded")
                output_bound = None
            if unsafe_payload:
                input_bound = None
            started_clock = time.monotonic()
            try:
                reservation = await self.db.call(
                    self.store.reserve_usage,
                    client_id,
                    model,
                    input_bound,
                    output_bound,
                    key_id=key_id,
                    started_at=started_at,
                )
            except BudgetDenied:
                raise GatewayError("budget_exceeded") from None

        async def observer(outcome: str, usage: dict[str, int] | None) -> None:
            if reservation is None:
                return
            from gateway7.loader import complete_cleanup

            async def settle() -> None:
                await self.db.call(
                    self.store.settle_usage,
                    reservation["id"],
                    outcome,
                    usage,
                    duration_ms=int((time.monotonic() - started_clock) * 1000),
                )

            await complete_cleanup(settle())

        return before, observer

    async def history(self, **filters: Any) -> dict[str, Any]:
        for name in ("start", "end"):
            if filters.get(name) is not None:
                filters[name] = utc_timestamp(filters[name])
        if (
            filters.get("start") is not None
            and filters.get("end") is not None
            and filters["start"] >= filters["end"]
        ):
            raise ValueError("History start must precede end")
        if filters.get("client_id") is not None:
            _valid_client_ids([filters["client_id"]])
        if filters.get("model") is not None:
            validate_model_id(filters["model"])
        return await self.db.call(self.store.list_usage_events, **filters)

    async def report(
        self,
        *,
        client_id: str | None = None,
        model: str | None = None,
        start: str | None = None,
        end: str | None = None,
        bucket: str = "day",
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        _page(offset, limit)
        if bucket not in ("hour", "day"):
            raise ValueError("Report bucket must be hour or day")
        end = utc_timestamp(end)
        start = utc_timestamp(
            start or (datetime.fromisoformat(end) - timedelta(days=30)).isoformat()
        )
        if start >= end:
            raise ValueError("Report start must precede end")
        if client_id is not None:
            _valid_client_ids([client_id])
        if model is not None:
            validate_model_id(model)

        def read():
            group_page = self.store.usage_group_page(
                start=start, end=end, client_id=client_id, model=model, offset=offset, limit=limit
            )
            groups: dict[tuple[str, str, str], dict[str, Any]] = {
                tuple(key): {
                    "client_id": key[0],
                    "model": key[1],
                    "day": key[2],
                    **_empty_counts(),
                    "cost_micro_usd": 0,
                    "unknown_cost_attempts": 0,
                }
                for key in group_page["keys"]
            }
            clients: dict[str, Any] = {}
            series: dict[str, dict[str, Any]] = {}
            summary = {
                **_empty_counts(),
                "cost_micro_usd": 0,
                "unknown_cost_attempts": 0,
                "pending_attempts": 0,
            }
            for event in _events(
                self.store, start=start, end=end, client_id=client_id, model=model
            ):
                if event.get("kind") != "provider":
                    continue
                counts = _event_counts(event)
                _merge_counts(summary, counts)
                _merge_counts(clients.setdefault(event["client_id"], _empty_counts()), counts)
                key = (event["client_id"], event["model"], event["started_at"][:10])
                group = groups.get(key)
                if group is not None:
                    _merge_counts(group, counts)
                cost = (
                    None
                    if event.get("known_input_tokens") is None
                    or event.get("known_output_tokens") is None
                    or event.get("price") is None
                    else _cost(
                        event["known_input_tokens"], event["known_output_tokens"], event["price"]
                    )
                )
                if cost is None:
                    summary["unknown_cost_attempts"] += 1
                    if group is not None:
                        group["unknown_cost_attempts"] += 1
                else:
                    summary["cost_micro_usd"] += cost
                    if group is not None:
                        group["cost_micro_usd"] += cost
                summary["pending_attempts"] += event["status"] == "pending"
                at = (
                    event["started_at"][:13] + ":00:00+00:00"
                    if bucket == "hour"
                    else event["started_at"][:10] + "T00:00:00+00:00"
                )
                point = series.setdefault(at, {"at": at, **_empty_counts(), "cost_micro_usd": 0})
                _merge_counts(point, counts)
                point["cost_micro_usd"] += cost or 0
            legacy_count = legacy_excluded = 0
            for legacy, included in _legacy_rows(
                self.store, start=start, end=end, client_id=client_id, model=model
            ):
                if not included:
                    legacy_excluded += 1
                    continue
                legacy_count += 1
                _merge_counts(summary, legacy)
                _merge_counts(clients.setdefault(legacy["client_id"], _empty_counts()), legacy)
                key = (legacy["client_id"], legacy["model"], legacy["day"])
                group = groups.get(key)
                if group is not None:
                    _merge_counts(group, legacy)
                    group["precision"] = "day"
                    group["cost_micro_usd"] += legacy["cost_micro_usd"]
                    group["unknown_cost_attempts"] += legacy["unknown_cost_attempts"]
                summary["cost_micro_usd"] += legacy["cost_micro_usd"]
                summary["unknown_cost_attempts"] += legacy["unknown_cost_attempts"]
                if bucket == "day":
                    at = legacy["day"] + "T00:00:00+00:00"
                    point = series.setdefault(
                        at, {"at": at, **_empty_counts(), "cost_micro_usd": 0}
                    )
                    _merge_counts(point, legacy)
                    point["cost_micro_usd"] += legacy["cost_micro_usd"]
            rows = [groups[key] for key in sorted(groups)]
            return {
                "scope": "persistent",
                "started_at": self.store.started_at,
                "reset_on_restart": False,
                "clients": clients,
                "rows": rows,
                "summary": summary,
                "timeseries": [series[key] for key in sorted(series)],
                "pagination": {"offset": offset, "limit": limit, "total": group_page["total"]},
                "filters": {
                    "client_id": client_id,
                    "model": model,
                    "start": start,
                    "end": end,
                    "bucket": bucket,
                },
                "legacy_daily_precision": legacy_count > 0,
                "legacy_daily_rows_excluded": legacy_excluded,
                "retention": {
                    "detail_days": _configuration(self.store)[1]["retention"]["days"],
                    "detail_retained_from": dict(
                        self.store._control_query("SELECT name,value FROM {prefix}metadata")
                    ).get("detail_retained_from"),
                    "daily_rollups_retained": True,
                },
            }

        return await self.db.call(read)

    async def _iter_csv(
        self,
        *,
        client_id: str | None = None,
        model: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ):
        # A captured upper bound and an ascending keyset prevent newly inserted
        # rows from shifting already exported pages or duplicating old records.
        end = utc_timestamp(end)
        start = utc_timestamp(
            start or (datetime.fromisoformat(end) - timedelta(days=30)).isoformat()
        )
        if start >= end:
            raise ValueError("Export start must precede end")
        if client_id is not None:
            _valid_client_ids([client_id])
        if model is not None:
            validate_model_id(model)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        fields = [
            "started_at",
            "day",
            "precision",
            "client_id",
            "model",
            "status",
            "provider_attempts",
            "known_input_tokens",
            "known_output_tokens",
            "cost_micro_usd",
            "unknown_cost_attempts",
            "charged_cost_micro_usd",
            "pricing_revision",
        ]
        writer.writerow(fields)
        yield buffer.getvalue()
        after = None
        while True:
            page = await self.db.call(
                self.store.usage_export_page,
                start=start,
                end=end,
                client_id=client_id,
                model=model,
                after=after,
                limit=500,
            )
            if not page:
                break
            buffer.seek(0)
            buffer.truncate(0)
            for event in page:
                known_cost = (
                    None
                    if event.get("price") is None
                    or event.get("known_input_tokens") is None
                    or event.get("known_output_tokens") is None
                    else _cost(
                        event["known_input_tokens"], event["known_output_tokens"], event["price"]
                    )
                )
                event = {
                    **event,
                    "day": event["started_at"][:10],
                    "precision": "timestamp",
                    "provider_attempts": 1,
                    "cost_micro_usd": known_cost,
                    "unknown_cost_attempts": int(known_cost is None),
                }
                writer.writerow(
                    [
                        (
                            "'" + value
                            if isinstance(value := event.get(field), str)
                            and value.startswith(("=", "+", "-", "@"))
                            else value
                        )
                        for field in fields
                    ]
                )
            after = (page[-1]["started_at"], page[-1]["id"])
            yield buffer.getvalue()
            if len(page) < 500:
                break
        coarse_after = None
        while True:
            page = await self.db.call(
                self.store.legacy_export_page,
                start=start,
                end=end,
                client_id=client_id,
                model=model,
                after=coarse_after,
                limit=500,
            )
            if not page:
                break
            buffer.seek(0)
            buffer.truncate(0)
            for row in page:
                row["precision"] = "day"
                writer.writerow(
                    [
                        (
                            "'" + value
                            if isinstance(value := row.get(field), str)
                            and value.startswith(("=", "+", "-", "@"))
                            else value
                        )
                        for field in fields
                    ]
                )
            coarse_after = (
                page[-1]["day"],
                page[-1]["client_id"],
                page[-1]["model"],
                page[-1]["source"],
            )
            yield buffer.getvalue()
            if len(page) < 500:
                break

    async def iter_csv(self, **filters: Any):
        await self._maintenance.acquire()
        self._exports += 1
        try:
            async for chunk in self._iter_csv(**filters):
                yield chunk
        finally:
            self._exports -= 1
            self._maintenance.release()

    async def record_http(
        self,
        *,
        client_id: str,
        model: str | None = None,
        key_id: str | None = None,
        started_at: str | None = None,
        outcome: str,
        duration_ms: int = 0,
        request_id: str | None = None,
        route: str | None = None,
    ) -> None:
        _valid_client_ids([client_id])
        if key_id is not None:
            _identifier(key_id)
        event = {
            "id": uuid.uuid4().hex,
            "kind": "http",
            "started_at": utc_timestamp(started_at),
            "client_id": client_id,
            "model": model or "unselected",
            "key_id": key_id,
            "status": _identifier(outcome),
            "duration_ms": max(0, int(duration_ms)),
            "request_id": request_id,
            "route": route,
        }

        def save():
            with self.store._lock, self.store._control_transaction():
                self.store._put_usage_event(event)

        await self.db.call(save)

    async def diagnostics(self, **filters: Any) -> dict[str, Any]:
        if filters.get("end") is None:
            filters["end"] = utc_timestamp()
        if filters.get("start") is None:
            filters["start"] = utc_timestamp(
                (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            )

        def read():
            page = self.store.list_usage_events(**filters)
            result = {
                **page,
                "http_outcomes": {},
                "last_seen": None,
                "mean_latency_ms": None,
                "key_last_used": self.store.key_last_used(),
            }
            total_duration = total_count = 0
            selection = {
                key: value for key, value in filters.items() if key not in ("offset", "limit")
            }
            for event in _events(self.store, **selection):
                if result["last_seen"] is None or event["started_at"] > result["last_seen"]:
                    result["last_seen"] = event["started_at"]
                if event.get("kind") == "http":
                    result["http_outcomes"][event["status"]] = (
                        result["http_outcomes"].get(event["status"], 0) + 1
                    )
                    if event.get("duration_ms") is not None:
                        total_duration += event["duration_ms"]
                        total_count += 1
            if total_count:
                result["mean_latency_ms"] = total_duration / total_count
            return result

        return await self.db.call(read)

    async def purge(self) -> dict[str, int]:
        if self._maintenance.locked():
            return {"events_deleted": 0, "audit_deleted": 0, "skipped_active_exports": 1}
        async with self._maintenance:
            return await self._purge_owned()

    async def _purge_owned(self) -> dict[str, int]:
        policy = await self.policies()
        cutoff = utc_timestamp(
            (
                datetime.now(timezone.utc) - timedelta(days=max(32, policy["retention"]["days"]))
            ).isoformat()
        )

        def remove():
            removed = 0
            with self.store._lock, self.store._control_transaction():
                while True:
                    batch = list(
                        self.store._control_query(
                            "SELECT id,value FROM {prefix}usage_events WHERE started_at<? AND status<>'pending' ORDER BY started_at,id LIMIT 500",
                            (cutoff,),
                        )
                    )
                    if not batch:
                        break
                    for identity, encoded in batch:
                        event = json.loads(encoded)
                        if event["kind"] == "provider":
                            key = (event["client_id"], event["model"], event["started_at"][:10])
                            existing = self.store._control_query(
                                "SELECT value FROM {prefix}archived_usage WHERE client_id=? AND model=? AND day=?",
                                key,
                            ).fetchone()
                            row = (
                                json.loads(existing[0])
                                if existing
                                else {
                                    **_empty_counts(),
                                    "cost_micro_usd": 0,
                                    "unknown_cost_attempts": 0,
                                }
                            )
                            _merge_counts(row, _event_counts(event))
                            if (
                                event["price"] is not None
                                and event.get("known_input_tokens") is not None
                                and event.get("known_output_tokens") is not None
                            ):
                                row["cost_micro_usd"] += _cost(
                                    event["known_input_tokens"],
                                    event["known_output_tokens"],
                                    event["price"],
                                )
                            else:
                                row["unknown_cost_attempts"] += 1
                            self.store._control_query(
                                "INSERT INTO {prefix}archived_usage(client_id,model,day,value) VALUES (?,?,?,?) ON CONFLICT(client_id,model,day) DO UPDATE SET value=excluded.value",
                                (*key, json.dumps(row)),
                            )
                        self.store._control_query(
                            "DELETE FROM {prefix}usage_events WHERE id=?", (identity,)
                        )
                        removed += 1
                audit = self.store._control_query(
                    "DELETE FROM {prefix}control_audit WHERE at<?", (cutoff,)
                ).rowcount
                if removed:
                    previous = self.store._control_query(
                        "SELECT value FROM {prefix}metadata WHERE name='detail_retained_from'"
                    ).fetchone()
                    boundary = max(cutoff, previous[0]) if previous else cutoff
                    self.store._control_query(
                        "INSERT INTO {prefix}metadata(name,value) VALUES ('detail_retained_from',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                        (boundary,),
                    )
            return {"events_deleted": removed, "audit_deleted": audit}

        return await self.db.call(remove)
