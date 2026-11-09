"""Encode checked native Responses output, never replay provider events.

Call only after request-aware response validation, consent and response policies
have succeeded. Encoding rechecks structural/delivery invariants, not policies.
The buffered functions finish before the HTTP owner starts headers. The early
encoder accepts only structured, provider-checked leading assistant text.

Source-reported partial usage is preserved. SDK 3.37's stricter required usage
details and optional echo fields must not be satisfied with invented values.
Legacy native reasoning content type `text` is also preserved, although the SDK
accepts only `reasoning_text`; its specific text events need no forged part type.
The native failed-search shape can omit action; the SDK requires it. An absent
action remains absent rather than being replaced with an invented search.
"""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from gateway7.errors import GatewayError
from gateway7.responses_events import ResponsesStreamHead, ResponsesTextDelta
from gateway7.responses_models import (
    MAX_JSON_BYTES,
    CustomToolCallItem,
    FunctionCallItem,
    HostedToolChoice,
    OutputTextPart,
    ReasoningItem,
    RefusalPart,
    ResponseFunctionToolEchoes,
    ResponseMessageItem,
    ResponsesResponse,
    ResponsesResponseEchoes,
    ToolSearchCallItem,
    WebSearchCallItem,
    _revalidated_state,
)
from gateway7.responses_stream import MAX_EVENT_BYTES, MAX_RESPONSE_BYTES

_DELTA_CHARACTERS = 1024
_INVALID_RESPONSE = "Invalid checked Responses response"
_INVALID_EARLY = "Invalid early Responses stream"


def _canonical(response: ResponsesResponse) -> dict[str, Any]:
    if type(response) is not ResponsesResponse:
        raise ValueError(_INVALID_RESPONSE)
    # Share the DTO's serializer-free actual-state check: invalid copied values
    # must not escape through serializer warnings or forged unset-field claims.
    checked = _revalidated_state(response, ResponsesResponse)
    result = checked.wire_dict()
    result["object"] = "response"
    item_ids: set[str] = set()
    call_ids: set[str] = set()
    local_calls = 0
    if checked.status == "failed":
        # A failed upstream's generated output is not a deliverable success.
        if checked.output:
            raise ValueError(_INVALID_RESPONSE)
        result["error"] = {"code": "server_error", "message": "Provider request failed"}
    for item, encoded in zip(checked.output, result["output"], strict=True):
        if item.id is None or item.id in item_ids:
            raise ValueError(_INVALID_RESPONSE)
        item_ids.add(item.id)
        encoded["type"] = item.type
        if item.status is None:
            # A completed enclosing response commits all its items. An incomplete
            # response does not tell us which preceding items completed: refuse
            # to guess when the provider/parser omitted their individual states.
            if checked.status != "completed":
                raise ValueError(_INVALID_RESPONSE)
            encoded["status"] = "completed"
        elif item.status not in (
            ("completed", "incomplete", "failed")
            if isinstance(item, WebSearchCallItem)
            else ("completed", "incomplete")
        ) or (item.status == "incomplete" and checked.status == "completed"):
            raise ValueError(_INVALID_RESPONSE)
        if isinstance(item, (FunctionCallItem, CustomToolCallItem, ToolSearchCallItem)):
            if item.call_id is not None:
                if item.call_id in call_ids or item.call_id == item.id:
                    raise ValueError(_INVALID_RESPONSE)
                call_ids.add(item.call_id)
            executable = not isinstance(item, ToolSearchCallItem) or item.execution == "client"
            if executable:
                local_calls += 1
                if encoded["status"] != "completed":
                    raise ValueError(_INVALID_RESPONSE)
        if isinstance(item, ResponseMessageItem):
            if (
                item.role != "assistant"
                or not isinstance(item.content, list)
                or any(not isinstance(part, (OutputTextPart, RefusalPart)) for part in item.content)
            ):
                raise ValueError(_INVALID_RESPONSE)
            for part, source in zip(encoded["content"], item.content, strict=True):
                if isinstance(source, OutputTextPart):
                    part.setdefault("annotations", [])
        elif isinstance(item, ReasoningItem):
            encoded.setdefault("summary", [])
    if checked.parallel_tool_calls is False and local_calls > 1:
        raise ValueError(_INVALID_RESPONSE)
    # Serialize now as a preflight, including nonfinite numbers and lone
    # surrogates, rather than discovering an encoding failure after headers.
    _json_bytes(result)
    return result


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode(
        "ascii"
    )


