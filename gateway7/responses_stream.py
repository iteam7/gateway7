"""Bounded native Responses SSE state, independent of request/consent validation."""

import codecs
from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
import re
from typing import Any, cast

from pydantic import TypeAdapter

from gateway7.errors import ProviderError, ProviderErrorReason
from gateway7.models import argument_object
from gateway7.responses_events import ResponsesStreamHead, ResponsesTextDelta
from gateway7.responses_models import (
    ResponseTool,
    ResponsesResponseEchoes,
    project_provider_response,
)

MAX_RESPONSE_BYTES = 1_048_576
MAX_EVENT_BYTES = 65_536
_MAX_INTEGER = 2**63 - 1
_MAX_JSON_DEPTH = 64
_RESPONSE_IDENTITY_FIELDS = ("id", "object", "created_at", "model")
_RESPONSE_TOOLS = TypeAdapter(list[ResponseTool])
_ID = re.compile(r"[A-Za-z0-9_-]+\Z")
_REF = {"output_index", "item_id"}
_CONTENT = _REF | {"content_index"}
_SUMMARY = _REF | {"summary_index"}
_EVENT_FIELDS = {
    **{
        f"response.{name}": {"response"}
        for name in ("created", "in_progress", "completed", "incomplete", "failed")
    },
    **{f"response.output_item.{name}": {"output_index", "item"} for name in ("added", "done")},
    **{f"response.content_part.{name}": _CONTENT | {"part"} for name in ("added", "done")},
    **{
        f"response.output_text.{name}": _CONTENT
        | {"delta" if name == "delta" else "text", "logprobs"}
        for name in ("delta", "done")
    },
    **{
        f"response.refusal.{name}": _CONTENT | {"delta" if name == "delta" else "refusal"}
        for name in ("delta", "done")
    },
    **{
        f"response.function_call_arguments.{name}": _REF
        | {"delta" if name == "delta" else "arguments"}
        for name in ("delta", "done")
    },
    **{
        f"response.custom_tool_call_input.{name}": _REF | {"delta" if name == "delta" else "input"}
        for name in ("delta", "done")
    },
    **{
        f"response.reasoning_summary_part.{name}": _SUMMARY | {"part"} for name in ("added", "done")
    },
    **{
        f"response.reasoning_summary_text.{name}": _SUMMARY
        | {"delta" if name == "delta" else "text"}
        for name in ("delta", "done")
    },
    **{
        f"response.reasoning_text.{name}": _CONTENT | {"delta" if name == "delta" else "text"}
        for name in ("delta", "done")
    },
    **{
        f"response.web_search_call.{name}": _REF
        for name in ("in_progress", "searching", "completed")
    },
    "response.output_text.annotation.added": _CONTENT | {"annotation_index"},
    "error": {"message"},
}
_OPTIONAL_FIELDS = {
    "error": {"code", "param"},
    "response.output_text.delta": {"obfuscation"},
    "response.custom_tool_call_input.delta": {"call_id"},
    "response.custom_tool_call_input.done": {"call_id"},
    "response.reasoning_summary_part.done": {"status"},
    "response.output_text.annotation.added": {"annotation"},
}
# The projected native HTTP envelope, including its typed echo fields.
# Event roots and semantic item trees remain closed independently of projection.
_RESPONSE_FIELDS = {
    "id",
    "object",
    "created_at",
    "model",
    "status",
    "output",
    "usage",
    "error",
    "incomplete_details",
    "completed_at",
    "parallel_tool_calls",
    "tool_choice",
    "tools",
    "instructions",
    "reasoning",
    "text",
    "max_output_tokens",
    "prompt_cache_key",
    "service_tier",
    "store",
    "metadata",
    "temperature",
    "top_p",
    "truncation",
    "background",
    "previous_response_id",
} | set(ResponsesResponseEchoes.model_fields)
_ITEM_FIELDS = {
    "message": {"role", "content", "phase"},
    "function_call": {
        "call_id",
        "name",
        "namespace",
        "arguments",
        "async",
        "caller",
        "encrypted_function_args",
    },
    "custom_tool_call": {"call_id", "name", "namespace", "input", "async", "caller"},
    "reasoning": {"summary", "content", "encrypted_content"},
    "web_search_call": {"action"},
    "tool_search_call": {"execution", "call_id", "arguments", "created_by"},
    "tool_search_output": {"execution", "call_id", "tools", "created_by"},
}
_IMMUTABLE = (
    "id",
    "type",
    "role",
    "phase",
    "call_id",
    "name",
    "namespace",
    "execution",
    "created_by",
    "async",
    "caller",
)


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("Invalid Responses stream")