def response_json(response: ResponsesResponse) -> dict[str, Any]:
    """Return a detached native object; JSON byte serialization must use ASCII escapes.

    In particular, a framework JSON serializer using ensure_ascii=False cannot
    represent a JSON-escaped lone surrogate. The HTTP owner should serialize this
    object with json.dumps(..., ensure_ascii=True, allow_nan=False).
    """
    try:
        return _canonical(response)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ValueError(_INVALID_RESPONSE) from None


class _Events:
    """One local sequence and a fully serialized body, with no transport lifetime."""

    def __init__(self, *, bounded: bool = False, prior_bytes: int = 0) -> None:
        self.sequence = 0
        self.frames: list[bytes] = []
        self._bounded = bounded
        self._bytes = prior_bytes

    def emit(self, kind: str, **fields: Any) -> None:
        event = {"type": kind, "sequence_number": self.sequence, **fields}
        frame = b"event: " + kind.encode("ascii") + b"\ndata: " + _json_bytes(event) + b"\n\n"
        if self._bounded and (
            len(frame) > MAX_EVENT_BYTES or self._bytes + len(frame) > MAX_RESPONSE_BYTES
        ):
            raise ValueError(_INVALID_RESPONSE)
        self.frames.append(frame)
        self._bytes += len(frame)
        self.sequence += 1

    def text(self, prefix: str, refs: dict[str, Any], text: str, *, field: str = "text") -> None:
        extra: dict[str, Any] = {"logprobs": []} if prefix == "response.output_text" else {}
        for offset in range(0, len(text), _DELTA_CHARACTERS):
            self.emit(
                prefix + ".delta", **refs, delta=text[offset : offset + _DELTA_CHARACTERS], **extra
            )
        self.emit(prefix + ".done", **refs, **{field: text}, **extra)


def _message(
    events: _Events, item: dict[str, Any], refs: dict[str, Any], *, start_index: int = 0
) -> None:
    for index, part in enumerate(item["content"], start=start_index):
        reference = {**refs, "content_index": index}
        field = "refusal" if part["type"] == "refusal" else "text"
        blank = {**part, field: ""}
        if field == "text":
            blank["annotations"] = []
            if part.get("logprobs"):
                blank["logprobs"] = []
        events.emit("response.content_part.added", **reference, part=blank)
        prefix = "response.refusal" if field == "refusal" else "response.output_text"
        # Annotation events belong to the same content part; the full annotations
        # also remain in its final snapshot and the canonical terminal response.
        if field == "text" and (part["annotations"] or part.get("logprobs")):
            probabilities = [
                {
                    "token": record["token"],
                    "logprob": record["logprob"],
                    "top_logprobs": [
                        {"token": top["token"], "logprob": top["logprob"]}
                        for top in record["top_logprobs"]
                    ],
                }
                for record in part.get("logprobs") or []
            ]
            if probabilities:
                # The final snapshot has no reliable per-character token boundary.
                # Emit the complete part or fail the bounded preflight; never guess.
                events.emit(
                    prefix + ".delta", **reference, delta=part["text"], logprobs=probabilities
                )
            else:
                for offset in range(0, len(part["text"]), _DELTA_CHARACTERS):
                    events.emit(
                        prefix + ".delta",
                        **reference,
                        delta=part["text"][offset : offset + _DELTA_CHARACTERS],
                        logprobs=[],
                    )
            for annotation_index, annotation in enumerate(part["annotations"]):
                events.emit(
                    "response.output_text.annotation.added",
                    **reference,
                    annotation_index=annotation_index,
                    annotation=annotation,
                )
            events.emit(prefix + ".done", **reference, text=part["text"], logprobs=probabilities)
        else:
            events.text(prefix, reference, part[field], field=field)
        events.emit("response.content_part.done", **reference, part=part)


def _reasoning(events: _Events, item: dict[str, Any], refs: dict[str, Any]) -> None:
    for index, part in enumerate(item["summary"]):
        reference = {**refs, "summary_index": index}
        events.emit("response.reasoning_summary_part.added", **reference, part={**part, "text": ""})
        events.text("response.reasoning_summary_text", reference, part["text"])
        extra = {"status": "incomplete"} if item["status"] == "incomplete" else {}
        events.emit("response.reasoning_summary_part.done", **reference, part=part, **extra)
    for index, part in enumerate(item.get("content") or []):
        reference = {**refs, "content_index": index}
        # The native legacy `text` tag is not the SDK's `reasoning_text` tag.
        # Preserve it in item snapshots; emit only the correctly indexed text
        # family instead of manufacturing a differently typed generic part.
        if part["type"] == "reasoning_text":
            events.emit("response.content_part.added", **reference, part={**part, "text": ""})
        events.text("response.reasoning_text", reference, part["text"])
        if part["type"] == "reasoning_text":
            events.emit("response.content_part.done", **reference, part=part)


def _output_item(events: _Events, item: dict[str, Any], index: int) -> None:
    refs = {"output_index": index, "item_id": item["id"]}
    added = deepcopy(item)
    added["status"] = "in_progress"
    kind = item["type"]
    if kind == "message":
        added["content"] = []
    elif kind == "reasoning":
        added["summary"] = []
        if added.get("content") is not None:
            added["content"] = []
        added.pop("encrypted_content", None)
    elif kind == "function_call":
        added["arguments"] = ""
        added.pop("encrypted_function_args", None)
    elif kind == "custom_tool_call":
        added["input"] = ""
    elif kind == "tool_search_call":
        added["arguments"] = {}
    elif kind == "tool_search_output":
        added["tools"] = []
    events.emit("response.output_item.added", output_index=index, item=added)
    if kind == "message":
        _message(events, item, refs)
    elif kind == "reasoning":
        _reasoning(events, item, refs)
    elif kind == "function_call":
        events.text("response.function_call_arguments", refs, item["arguments"], field="arguments")
    elif kind == "custom_tool_call":
        events.text("response.custom_tool_call_input", refs, item["input"], field="input")
    elif kind == "web_search_call":
        events.emit("response.web_search_call.in_progress", **refs)
        if item["status"] == "completed":
            events.emit("response.web_search_call.completed", **refs)
    events.emit("response.output_item.done", output_index=index, item=item)


def _needs_compatibility_preflight(canonical: dict[str, Any]) -> bool:
    return (
        any(name in canonical for name in ResponsesResponseEchoes.model_fields)
        or any(
            any(
                (field.alias or name) in tool
                for name, field in ResponseFunctionToolEchoes.model_fields.items()
            )
            for root in canonical.get("tools") or []
            for tool in (root["tools"] if root["type"] == "namespace" else [root])
            if tool["type"] == "function"
        )
        or any(
            "logprobs" in part
            for item in canonical.get("output", [])
            if item["type"] == "message"
            for part in item["content"]
            if part["type"] == "output_text"
        )
    )


def _stream(canonical: dict[str, Any]) -> bytes:
    events = _Events(bounded=_needs_compatibility_preflight(canonical))
    initial = deepcopy(canonical)
    initial.update(status="in_progress", output=[], usage=None, error=None, incomplete_details=None)
    initial.pop("completed_at", None)
    events.emit("response.created", response=initial)
    events.emit("response.in_progress", response=initial)
    # This is checked playback in canonical output order, not a reconstruction of
    # the provider's original fragment sizes, concurrency or generation timing.
    for index, item in enumerate(canonical["output"]):
        _output_item(events, item, index)
    events.emit("response." + canonical["status"], response=canonical)
    return b"".join(events.frames)


def response_sse(response: ResponsesResponse) -> bytes:
    """Return one complete checked SSE body, with no Chat terminal marker.

    No bytes are returned unless the entire response and all event serialization
    succeed. Incomplete executable items and failed response output are refused.
    Completed, policy-approved calls in an otherwise incomplete response retain
    their actual state; the enclosing response is never relabeled completed.
    """
    try:
        return _stream(_canonical(response))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ValueError(_INVALID_RESPONSE) from None