def _integer(value: Any, maximum: int = _MAX_INTEGER) -> int:
    _require(type(value) is int and 0 <= value <= maximum)
    return cast(int, value)


def _string(value: Any) -> str:
    _require(isinstance(value, str))
    return cast(str, value)


def _identifier(value: Any) -> str:
    result = _string(value)
    _require(_ID.fullmatch(result) is not None)
    return result


def _object(value: Any) -> dict[str, Any]:
    _require(isinstance(value, dict))
    return cast(dict[str, Any], value)


def _same(left: Any, right: Any) -> bool:
    """JSON identity must not equate boolean values with integer counters."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _same(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return bool(left == right)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _bounded_depth(value: Any) -> None:
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        _require(depth <= _MAX_JSON_DEPTH)
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def _copy_native_usage(value: dict[str, Any]) -> dict[str, object]:
    # Validated usage has exactly two mutable levels; counts are integers or null.
    return {name: item.copy() if isinstance(item, dict) else item for name, item in value.items()}


def _reject_constant(_: str) -> None:
    raise ValueError("Invalid JSON number")


def _finite_float(value: str) -> float:
    result = float(value)
    _require(math.isfinite(result))
    return result


def _annotation(value: Any) -> None:
    value = _object(value)
    shapes = {
        "file_citation": {"file_id", "filename", "index"},
        "url_citation": {"url", "title", "start_index", "end_index"},
        "container_file_citation": {
            "container_id",
            "file_id",
            "filename",
            "start_index",
            "end_index",
        },
        "file_path": {"file_id", "index"},
    }
    kind = value.get("type")
    _require(isinstance(kind, str) and kind in shapes)
    _require(set(value) == shapes[kind] | {"type"})
    for name, item in value.items():
        if name.endswith("index"):
            _integer(item)
        else:
            _string(item)
    if "end_index" in value:
        _require(value["start_index"] <= value["end_index"])


def _event_logprobs(value: Any) -> list[Any]:
    """Delta/done records have no byte field, and optional partial top records."""
    _require(isinstance(value, list))
    for item in value:
        item = _object(item)
        _require({"token", "logprob"} <= set(item) <= {"token", "logprob", "top_logprobs"})
        _string(item["token"])
        _require(type(item["logprob"]) in (int, float) and math.isfinite(item["logprob"]))
        top = item.get("top_logprobs")
        if top is not None:
            _require(isinstance(top, list))
            for candidate in top:
                candidate = _object(candidate)
                _require(set(candidate) <= {"token", "logprob"})
                if candidate.get("token") is not None:
                    _string(candidate["token"])
                if candidate.get("logprob") is not None:
                    _require(
                        type(candidate["logprob"]) in (int, float)
                        and math.isfinite(candidate["logprob"])
                    )
    return cast(list[Any], value)


def _output_logprobs(value: Any, *, top: bool = False) -> list[Any]:
    """Final output-part records carry bytes and complete top-token records."""
    _require(isinstance(value, list))
    for item in value:
        item = _object(item)
        _require(set(item) == {"token", "bytes", "logprob"} | (set() if top else {"top_logprobs"}))
        _string(item["token"])
        _require(type(item["logprob"]) in (int, float) and math.isfinite(item["logprob"]))
        _require(isinstance(item["bytes"], list))
        for byte in item["bytes"]:
            _integer(byte, 255)
        if not top:
            _output_logprobs(item["top_logprobs"], top=True)
    return cast(list[Any], value)


def _match_logprobs(left: list[Any], right: list[Any]) -> None:
    """Compare supplied common facts, without manufacturing bytes or unknown tops."""
    _require(len(left) == len(right))
    for a, b in zip(left, right):
        _require(a["token"] == b["token"] and a["logprob"] == b["logprob"])
        top_a, top_b = a.get("top_logprobs"), b.get("top_logprobs")
        if top_a is not None and top_b is not None:
            _require(len(top_a) == len(top_b))
            for candidate_a, candidate_b in zip(top_a, top_b):
                for name in ("token", "logprob"):
                    if candidate_a.get(name) is not None and candidate_b.get(name) is not None:
                        _require(candidate_a[name] == candidate_b[name])


def _part(value: Any) -> dict[str, Any]:
    value = _object(value)
    kind = value.get("type")
    if kind == "output_text":
        _require(
            {"type", "text", "annotations"}
            <= set(value)
            <= {"type", "text", "annotations", "logprobs"}
        )
        _string(value["text"])
        _require(isinstance(value["annotations"], list))
        for annotation in value["annotations"]:
            _annotation(annotation)
        if value.get("logprobs") is not None:
            _output_logprobs(value["logprobs"])
    else:
        name = "refusal" if kind == "refusal" else "text"
        _require(
            kind in ("refusal", "summary_text", "reasoning_text") and set(value) == {"type", name}
        )
        _string(value[name])
    return value


def _web_action(value: Any) -> None:
    value = _object(value)
    kind = value.get("type")
    fields = {
        "search": {"type", "queries", "query", "sources"},
        "open_page": {"type", "url"},
        "find_in_page": {"type", "url", "pattern"},
    }
    _require(isinstance(kind, str) and kind in fields and set(value) <= fields[kind])
    for name in ("query", "url", "pattern"):
        if value.get(name) is not None:
            _string(value[name])
    if kind == "find_in_page":
        _require({"url", "pattern"} <= set(value))
    if value.get("queries") is not None:
        _require(isinstance(value["queries"], list))
        for query in value["queries"]:
            _string(query)
    if value.get("sources") is not None:
        _require(isinstance(value["sources"], list))
        for source in value["sources"]:
            source = _object(source)
            _require(set(source) == {"type", "url"} and source["type"] == "url")
            _string(source["url"])


def _item(value: Any, *, done: bool) -> dict[str, Any]:
    value = _object(value)
    kind = value.get("type")
    _require(isinstance(kind, str) and kind in _ITEM_FIELDS)
    _require(
        set(value)
        <= _ITEM_FIELDS[kind]
        | {"id", "type", "status", "internal_chat_message_metadata_passthrough"}
    )
    _identifier(value.get("id"))
    status = value.get("status")
    if status is not None:
        _require(
            status
            in (
                ("completed", "incomplete", "failed")
                if done and kind == "web_search_call"
                else ("completed", "incomplete")
                if done
                else ("in_progress",)
            )
        )
    if kind == "message":
        _require(value.get("role") == "assistant" and status is not None)
        _require(value.get("phase") in (None, "commentary", "final_answer"))
        _require(isinstance(value.get("content"), list))
        for part in value["content"]:
            _require(_part(part)["type"] in ("output_text", "refusal"))
        if not done:
            _require(value["content"] == [])
    elif kind in ("function_call", "custom_tool_call"):
        _identifier(value.get("call_id"))
        _identifier(value.get("name"))
        if value.get("namespace") is not None:
            _identifier(value["namespace"])
        field_name = "arguments" if kind == "function_call" else "input"
        _string(value.get(field_name))
        if not done:
            _require(value[field_name] == "")
        elif kind == "function_call":
            argument_object(value[field_name])
        if "async" in value:
            _require(value["async"] is None or type(value["async"]) is bool)
    elif kind == "reasoning":
        _require(isinstance(value.get("summary"), list))
        for part in value["summary"]:
            _require(_part(part)["type"] == "summary_text")
        if value.get("content") is not None:
            _require(isinstance(value["content"], list))
            for part in value["content"]:
                _require(_part(part)["type"] == "reasoning_text")
        if value.get("encrypted_content") is not None:
            _string(value["encrypted_content"])
        if not done:
            _require(value["summary"] == [] and not value.get("content"))
    elif kind == "web_search_call":
        if value.get("action") is not None:
            _web_action(value["action"])
        if done:
            _require(value.get("action") is not None)
    else:
        _require(value.get("execution") in ("client", "server"))
        if value.get("call_id") is not None:
            _identifier(value["call_id"])
        if value["execution"] == "client":
            _identifier(value.get("call_id"))
        if kind == "tool_search_call":
            _require("arguments" in value)
        else:
            _require(isinstance(value.get("tools"), list))
    return value


@dataclass
class _Text:
    part: dict[str, Any]
    fragments: list[str] = field(default_factory=list)
    logprobs: list[Any] = field(default_factory=list)
    done_logprobs: list[Any] | None = None
    text_done: bool = False
    part_done: bool = False

    @property
    def value(self) -> str:
        return "".join(self.fragments)


@dataclass
class _Item:
    initial: dict[str, Any]
    final: dict[str, Any] | None = None
    parts: dict[tuple[str, int], _Text] = field(default_factory=dict)
    fragments: list[str] = field(default_factory=list)
    string_done: bool = False
    web_phase: int = -1
    incomplete_summary: bool = False


class ResponsesStream:
    """Assemble a native response; only validated output-text deltas may drain.

    Semantic failures suppress all pending/future text, while bounded parsing
    continues to retain independently valid accounting. Hard byte/UTF-8 failures
    raise immediately. Previously drained text cannot be retracted. The caller
    must validate finish()'s native snapshot against its request and consent DTO.
    """

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._bytes = 0
        self._event_bytes = 0
        self._closed_event_bytes = 0
        self._line: list[str] = []
        self._data: list[str] = []
        self._event_name: str | None = None
        self._after_cr = False
        self._first_character = True
        self._invalid = False
        self._sequence = -1
        self._initial: dict[str, Any] | None = None
        self._in_progress = False
        self._terminal: dict[str, Any] | None = None
        self._failure: ProviderErrorReason | None = None
        self._items: list[_Item] = []
        self._ids: set[str] = set()
        self._calls: set[str] = set()
        self._pending: list[ResponsesTextDelta] = []
        self._head: ResponsesStreamHead | None = None
        self._leading_prefix_open = True
        self._usage: dict[str, int] | None = None
        self._usage_conflict = False
        self._native_usage: dict[str, object] | None = None
        self._accounting_identity: dict[str, Any] | None = None

    @property
    def usage(self) -> dict[str, int] | None:
        return None if self._usage is None else self._usage.copy()

    @property
    def native_usage(self) -> dict[str, object] | None:
        """Detach the latest validated source usage with at least one reported count.

        Null/unknown usage and malformed updates never erase a known snapshot.
        This remains available after stream or consumer failure; no missing count
        is derived or replaced with zero, and the final wire snapshot is unchanged.
        """
        return None if self._native_usage is None else _copy_native_usage(self._native_usage)

    def _invalidate(self) -> None:
        self._invalid = True
        self._pending.clear()

    def _error(self) -> ProviderError:
        self._invalidate()
        return ProviderError(ProviderErrorReason.INVALID_RESPONSE, usage=self.usage)

    def drain_text_deltas(self) -> tuple[ResponsesTextDelta, ...]:
        """Consume validated, detached text records once, with native identities.

        leading_prefix proves only the uninterrupted first assistant item/part.
        Other items/parts, held metadata, or closing that part permanently end
        that window. Later text still retains its real position for final replay.
        """
        result = () if self._invalid or self._failure is not None else tuple(self._pending)
        self._pending.clear()
        return result

    def drain_text(self) -> tuple[str, ...]:
        """Consume the same pending records as strings, without duplicate delivery."""
        return tuple(record.delta for record in self.drain_text_deltas())

    def _record_text_delta(self, kind: str, event: dict[str, Any]) -> None:
        # This runs only after the entire native event has passed state validation.
        if self._leading_prefix_open:
            if kind in ("response.created", "response.in_progress"):
                pass
            elif kind == "response.output_item.added":
                self._leading_prefix_open = (
                    event["output_index"] == 0 and event["item"]["type"] == "message"
                )
            elif kind == "response.content_part.added":
                part = event["part"]
                self._leading_prefix_open = (
                    event["output_index"] == 0
                    and event["content_index"] == 0
                    and part["type"] == "output_text"
                    and not part["annotations"]
                    and not part.get("logprobs")
                )
            elif kind == "response.output_text.delta":
                self._leading_prefix_open = (
                    event["output_index"] == 0
                    and event["content_index"] == 0
                    and not event["logprobs"]
                )
            else:
                self._leading_prefix_open = False
        if kind != "response.output_text.delta" or not event["delta"]:
            return
        if self._head is None:
            initial = _object(self._initial)
            head = {name: initial[name] for name in ("id", "created_at", "model")}
            for name in ("parallel_tool_calls", "tool_choice", "tools"):
                if name in initial:
                    value = initial[name]
                    head[name] = tuple(value) if name == "tools" and value is not None else value
            self._head = ResponsesStreamHead.model_validate(head)
        record = ResponsesTextDelta(
            head=self._head,
            sequence_number=event["sequence_number"],
            item_id=event["item_id"],
            output_index=event["output_index"],
            content_index=event["content_index"],
            phase=self._items[event["output_index"]].initial.get("phase"),
            delta=event["delta"],
            leading_prefix=self._leading_prefix_open,
        )
        self._pending.append(record)

    def feed(self, chunk: bytes) -> None:
        accepted = chunk[: MAX_RESPONSE_BYTES - self._bytes]
        self._bytes += len(accepted)
        try:
            # Complete lines preserve earlier accounting if later bytes are bad.
            for part in accepted.splitlines(keepends=True):
                self._characters(self._decoder.decode(part))
        except UnicodeError:
            raise self._error() from None
        if len(accepted) != len(chunk):
            raise self._error()

    def _characters(self, text: str) -> None:
        for character in text:
            if self._first_character:
                self._first_character = False
                if character == "\ufeff":
                    continue
            if self._after_cr:
                self._after_cr = False
                if character == "\n":
                    if (self._event_bytes or self._closed_event_bytes) + 1 > MAX_EVENT_BYTES:
                        raise self._error()
                    if self._event_bytes:
                        self._event_bytes += 1
                    continue
            self._event_bytes += len(character.encode("utf-8"))
            if self._event_bytes > MAX_EVENT_BYTES:
                raise self._error()
            if character in ("\r", "\n"):
                self._end_line()
                self._after_cr = character == "\r"
            else:
                self._line.append(character)

    def _end_line(self) -> None:
        line = "".join(self._line)
        self._line.clear()
        if not line:
            self._event()
            self._closed_event_bytes = self._event_bytes
            self._event_bytes = 0
            return
        name, separator, value = line.partition(":")
        value = value.removeprefix(" ") if separator else ""
        if name == "data":
            self._data.append(value)
        elif name == "event":
            self._event_name = value

    def _response_identity(self, value: dict[str, Any]) -> None:
        _identifier(value.get("id"))
        _require(value.get("object") == "response")
        _require(bool(_string(value.get("model"))))
        created = value.get("created_at")
        _require(type(created) in (int, float))
        _require(math.isfinite(cast(float, created)) and cast(float, created) >= 0)
        for identity in (self._initial, self._accounting_identity):
            if identity is not None:
                for name in _RESPONSE_IDENTITY_FIELDS:
                    current, initial = value.get(name), identity.get(name)
                    _require(
                        current == initial if name == "created_at" else _same(current, initial)
                    )

    def _account(self, response: Any) -> None:
        if not isinstance(response, dict) or response.get("usage") is None:
            return
        try:
            self._response_identity(response)
            value = _object(response["usage"])
            _bounded_depth(value)
            _require(
                set(value)
                <= {
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "input_tokens_details",
                    "output_tokens_details",
                }
            )
            reported: list[int] = []
            for name in ("input_tokens", "output_tokens", "total_tokens"):
                if value.get(name) is not None:
                    reported.append(_integer(value[name]))
            details = (value.get("input_tokens_details"), value.get("output_tokens_details"))
            detail_fields = ({"cached_tokens", "cache_write_tokens"}, {"reasoning_tokens"})
            for detail, allowed in zip(details, detail_fields):
                if detail is not None:
                    detail = _object(detail)
                    _require(set(detail) <= allowed)
                    for count in detail.values():
                        if count is not None:
                            reported.append(_integer(count))
            total = value.get("total_tokens")
            if total is not None:
                for name in ("input_tokens", "output_tokens"):
                    if value.get(name) is not None:
                        _require(value[name] <= total)
                for detail in details:
                    if isinstance(detail, dict):
                        for count in detail.values():
                            if count is not None:
                                _require(count <= total)
            if all(
                value.get(name) is not None
                for name in ("input_tokens", "output_tokens", "total_tokens")
            ):
                _require(value["input_tokens"] + value["output_tokens"] == value["total_tokens"])
            if isinstance(details[0], dict) and value.get("input_tokens") is not None:
                for name in ("cached_tokens", "cache_write_tokens"):
                    if details[0].get(name) is not None:
                        _require(details[0][name] <= value["input_tokens"])
            if (
                isinstance(details[1], dict)
                and value.get("output_tokens") is not None
                and details[1].get("reasoning_tokens") is not None
            ):
                _require(details[1]["reasoning_tokens"] <= value["output_tokens"])
            if reported:
                if self._accounting_identity is None:
                    self._accounting_identity = {
                        name: response[name] for name in _RESPONSE_IDENTITY_FIELDS
                    }
                self._native_usage = _copy_native_usage(value)
            if value.get("input_tokens") is None or value.get("output_tokens") is None:
                return
            usage = {"input_tokens": value["input_tokens"], "output_tokens": value["output_tokens"]}
        except (ValueError, TypeError):
            self._invalidate()
            return
        if self._usage is not None and usage != self._usage:
            self._usage_conflict = True
        self._usage = None if self._usage_conflict else usage

    def _event(self) -> None:
        name, self._event_name = self._event_name, None
        if not self._data:
            if name is not None:
                self._invalidate()
            return
        raw = "\n".join(self._data)
        self._data.clear()
        try:
            event = _object(
                json.loads(
                    raw,
                    object_pairs_hook=_unique_object,
                    parse_constant=_reject_constant,
                    parse_float=_finite_float,
                )
            )
            self._account(event.get("response"))
            if self._invalid:
                return
            _bounded_depth(event)
            kind = _string(event.get("type"))
            _require(kind in _EVENT_FIELDS)
            _require(name in (None, "", kind))
            required = _EVENT_FIELDS[kind] | {"type", "sequence_number"}
            _require(required <= set(event) <= required | _OPTIONAL_FIELDS.get(kind, set()))
            sequence = _integer(event["sequence_number"])
            _require(sequence > self._sequence and self._terminal is None and self._failure is None)
            for index in ("output_index", "content_index", "summary_index", "annotation_index"):
                if index in event:
                    _integer(event[index])
            if kind == "response.output_text.delta" and "obfuscation" in event:
                _string(event["obfuscation"])
                del event["obfuscation"]
            self._process(kind, event)
            self._record_text_delta(kind, event)
            self._sequence = sequence
        except (
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            RecursionError,
            UnicodeError,
            OverflowError,
        ):
            self._invalidate()

    def _process(self, kind: str, event: dict[str, Any]) -> None:
        if kind == "error":
            self._fail(event)
            return
        if "response" in event:
            self._response(kind, _object(event["response"]))
            return
        _require(self._initial is not None)
        index = event["output_index"]
        if kind == "response.output_item.added":
            value = _item(event["item"], done=False)
            _require(index == len(self._items) and value["id"] not in self._ids)
            if (
                value["type"] in ("function_call", "custom_tool_call", "tool_search_call")
                and value.get("call_id") is not None
            ):
                _require(value["call_id"] not in self._calls)
                self._calls.add(value["call_id"])
            self._ids.add(value["id"])
            self._items.append(_Item(value))
            return
        _require(index < len(self._items))
        item = self._items[index]
        _require(item.final is None)
        if kind == "response.output_item.done":
            self._item_done(item, _item(event["item"], done=True))
            return
        _require(event["item_id"] == item.initial["id"])
        if "call_id" in event:
            _require(event["call_id"] == item.initial.get("call_id"))
        if kind.startswith("response.web_search_call."):
            _require(item.initial["type"] == "web_search_call")
            phase = ("in_progress", "searching", "completed").index(kind.rsplit(".", 1)[1])
            _require(phase > item.web_phase)
            item.web_phase = phase
        elif "function_call_arguments" in kind or "custom_tool_call_input" in kind:
            custom = "custom_tool" in kind
            _require(item.initial["type"] == ("custom_tool_call" if custom else "function_call"))
            _require(not item.string_done)
            fragment = _string(
                event["delta" if kind.endswith(".delta") else "input" if custom else "arguments"]
            )
            if kind.endswith(".delta"):
                item.fragments.append(fragment)
            else:
                _require(fragment == "".join(item.fragments))
                if not custom:
                    argument_object(fragment)
                item.string_done = True
        else:
            self._content_event(kind, event, item)

    def _response(self, kind: str, value: dict[str, Any]) -> None:
        value = project_provider_response(value)
        _require(set(value) <= _RESPONSE_FIELDS)
        ResponsesResponseEchoes.model_validate(
            {name: value[name] for name in ResponsesResponseEchoes.model_fields if name in value}
        )
        self._response_identity(value)
        _require(isinstance(value.get("output"), list))
        _require(
            type(value.get("parallel_tool_calls")) is bool and isinstance(value.get("tools"), list)
        )
        _RESPONSE_TOOLS.validate_python(value["tools"], strict=True)
        if self._initial is None:
            _require(kind == "response.created")
            self._initial = value
        else:
            _require(kind != "response.created")
            for field_name in ("parallel_tool_calls", "tools", "tool_choice"):
                _require(_same(value.get(field_name), self._initial.get(field_name)))
        if kind in ("response.created", "response.in_progress"):
            _require(value.get("status") == "in_progress" and value["output"] == [])
            _require(value.get("error") is None and value.get("incomplete_details") is None)
            if kind == "response.in_progress":
                _require(not self._in_progress and not self._items)
                self._in_progress = True
            return
        status = kind.removeprefix("response.")
        _require(value.get("status") == status)
        if status == "failed":
            self._fail(_object(value.get("error")))
            self._terminal = value
            return
        _require(all(item.final is not None for item in self._items))
        _require(_same(value["output"], [item.final for item in self._items]))
        _require(value.get("error") is None)
        if status == "incomplete":
            details = _object(value.get("incomplete_details"))
            _require(
                set(details) == {"reason"}
                and details["reason"] in ("max_output_tokens", "content_filter", "max_messages")
            )
        else:
            _require(status == "completed" and value.get("incomplete_details") is None)
            _require(
                all(
                    item.final is not None
                    and (
                        item.initial["type"] == "web_search_call"
                        or item.final.get("status") in (None, "completed")
                    )
                    and not item.incomplete_summary
                    for item in self._items
                )
            )
        self._terminal = value

    def _fail(self, error: dict[str, Any]) -> None:
        _string(error.get("message"))
        code = error.get("code")
        if code is not None:
            code = _string(code)
        if error.get("param") is not None:
            _string(error["param"])
        self._failure = {
            "rate_limit_exceeded": ProviderErrorReason.RATE_LIMIT,
            "insufficient_quota": ProviderErrorReason.RATE_LIMIT,
            "server_error": ProviderErrorReason.UNAVAILABLE,
            "server_is_overloaded": ProviderErrorReason.UNAVAILABLE,
            "invalid_prompt": ProviderErrorReason.REJECTED,
            "context_length_exceeded": ProviderErrorReason.REJECTED,
            "bio_policy": ProviderErrorReason.REJECTED,
            "cyber_policy": ProviderErrorReason.REJECTED,
        }.get(cast(str, code), ProviderErrorReason.INVALID_RESPONSE)
        self._pending.clear()

    def _content_event(self, kind: str, event: dict[str, Any], item: _Item) -> None:
        summary = "reasoning_summary" in kind
        reasoning = "reasoning_text" in kind
        family = "summary" if summary else "reasoning" if reasoning else "content"
        _require(item.initial["type"] == ("reasoning" if summary or reasoning else "message"))
        sub = event["summary_index" if summary else "content_index"]
        key = (family, sub)
        if "_part." in kind and kind.endswith(".added"):
            part = _part(event["part"])
            _require(part["type"] in (("summary_text",) if summary else ("output_text", "refusal")))
            _require(sub == sum(k[0] == family for k in item.parts) and key not in item.parts)
            _require(part.get("text", part.get("refusal")) == "")
            item.parts[key] = _Text(deepcopy(part))
            return
        if reasoning and key not in item.parts:
            _require(sub == sum(k[0] == family for k in item.parts))
            item.parts[key] = _Text({"type": "reasoning_text", "text": ""})
        _require(key in item.parts)
        text = item.parts[key]
        _require(not text.part_done)
        if "_part." in kind:
            part = _part(event["part"])
            _require(text.text_done and part["type"] == text.part["type"])
            _require(part.get("text", part.get("refusal")) == text.value)
            if part["type"] == "output_text":
                _require(part["annotations"] == text.part["annotations"])
                _match_logprobs(text.logprobs, part.get("logprobs") or [])
                if text.done_logprobs is not None:
                    _match_logprobs(text.done_logprobs, part.get("logprobs") or [])
            if "status" in event:
                _require(event["status"] in (None, "incomplete"))
                item.incomplete_summary |= event["status"] == "incomplete"
            text.part = part
            text.part_done = True
            return
        if kind == "response.output_text.annotation.added":
            _require(text.part["type"] == "output_text")
            _annotation(event.get("annotation"))
            _require(event["annotation_index"] == len(text.part["annotations"]))
            text.part["annotations"].append(event["annotation"])
            return
        expected = (
            "summary_text"
            if summary
            else "reasoning_text"
            if reasoning
            else "refusal"
            if ".refusal." in kind
            else "output_text"
        )
        _require(text.part["type"] == expected and not text.text_done)
        value = _string(
            event[
                "delta"
                if kind.endswith(".delta")
                else "refusal"
                if expected == "refusal"
                else "text"
            ]
        )
        logprobs = _event_logprobs(event["logprobs"]) if expected == "output_text" else []
        if kind.endswith(".delta"):
            text.fragments.append(value)
            text.logprobs.extend(logprobs)
        else:
            _require(value == text.value)
            _match_logprobs(text.logprobs, logprobs)
            text.done_logprobs = logprobs
            text.text_done = True
            if reasoning:
                text.part = {"type": "reasoning_text", "text": value}
                text.part_done = True

    def _item_done(self, item: _Item, final: dict[str, Any]) -> None:
        for name in _IMMUTABLE:
            _require(_same(final.get(name), item.initial.get(name)))
        _require(all(part.part_done for part in item.parts.values()))
        kind = final["type"]
        if kind in ("function_call", "custom_tool_call"):
            field_name = "arguments" if kind == "function_call" else "input"
            _require(item.string_done and final[field_name] == "".join(item.fragments))
        elif kind in ("message", "reasoning"):
            for family, field_name in (
                (("content", "content"),)
                if kind == "message"
                else (("summary", "summary"), ("reasoning", "content"))
            ):
                parts = [part.part for key, part in sorted(item.parts.items()) if key[0] == family]
                _require((final.get(field_name) or []) == parts)
        elif kind == "web_search_call" and item.web_phase == 2:
            _require(final.get("status") == "completed")
        item.final = final

    def finish(self) -> dict[str, object]:
        """Return the unflattened native terminal snapshot, or a safe provider error."""
        try:
            self._characters(self._decoder.decode(b"", final=True))
        except UnicodeError:
            raise self._error() from None
        if self._invalid or self._line or self._data or self._event_name is not None:
            raise self._error()
        if self._failure is not None:
            raise ProviderError(self._failure, usage=self.usage)
        if self._terminal is None:
            raise self._error()
        try:
            _bounded_depth(self._terminal)
            return deepcopy(self._terminal)
        except (ValueError, RecursionError):
            raise self._error() from None