def _early_initial(head: ResponsesStreamHead) -> dict[str, Any] | None:
    if (
        head.parallel_tool_calls is None
        or head.tool_choice is None
        or head.tools is None
        # SDK 3.37 does not accept these native named hosted choices. Do not
        # replace them with an invented compatible choice to start headers.
        or isinstance(head.tool_choice, HostedToolChoice)
    ):
        return None
    initial = head.wire_dict()
    initial.update(
        object="response",
        status="in_progress",
        output=[],
        usage=None,
        error=None,
        incomplete_details=None,
    )
    return initial if len(_json_bytes(initial)) <= MAX_JSON_BYTES else None


class EarlyResponsesEncoder:
    """A bounded leading 0/0 assistant-text window, not an event scheduler.

    The parser owns the permanent leading-prefix proof; the provider checks the
    head against the actual post-policy request. Stage immediately before the
    corresponding text callback. There is one pending record, never a queue.
    All non-text output waits for the fully checked final response.
    """

    def __init__(self) -> None:
        self._pending: ResponsesTextDelta | None = None
        self._head: ResponsesStreamHead | None = None
        self._item_id: str | None = None
        self._phase: str | None = None
        self._prefix = ""
        self._bytes = 0
        self._sequence = 0
        self._source_sequence = -1
        self._closed = False
        self._broken = False
        self._terminal = False

    def _reject(self) -> None:
        self._pending = None
        self._closed = self._broken = True
        raise ValueError(_INVALID_EARLY) from None

    def stage_text(self, delta: ResponsesTextDelta) -> str | None:
        """Return the eligible callback string, or permanently hold back text."""
        if self._terminal or self._broken or self._pending is not None:
            self._reject()
        try:
            if type(delta) is not ResponsesTextDelta:
                raise ValueError(_INVALID_EARLY)
            checked = _revalidated_state(delta, ResponsesTextDelta)
            if checked.sequence_number <= self._source_sequence:
                raise ValueError(_INVALID_EARLY)
            self._source_sequence = checked.sequence_number
            if self._head is not None and json.dumps(
                checked.head.wire_dict(), sort_keys=True, allow_nan=False
            ) != json.dumps(self._head.wire_dict(), sort_keys=True, allow_nan=False):
                raise ValueError(_INVALID_EARLY)
            if (
                self._closed
                or not checked.leading_prefix
                or checked.output_index != 0
                or checked.content_index != 0
                or len(self._prefix) + len(checked.delta) > MAX_JSON_BYTES
                or _early_initial(checked.head) is None
            ):
                self._closed = True
                return None
            if self._head is not None and (
                checked.item_id != self._item_id or checked.phase != self._phase
            ):
                raise ValueError(_INVALID_EARLY)
            self._pending = checked
            return checked.delta
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            self._reject()
        return None

    def text(self, text: str) -> bytes:
        """Consume exactly the current staged fragment and emit no done event."""
        if (
            self._terminal
            or self._broken
            or self._pending is None
            or type(text) is not str
            or text != self._pending.delta
        ):
            self._reject()
        pending = self._pending
        assert pending is not None
        self._pending = None
        events = _Events()
        events.sequence = self._sequence
        if self._head is None:
            initial = _early_initial(pending.head)
            assert initial is not None
            events.emit("response.created", response=initial)
            events.emit("response.in_progress", response=initial)
            added: dict[str, Any] = {
                "id": pending.item_id,
                "type": "message",
                "role": "assistant",
                "status": "in_progress",
                "content": [],
            }
            if pending.phase is not None:
                added["phase"] = pending.phase
            events.emit("response.output_item.added", output_index=0, item=added)
            events.emit(
                "response.content_part.added",
                output_index=0,
                item_id=pending.item_id,
                content_index=0,
                part={"type": "output_text", "text": "", "annotations": []},
            )
        for offset in range(0, len(text), _DELTA_CHARACTERS):
            events.emit(
                "response.output_text.delta",
                output_index=0,
                item_id=pending.item_id,
                content_index=0,
                delta=text[offset : offset + _DELTA_CHARACTERS],
                logprobs=[],
            )
        body = b"".join(events.frames)
        if _needs_compatibility_preflight(pending.head.wire_dict()) and (
            any(len(frame) > MAX_EVENT_BYTES for frame in events.frames)
            or self._bytes + len(body) > MAX_RESPONSE_BYTES
        ):
            self._reject()
        self._head = pending.head
        self._item_id = pending.item_id
        self._phase = pending.phase
        self._prefix += text
        self._bytes += len(body)
        self._sequence = events.sequence
        return body

    def complete(self, response: ResponsesResponse) -> bytes:
        """Reconcile the entire final response before returning any final bytes."""
        if self._terminal or self._broken or self._pending is not None:
            self._reject()
        try:
            if self._head is None:
                body = response_sse(response)
            else:
                canonical = response_json(response)
                head = self._head.wire_dict()
                if json.dumps(
                    {key: canonical[key] for key in head}, sort_keys=True, allow_nan=False
                ) != json.dumps(head, sort_keys=True, allow_nan=False):
                    raise ValueError(_INVALID_EARLY)
                if not canonical["output"]:
                    raise ValueError(_INVALID_EARLY)
                item = canonical["output"][0]
                if (
                    item["type"] != "message"
                    or item["id"] != self._item_id
                    or item.get("phase") != self._phase
                    or not item["content"]
                    or item["content"][0]["type"] != "output_text"
                    or not item["content"][0]["text"].startswith(self._prefix)
                    or bool(item["content"][0].get("logprobs"))
                ):
                    raise ValueError(_INVALID_EARLY)
                events = _Events(
                    bounded=_needs_compatibility_preflight(canonical), prior_bytes=self._bytes
                )
                events.sequence = self._sequence
                refs = {"output_index": 0, "item_id": self._item_id, "content_index": 0}
                part = item["content"][0]
                suffix = part["text"][len(self._prefix) :]
                for offset in range(0, len(suffix), _DELTA_CHARACTERS):
                    events.emit(
                        "response.output_text.delta",
                        **refs,
                        delta=suffix[offset : offset + _DELTA_CHARACTERS],
                        logprobs=[],
                    )
                for index, annotation in enumerate(part["annotations"]):
                    events.emit(
                        "response.output_text.annotation.added",
                        **refs,
                        annotation_index=index,
                        annotation=annotation,
                    )
                events.emit("response.output_text.done", **refs, text=part["text"], logprobs=[])
                events.emit("response.content_part.done", **refs, part=part)
                _message(
                    events,
                    {**item, "content": item["content"][1:]},
                    {"output_index": 0, "item_id": self._item_id},
                    start_index=1,
                )
                events.emit("response.output_item.done", output_index=0, item=item)
                for index, remaining in enumerate(canonical["output"][1:], start=1):
                    _output_item(events, remaining, index)
                events.emit("response." + canonical["status"], response=canonical)
                body = b"".join(events.frames)
            self._terminal = True
            return body
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            self._reject()
        return b""

    def error(self, error: GatewayError) -> bytes:
        """After published text, fail safely without releasing executable output."""
        if self._terminal or self._head is None or type(error) is not GatewayError:
            self._reject()
        assert self._head is not None
        safe = GatewayError(error.code if type(error.code) is str else "internal_error")
        failed = _early_initial(self._head)
        assert failed is not None
        partial: dict[str, Any] = {
            "id": self._item_id,
            "type": "message",
            "role": "assistant",
            "status": "incomplete",
            "content": [{"type": "output_text", "text": self._prefix, "annotations": []}],
        }
        if self._phase is not None:
            partial["phase"] = self._phase
        failed.update(
            status="failed",
            error={"code": "server_error", "message": safe.message},
            output=[partial],
        )
        events = _Events()
        events.sequence = self._sequence
        events.emit("response.failed", response=failed)
        self._pending = None
        self._terminal = self._closed = True
        return b"".join(events.frames)
