"""Closed native Responses models for the pinned Codex HTTP client profile.

These are independent of Chat Completions. Consent and routing authority belong
to the HTTP owner, never to middleware-editable payloads. SDK request TypedDicts
are not used for validation: they discard fields and defer iterable validation.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Iterator
import math
from typing import Annotated, Any, Literal, Self, TypeAlias, TypeVar

from pydantic import (
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    JsonValue,
    ModelWrapValidatorHandler,
    Tag,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from gateway7.config import ModelId
from gateway7.models import StrictPayload, ToolCallId, ToolName, _json_object, argument_object

# Match the existing JSON-object budget and the largest configurable HTTP body.
MAX_JSON_BYTES = 65_536
MAX_MEDIA_BYTES = 10 * 1024 * 1024
MAX_ITEMS = 4096
JSONObj = Annotated[dict[str, JsonValue], BeforeValidator(_json_object)]
NativeId = ToolCallId
ItemStatus = Literal["in_progress", "completed", "incomplete"]
Count = Annotated[int, Field(ge=0, le=2**63 - 1)]
OpaqueText = Annotated[str, Field(min_length=1, max_length=MAX_MEDIA_BYTES)]


class ResponsesModel(StrictPayload):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        hide_input_in_errors=True,
    )

    def wire_dict(self) -> dict[str, Any]:
        """Preserve omitted/null fields and raw strings without dropping known extensions."""
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)


ModelPayload = TypeVar("ModelPayload", bound=ResponsesModel)


def _invalid_state() -> None:
    # Do not serialize or format unchecked values while building diagnostics.
    raise ValidationError.from_exception_data(
        "Responses model state",
        [
            {
                "type": "value_error",
                "loc": (),
                "input": None,
                "ctx": {"error": ValueError("Invalid or unexpected Responses model state")},
            }
        ],
        hide_input=True,
    )


def _full_state(value: Any, ancestors: frozenset[int] = frozenset()) -> Any:
    """Read actual state without serializers or trusting __pydantic_fields_set__."""
    if not isinstance(value, (ResponsesModel, dict, list, tuple)):
        return value
    if id(value) in ancestors:
        _invalid_state()
    ancestors = ancestors | {id(value)}
    if isinstance(value, ResponsesModel):
        actual = vars(value)
        fields = type(value).model_fields
        claimed = value.__pydantic_fields_set__
        if (
            set(actual) - fields.keys()
            or value.__pydantic_extra__
            or type(claimed) is not set
            or claimed - actual.keys()
            or claimed - fields.keys()
        ):
            _invalid_state()
        return {
            fields[name].alias or name: _full_state(child, ancestors)
            for name, child in actual.items()
        }
    if isinstance(value, dict):
        return {key: _full_state(child, ancestors) for key, child in value.items()}
    if isinstance(value, tuple):
        return tuple(_full_state(child, ancestors) for child in value)
    return [_full_state(child, ancestors) for child in value]


def _restore_unset(original: Any, checked: Any) -> None:
    """Preserve legitimate omissions, never hide a present nondefault value."""
    if isinstance(original, ResponsesModel) and isinstance(checked, ResponsesModel):
        explicit = set(original.__pydantic_fields_set__)
        for name, field in type(checked).model_fields.items():
            if name not in vars(original):
                continue
            before = vars(original)[name]
            after = getattr(checked, name)
            if field.is_required() or before != field.get_default(call_default_factory=True):
                explicit.add(name)
            _restore_unset(before, after)
        checked.__pydantic_fields_set__ = explicit
    elif isinstance(original, (list, tuple)) and isinstance(checked, (list, tuple)):
        for before, after in zip(original, checked, strict=True):
            _restore_unset(before, after)
    elif isinstance(original, dict) and isinstance(checked, dict):
        for key in original.keys() & checked.keys():
            _restore_unset(original[key], checked[key])


def _revalidated_state(
    value: ModelPayload, expected: type[ModelPayload], *, context: Any = None
) -> ModelPayload:
    checked = expected.model_validate(_full_state(value), context=context)
    _restore_unset(value, checked)
    return checked


class ResponsesConsent(ResponsesModel):
    """HTTP-owned capabilities, passed as context={\"consent\": consent}."""

    allow_opaque: bool = False
    allow_hosted: bool = False


def _consent(info: ValidationInfo) -> ResponsesConsent:
    value = info.context.get("consent") if isinstance(info.context, dict) else None
    if value is None:
        return ResponsesConsent()
    if not isinstance(value, ResponsesConsent):
        raise ValueError("Invalid Responses consent")
    return ResponsesConsent.model_validate(value)


def _data_url(value: str, *, audio: bool = False) -> str:
    # The gateway never fetches media. Bound inline data before base64 decoding.
    media, separator, encoded = value.partition(",")
    allowed = (
        {
            "audio/wav",
            "audio/x-wav",
            "audio/mpeg",
            "audio/mp4",
            "audio/webm",
            "audio/ogg",
            "audio/flac",
        }
        if audio
        else {"image/png", "image/jpeg", "image/webp", "image/gif"}
    )
    if not separator or not media.startswith("data:") or not media.endswith(";base64"):
        raise ValueError("Media must use a bounded inline base64 data URL")
    if media[5:-7] not in allowed or len(encoded) > 4 * ((MAX_MEDIA_BYTES + 2) // 3):
        raise ValueError("Unsupported media format or size")
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Invalid base64 media") from None
    if not decoded or len(decoded) > MAX_MEDIA_BYTES:
        raise ValueError("Unsupported media size")
    return value


class InputTextPart(ResponsesModel):
    type: Literal["input_text"]
    text: str


class URLCitation(ResponsesModel):
    type: Literal["url_citation"]
    start_index: Count
    end_index: Count
    title: str
    url: str

    @model_validator(mode="after")
    def ordered_offsets(self) -> URLCitation:
        if self.end_index < self.start_index:
            raise ValueError("Invalid citation offsets")
        return self


class OutputTextPart(ResponsesModel):
    type: Literal["output_text"]
    text: str
    annotations: list[URLCitation] = Field(default_factory=list, max_length=MAX_ITEMS)


class RefusalPart(ResponsesModel):
    type: Literal["refusal"]
    refusal: str


class OutputTokenTopLogprob(ResponsesModel):
    """Complete final-snapshot facts, not the different SSE event shape."""

    token: str
    bytes: list[Annotated[int, Field(ge=0, le=255)]] = Field(max_length=MAX_JSON_BYTES)
    logprob: float = Field(allow_inf_nan=False)


class OutputTokenLogprob(OutputTokenTopLogprob):
    top_logprobs: list[OutputTokenTopLogprob] = Field(max_length=20)


class ResponseOutputTextPart(OutputTextPart):
    logprobs: list[OutputTokenLogprob] | None = Field(default=None, max_length=MAX_ITEMS)


class ResponseMessageItem(ResponsesModel):
    """Provider output only; request/history MessageItem remains unchanged."""

    type: Literal["message"] = "message"
    id: NativeId | None = None
    role: Literal["assistant"]
    content: list[Annotated[ResponseOutputTextPart | RefusalPart, Field(discriminator="type")]] = (
        Field(max_length=MAX_ITEMS)
    )
    phase: Literal["commentary", "final_answer"] | None = None
    status: ItemStatus | None = None


class InputImagePart(ResponsesModel):
    type: Literal["input_image"]
    image_url: str
    detail: Literal["auto", "low", "high", "original"] | None = None

    @field_validator("image_url")
    @classmethod
    def inline_image(cls, value: str) -> str:
        return _data_url(value)


class InputAudioPart(ResponsesModel):
    type: Literal["input_audio"]
    audio_url: str

    @field_validator("audio_url")
    @classmethod
    def inline_audio(cls, value: str) -> str:
        return _data_url(value, audio=True)


class EncryptedPart(ResponsesModel):
    type: Literal["encrypted_content"]
    encrypted_content: OpaqueText


MessagePart: TypeAlias = Annotated[
    InputTextPart | OutputTextPart | InputImagePart | InputAudioPart | RefusalPart,
    Field(discriminator="type"),
]
ResultPart: TypeAlias = Annotated[
    InputTextPart | InputImagePart | InputAudioPart | EncryptedPart,
    Field(discriminator="type"),
]
ResultContent: TypeAlias = str | Annotated[list[ResultPart], Field(max_length=MAX_ITEMS)]


class MessageItem(ResponsesModel):
    type: Literal["message"] = "message"
    id: NativeId | None = None
    role: Literal["system", "developer", "user", "assistant"]
    content: str | Annotated[list[MessagePart], Field(max_length=MAX_ITEMS)]
    phase: Literal["commentary", "final_answer"] | None = None
    status: ItemStatus | None = None

    @model_validator(mode="after")
    def assistant_fields(self) -> MessageItem:
        if self.role != "assistant" and (
            self.phase is not None
            or isinstance(self.content, list)
            and any(isinstance(part, (OutputTextPart, RefusalPart)) for part in self.content)
        ):
            raise ValueError("Assistant content requires the assistant role")
        return self


class SummaryPart(ResponsesModel):
    type: Literal["summary_text"]
    text: str


class ReasoningPart(ResponsesModel):
    type: Literal["reasoning_text", "text"]
    text: str


class ReasoningItem(ResponsesModel):
    type: Literal["reasoning"]
    id: NativeId | None = None
    summary: list[SummaryPart] = Field(default_factory=list, max_length=MAX_ITEMS)
    content: list[ReasoningPart] | None = Field(default=None, max_length=MAX_ITEMS)
    encrypted_content: OpaqueText | None = None
    status: ItemStatus | None = None


class FunctionTool(ResponsesModel):
    type: Literal["function"]
    name: ToolName
    description: str | None = Field(default=None, max_length=16_384)
    parameters: JSONObj
    strict: bool | None = None
    defer_loading: bool | None = None


class ResponseFunctionToolEchoes(ResponsesModel):
    """Response-only administrative absence, never invocation capabilities."""

    allowed_callers: None = None
    async_: None = Field(default=None, alias="async")
    output_schema: None = None


class ResponseFunctionTool(FunctionTool, ResponseFunctionToolEchoes):
    @model_validator(mode="wrap")
    @classmethod
    def legacy_tool_state(cls, value: Any, handler: ModelWrapValidatorHandler[Self]) -> Self:
        if type(value) is FunctionTool:
            checked = handler(_full_state(value))
            _restore_unset(value, checked)
            return checked
        return handler(value)


class TextToolFormat(ResponsesModel):
    type: Literal["text"]


class GrammarToolFormat(ResponsesModel):
    type: Literal["grammar"]
    syntax: Literal["lark", "regex"]
    definition: str = Field(min_length=1, max_length=MAX_JSON_BYTES)


class CustomTool(ResponsesModel):
    type: Literal["custom"]
    name: ToolName
    description: str | None = Field(default=None, max_length=16_384)
    format: Annotated[TextToolFormat | GrammarToolFormat, Field(discriminator="type")] | None = None
    defer_loading: bool | None = None


LocalTool: TypeAlias = Annotated[FunctionTool | CustomTool, Field(discriminator="type")]


class NamespaceTool(ResponsesModel):
    type: Literal["namespace"]
    name: NativeId
    description: str = Field(max_length=16_384)
    tools: list[LocalTool] = Field(min_length=1, max_length=128)


ResponseLocalTool: TypeAlias = Annotated[
    ResponseFunctionTool | CustomTool, Field(discriminator="type")
]


class ResponseNamespaceTool(ResponsesModel):
    type: Literal["namespace"]
    name: NativeId
    description: str = Field(max_length=16_384)
    tools: list[ResponseLocalTool] = Field(min_length=1, max_length=128)

    @model_validator(mode="wrap")
    @classmethod
    def legacy_namespace_state(cls, value: Any, handler: ModelWrapValidatorHandler[Self]) -> Self:
        if type(value) is NamespaceTool:
            checked = handler(_full_state(value))
            _restore_unset(value, checked)
            return checked
        return handler(value)


LoadableTool: TypeAlias = Annotated[
    FunctionTool | CustomTool | NamespaceTool, Field(discriminator="type")
]


class ToolSearchTool(ResponsesModel):
    type: Literal["tool_search"]
    execution: Literal["client", "server"]
    description: str | None = Field(default=None, max_length=16_384)
    parameters: JSONObj | None = None


class WebSearchFilters(ResponsesModel):
    allowed_domains: list[str] | None = Field(default=None, max_length=128)


class WebSearchLocation(ResponsesModel):
    type: Literal["approximate"]
    country: str | None = None
    region: str | None = None
    city: str | None = None
    timezone: str | None = None


class WebSearchTool(ResponsesModel):
    type: Literal["web_search"]
    external_web_access: bool | None = None
    indexed_web_access: bool | None = None
    filters: WebSearchFilters | None = None
    user_location: WebSearchLocation | None = None
    search_context_size: Literal["low", "medium", "high"] | None = None
    search_content_types: list[Literal["text", "image"]] | None = None


ResponsesTool: TypeAlias = Annotated[
    FunctionTool | CustomTool | NamespaceTool | ToolSearchTool | WebSearchTool,
    Field(discriminator="type"),
]


ResponseTool: TypeAlias = Annotated[
    ResponseFunctionTool | CustomTool | ResponseNamespaceTool | ToolSearchTool | WebSearchTool,
    Field(discriminator="type"),
]


class FunctionCallItem(ResponsesModel):
    type: Literal["function_call"]
    id: NativeId | None = None
    call_id: NativeId
    name: ToolName
    namespace: NativeId | None = None
    arguments: str = Field(max_length=MAX_JSON_BYTES)
    encrypted_function_args: list[OpaqueText] | None = Field(default=None, max_length=128)
    status: ItemStatus | None = None

    @field_validator("arguments")
    @classmethod
    def executable_json(cls, value: str) -> str:
        argument_object(value)
        return value


class CustomToolCallItem(ResponsesModel):
    type: Literal["custom_tool_call"]
    id: NativeId | None = None
    call_id: NativeId
    name: ToolName
    namespace: NativeId | None = None
    input: str = Field(max_length=MAX_JSON_BYTES)
    status: ItemStatus | None = None


class FunctionCallOutputItem(ResponsesModel):
    type: Literal["function_call_output"]
    id: NativeId | None = None
    call_id: NativeId
    name: ToolName | None = None
    namespace: NativeId | None = None
    output: ResultContent
    status: ItemStatus | None = None


class CustomToolCallOutputItem(ResponsesModel):
    type: Literal["custom_tool_call_output"]
    id: NativeId | None = None
    call_id: NativeId
    name: ToolName | None = None
    output: ResultContent
    status: ItemStatus | None = None


class ToolSearchCallItem(ResponsesModel):
    type: Literal["tool_search_call"]
    id: NativeId | None = None
    call_id: NativeId | None = None
    execution: Literal["client", "server"]
    status: ItemStatus | None = None
    arguments: JSONObj

    @model_validator(mode="after")
    def client_identity(self) -> ToolSearchCallItem:
        if self.execution == "client" and self.call_id is None:
            raise ValueError("Client tool search requires a call ID")
        return self


class ToolSearchOutputItem(ResponsesModel):
    type: Literal["tool_search_output"]
    id: NativeId | None = None
    call_id: NativeId | None = None
    execution: Literal["client", "server"]
    status: Literal["completed"]
    tools: list[LoadableTool] = Field(max_length=128)

    @model_validator(mode="after")
    def client_identity(self) -> ToolSearchOutputItem:
        if self.execution == "client" and self.call_id is None:
            raise ValueError("Client tool search result requires a call ID")
        _tool_catalog(self.tools)
        return self


class WebSource(ResponsesModel):
    type: Literal["url"]
    url: str


class WebSearchAction(ResponsesModel):
    type: Literal["search"]
    query: str | None = None
    queries: list[str] | None = None
    sources: list[WebSource] | None = None


class WebOpenAction(ResponsesModel):
    type: Literal["open_page"]
    url: str | None = None


class WebFindAction(ResponsesModel):
    type: Literal["find_in_page"]
    url: str
    pattern: str


class WebSearchCallItem(ResponsesModel):
    type: Literal["web_search_call"]
    id: NativeId | None = None
    status: Literal["in_progress", "searching", "completed", "failed", "incomplete"] | None = None
    action: (
        Annotated[WebSearchAction | WebOpenAction | WebFindAction, Field(discriminator="type")]
        | None
    ) = None


def _item_kind(value: Any) -> str | None:
    return value.get("type", "message") if isinstance(value, dict) else getattr(value, "type", None)


ResponsesInputItem: TypeAlias = Annotated[
    Annotated[MessageItem, Tag("message")]
    | Annotated[ReasoningItem, Tag("reasoning")]
    | Annotated[FunctionCallItem, Tag("function_call")]
    | Annotated[CustomToolCallItem, Tag("custom_tool_call")]
    | Annotated[FunctionCallOutputItem, Tag("function_call_output")]
    | Annotated[CustomToolCallOutputItem, Tag("custom_tool_call_output")]
    | Annotated[ToolSearchCallItem, Tag("tool_search_call")]
    | Annotated[ToolSearchOutputItem, Tag("tool_search_output")]
    | Annotated[WebSearchCallItem, Tag("web_search_call")],
    Discriminator(_item_kind),
]
ResponsesOutputItem: TypeAlias = Annotated[
    ResponseMessageItem
    | ReasoningItem
    | FunctionCallItem
    | CustomToolCallItem
    | ToolSearchCallItem
    | ToolSearchOutputItem
    | WebSearchCallItem,
    Field(discriminator="type"),
]


class ReasoningControls(ResponsesModel):
    effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None = None
    summary: Literal["auto", "concise", "detailed", "none"] | None = None
    context: Literal["auto", "current_turn", "all_turns"] | None = None


class TextFormat(ResponsesModel):
    type: Literal["text"]


class JSONSchemaFormat(ResponsesModel):
    type: Literal["json_schema"]
    name: ToolName
    strict: bool
    schema_: JSONObj = Field(alias="schema")


class TextControls(ResponsesModel):
    verbosity: Literal["low", "medium", "high"] | None = None
    format: Annotated[TextFormat | JSONSchemaFormat, Field(discriminator="type")] | None = None


class ResponsesStreamOptions(ResponsesModel):
    reasoning_summary_delivery: Literal["sequential_cutoff"] | None = None
    include_obfuscation: bool | None = None


class NamedToolChoice(ResponsesModel):
    type: Literal["function", "custom"]
    name: ToolName
    namespace: NativeId | None = None


class HostedToolChoice(ResponsesModel):
    type: Literal["web_search", "tool_search"]


ToolChoice: TypeAlias = Literal["auto", "none", "required"] | NamedToolChoice | HostedToolChoice
ToolIdentity: TypeAlias = tuple[str | None, str]


def _tool_catalog(tools: list[Any]) -> dict[ToolIdentity, FunctionTool | CustomTool]:
    catalog: dict[ToolIdentity, FunctionTool | CustomTool] = {}
    namespaces: set[str] = set()
    builtins: set[str] = set()
    for definition in tools:
        entries: list[tuple[str | None, FunctionTool | CustomTool]]
        if isinstance(definition, NamespaceTool):
            if definition.name in namespaces:
                raise ValueError("Duplicate namespace definition")
            namespaces.add(definition.name)
            entries = [(definition.name, child) for child in definition.tools]
        elif isinstance(definition, (FunctionTool, CustomTool)):
            entries = [(None, definition)]
        else:
            if definition.type in builtins:
                raise ValueError("Duplicate built-in tool definition")
            builtins.add(definition.type)
            entries = []
        for namespace, tool in entries:
            key = (namespace, tool.name)
            if key in catalog:
                raise ValueError("Duplicate function/custom tool identity")
            catalog[key] = tool
    return catalog


def _walk(value: Any) -> Iterator[ResponsesModel]:
    if isinstance(value, ResponsesModel):
        if set(vars(value)) - type(value).model_fields.keys():
            raise ValueError("Unexpected Responses model fields")
        yield value
        for name in type(value).model_fields:
            yield from _walk(getattr(value, name))
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _check_consent(value: Any, consent: ResponsesConsent) -> None:
    for item in _walk(value):
        opaque = isinstance(item, (InputImagePart, InputAudioPart, EncryptedPart))
        opaque |= isinstance(item, ReasoningItem) and item.encrypted_content is not None
        opaque |= isinstance(item, FunctionCallItem) and bool(item.encrypted_function_args)
        if opaque and not consent.allow_opaque:
            raise ValueError("Opaque content requires explicit consent")
        if (
            isinstance(item, (WebSearchTool, WebSearchCallItem))
            or isinstance(item, (ToolSearchTool, ToolSearchCallItem, ToolSearchOutputItem))
            and item.execution == "server"
        ) and not consent.allow_hosted:
            raise ValueError("Hosted tools require explicit consent")


def _history(items: list[ResponsesInputItem]) -> dict[ToolIdentity, FunctionTool | CustomTool]:
    pending: dict[str, FunctionCallItem | CustomToolCallItem | ToolSearchCallItem] = {}
    seen: set[str] = set()
    item_ids: set[str] = set()
    loaded: dict[ToolIdentity, FunctionTool | CustomTool] = {}
    server_searches = 0
    for item in items:
        if item.id is not None:
            if item.id in item_ids:
                raise ValueError("Duplicate history item ID")
            item_ids.add(item.id)
        if isinstance(item, (FunctionCallItem, CustomToolCallItem, ToolSearchCallItem)):
            if item.status not in (None, "completed"):
                raise ValueError("History calls must be complete")
            if item.call_id is None:
                server_searches += 1
                continue
            if item.call_id in seen:
                raise ValueError("Duplicate history call ID")
            seen.add(item.call_id)
            pending[item.call_id] = item
        elif isinstance(
            item, (FunctionCallOutputItem, CustomToolCallOutputItem, ToolSearchOutputItem)
        ):
            if item.status not in (None, "completed"):
                raise ValueError("History results must be complete")
            if item.call_id is None:
                if (
                    not isinstance(item, ToolSearchOutputItem)
                    or item.execution != "server"
                    or server_searches != 1
                ):
                    raise ValueError("Uncorrelated tool search result")
                server_searches -= 1
            else:
                call = pending.pop(item.call_id, None)
                result_kinds = {
                    "function_call": "function_call_output",
                    "custom_tool_call": "custom_tool_call_output",
                    "tool_search_call": "tool_search_output",
                }
                if call is None or item.type != result_kinds[call.type]:
                    raise ValueError("Tool result must match a preceding call of the same kind")
                if isinstance(item, ToolSearchOutputItem):
                    if not isinstance(call, ToolSearchCallItem) or item.execution != call.execution:
                        raise ValueError("Tool search execution mode changed")
                elif isinstance(call, (FunctionCallItem, CustomToolCallItem)):
                    if item.name is not None and item.name != call.name:
                        raise ValueError("Tool result name changed")
                    if (
                        isinstance(item, FunctionCallOutputItem)
                        and item.namespace is not None
                        and item.namespace != call.namespace
                    ):
                        raise ValueError("Tool result namespace changed")
            if isinstance(item, ToolSearchOutputItem):
                loaded.update(_tool_catalog(item.tools))
    if pending or server_searches:
        raise ValueError("History is missing a tool result")
    return loaded


class ResponsesRequest(ResponsesModel):
    """Native middleware payload. No model, stream, headers or consent authority."""

    input: str | Annotated[list[ResponsesInputItem], Field(max_length=MAX_ITEMS)]
    instructions: str | None = None
    max_output_tokens: int = Field(default=1024, ge=1, le=4096)
    tools: list[ResponsesTool] = Field(default_factory=list, max_length=128)
    tool_choice: ToolChoice = "auto"
    parallel_tool_calls: bool = True
    reasoning: ReasoningControls | None = None
    text: TextControls | None = None
    include: list[
        Literal[
            "reasoning.encrypted_content",
            "web_search_call.action.sources",
            "message.input_image.image_url",
        ]
    ] = Field(default_factory=list, max_length=16)
    prompt_cache_key: str | None = None
    # Codex's 16/64/128 metadata bounds apply to extra config, not its core values.
    # The existing HTTP body limit bounds this string map, including core JSON strings.
    client_metadata: dict[str, str] | None = None
    service_tier: (
        Literal["auto", "default", "flex", "priority", "fast", "scale", "ultrafast"] | None
    ) = None
    stream_options: ResponsesStreamOptions | None = None
    store: bool = False

    @field_validator("store")
    @classmethod
    def no_storage(cls, value: bool) -> bool:
        if value:
            raise ValueError("Responses storage must be disabled")
        return value

    @model_validator(mode="after")
    def native_contract(self, info: ValidationInfo) -> ResponsesRequest:
        consent = _consent(info)
        _check_consent(self, consent)
        if "reasoning.encrypted_content" in self.include and not consent.allow_opaque:
            raise ValueError("Encrypted reasoning include requires explicit consent")
        if len(set(self.include)) != len(self.include):
            raise ValueError("Duplicate include control")
        catalog = _history(self.input) if isinstance(self.input, list) else {}
        catalog.update(_tool_catalog(self.tools))
        if isinstance(self.tool_choice, NamedToolChoice):
            definition = catalog.get((self.tool_choice.namespace, self.tool_choice.name))
            if definition is None or definition.type != self.tool_choice.type:
                raise ValueError("Named choice must identify an advertised tool")
        elif isinstance(self.tool_choice, HostedToolChoice):
            if not any(tool.type == self.tool_choice.type for tool in self.tools):
                raise ValueError("Named built-in choice must identify an advertised tool")
        elif self.tool_choice == "required" and not (self.tools or catalog):
            raise ValueError("Required tool choice needs advertised tools")
        return self

    def wire_dict(self) -> dict[str, Any]:
        values = super().wire_dict()
        values["max_output_tokens"] = self.max_output_tokens
        values["store"] = False
        return values


class ResponsesCreateRequest(ResponsesRequest):
    """HTTP DTO; the application pins model and stream outside the core payload."""

    model: ModelId
    stream: bool = False

    def core_request(self, *, consent: ResponsesConsent = ResponsesConsent()) -> ResponsesRequest:
        checked = _revalidated_state(self, ResponsesCreateRequest, context={"consent": consent})
        values = checked.wire_dict()
        values.pop("model")
        values.pop("stream", None)
        return ResponsesRequest.model_validate(values, context={"consent": consent})


class InputTokensDetails(ResponsesModel):
    cached_tokens: Count | None = None
    cache_write_tokens: Count | None = None


class OutputTokensDetails(ResponsesModel):
    reasoning_tokens: Count | None = None


class ResponsesUsage(ResponsesModel):
    """Only source-reported counts; missing details remain missing, not zero."""

    input_tokens: Count | None = None
    output_tokens: Count | None = None
    total_tokens: Count | None = None
    input_tokens_details: InputTokensDetails | None = None
    output_tokens_details: OutputTokensDetails | None = None

    @model_validator(mode="after")
    def truthful_counts(self) -> ResponsesUsage:
        if (
            self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens is not None
        ):
            if self.total_tokens != self.input_tokens + self.output_tokens:
                raise ValueError("Reported total usage is inconsistent")
        if self.input_tokens is not None and self.input_tokens_details is not None:
            for count in (
                self.input_tokens_details.cached_tokens,
                self.input_tokens_details.cache_write_tokens,
            ):
                if count is not None and count > self.input_tokens:
                    raise ValueError("Input usage detail exceeds its aggregate")
        if self.output_tokens is not None and self.output_tokens_details is not None:
            count = self.output_tokens_details.reasoning_tokens
            if count is not None and count > self.output_tokens:
                raise ValueError("Reasoning usage exceeds its aggregate")
        return self


class IncompleteDetails(ResponsesModel):
    reason: Literal["max_output_tokens", "content_filter", "max_messages"]


class ResponsesError(ResponsesModel):
    code: str = Field(min_length=1, max_length=128)
    message: str
    param: str | None = None
    type: str | None = None


class ResponsesResponseEchoes(ResponsesModel):
    """Closed provider-response metadata, never request authority."""

    max_tool_calls: Count | None = None
    prompt_cache_retention: Literal["in_memory", "24h"] | None = None
    safety_identifier: str | None = None
    top_logprobs: Annotated[int, Field(ge=0, le=20)] | None = None
    user: str | None = None

    @field_validator("safety_identifier")
    @classmethod
    def bounded_safety_identifier(cls, value: str | None) -> str | None:
        if value is not None and len(value) > 128:
            raise ValueError("Safety identifier exceeds its native bound")
        return value


class ResponsesResponse(ResponsesResponseEchoes):
    """A terminal native response, not an unvalidated dictionary of upstream fields."""

    id: NativeId
    object: Literal["response"] = "response"
    created_at: float = Field(ge=0, allow_inf_nan=False)
    model: ModelId
    status: Literal["completed", "incomplete", "failed"]
    output: list[ResponsesOutputItem] = Field(max_length=MAX_ITEMS)
    usage: ResponsesUsage | None = None
    error: ResponsesError | None = None
    incomplete_details: IncompleteDetails | None = None
    completed_at: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    # Typed echo fields returned by the native HTTP endpoint. They cannot grant tools.
    parallel_tool_calls: bool | None = None
    tool_choice: ToolChoice | None = None
    tools: list[ResponseTool] | None = Field(default=None, max_length=128)
    instructions: str | None = None
    reasoning: ReasoningControls | None = None
    text: TextControls | None = None
    max_output_tokens: int | None = Field(default=None, ge=1, le=4096)
    prompt_cache_key: str | None = None
    service_tier: (
        Literal["auto", "default", "flex", "priority", "fast", "scale", "ultrafast"] | None
    ) = None
    store: bool | None = None
    metadata: dict[str, str] | None = None
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    top_p: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    truncation: Literal["auto", "disabled"] | None = None
    background: bool | None = None
    previous_response_id: None = None

    @field_validator("usage")
    @classmethod
    def unknown_usage(cls, value: ResponsesUsage | None) -> ResponsesUsage | None:
        if value is None:
            return None
        counts = [value.input_tokens, value.output_tokens, value.total_tokens]
        if value.input_tokens_details is not None:
            counts.extend(
                [
                    value.input_tokens_details.cached_tokens,
                    value.input_tokens_details.cache_write_tokens,
                ]
            )
        if value.output_tokens_details is not None:
            counts.append(value.output_tokens_details.reasoning_tokens)
        return value if any(count is not None for count in counts) else None

    @field_validator("store", "background")
    @classmethod
    def disabled_state(cls, value: bool | None) -> bool | None:
        if value:
            raise ValueError("Stateful Responses behavior is unsupported")
        return value

    @model_validator(mode="after")
    def terminal_state(self) -> ResponsesResponse:
        if self.status == "incomplete" and self.incomplete_details is None:
            raise ValueError("Incomplete response requires a reason")
        if self.status != "incomplete" and self.incomplete_details is not None:
            raise ValueError("Only incomplete responses carry incomplete details")
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("Only failed responses carry an error")
        if self.completed_at is not None and self.status != "completed":
            raise ValueError("Only completed responses carry a completion time")
        return self

    def wire_dict(self) -> dict[str, Any]:
        values = super().wire_dict()
        values["usage"] = None if self.usage is None else self.usage.wire_dict()
        return values

    def accounting_usage(self) -> dict[str, int] | None:
        """Return each reported input/output count, without deriving absent counts.

        Total-only or detail-only usage remains available in the native usage
        object, but cannot be converted into per-direction accounting.
        """
        if self.usage is None:
            return None
        usage = _revalidated_state(self.usage, ResponsesUsage)
        counts = {
            name: count
            for name in ("input_tokens", "output_tokens")
            if (count := getattr(usage, name)) is not None
        }
        return counts or None

    @property
    def output_text(self) -> str:
        return "".join(
            part.text
            for item in self.output
            if isinstance(item, ResponseMessageItem)
            for part in item.content
            if isinstance(part, OutputTextPart)
        )


def project_provider_response(value: dict[str, Any]) -> dict[str, Any]:
    """Project a strictly decoded provider response, never a DTO or an SSE event.

    Callers enforce original byte limits and duplicate-key rejection first. Check
    the entire decoded tree before discarding administrative root/config echoes;
    retained semantic trees still require the existing canonical validators.
    """
    if type(value) is not dict:
        raise ValueError("Invalid raw provider response")
    pending: list[tuple[Any, int]] = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise ValueError("Invalid raw provider response")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("Invalid raw provider response")
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) not in (str, int, float, bool, type(None)) or (
            type(item) is float and not math.isfinite(item)
        ):
            raise ValueError("Invalid raw provider response")
    if {"headers", "usage_metadata", "end_turn"} & value.keys():
        raise ValueError("Unsupported semantic provider response extension")
    projected = {
        name: child for name, child in value.items() if name in ResponsesResponse.model_fields
    }
    if "reasoning" in projected and projected["reasoning"] is not None:
        reasoning = projected["reasoning"]
        if type(reasoning) is not dict:
            raise ValueError("Invalid raw provider response")
        reasoning = {
            name: child
            for name, child in reasoning.items()
            if name in ReasoningControls.model_fields
        }
        ReasoningControls.model_validate(reasoning)
        projected["reasoning"] = reasoning
    return projected


def validate_request(
    request: ResponsesRequest, *, consent: ResponsesConsent = ResponsesConsent()
) -> ResponsesRequest:
    """Revalidate middleware edits, including copied extras and mutable children."""
    if type(request) is not ResponsesRequest:
        raise ValueError("Expected a core Responses request without transport authority")
    return _revalidated_state(request, ResponsesRequest, context={"consent": consent})


def validate_response(
    request: ResponsesRequest,
    response: ResponsesResponse,
    *,
    consent: ResponsesConsent = ResponsesConsent(),
) -> ResponsesResponse:
    """Check terminal provider output against the request, never echoed authority."""
    request = validate_request(request, consent=consent)
    if type(response) is not ResponsesResponse:
        raise ValueError("Expected a native Responses response")
    response = _revalidated_state(response, ResponsesResponse)
    _check_consent(response, consent)
    history = request.input if isinstance(request.input, list) else []
    catalog = _history(history)
    catalog.update(_tool_catalog(request.tools))
    old_ids = {item.id for item in history if item.id is not None}
    old_calls = {
        item.call_id
        for item in history
        if isinstance(item, (FunctionCallItem, CustomToolCallItem, ToolSearchCallItem))
        and item.call_id is not None
    }
    item_ids: set[str] = set()
    calls: set[str] = set()
    server_searches: dict[str | None, ToolSearchCallItem] = {}
    invoked = 0
    local_calls = 0
    for item in response.output:
        if item.id is None or item.id in old_ids or item.id in item_ids:
            raise ValueError("Output item IDs must be present, unique and unused in history")
        item_ids.add(item.id)
        terminal_statuses = (
            (None, "completed", "incomplete", "failed")
            if isinstance(item, WebSearchCallItem)
            else (None, "completed", "incomplete")
        )
        if item.status not in terminal_statuses:
            raise ValueError("Terminal output contains an unfinished item")
        if response.status == "completed" and item.status == "incomplete":
            raise ValueError("Completed response contains an incomplete item")
        if isinstance(item, ResponseMessageItem):
            if (
                item.role != "assistant"
                or not isinstance(item.content, list)
                or any(not isinstance(part, (OutputTextPart, RefusalPart)) for part in item.content)
            ):
                raise ValueError("Output messages must contain assistant output parts")
        if isinstance(item, (FunctionCallItem, CustomToolCallItem, ToolSearchCallItem)):
            executable = not isinstance(item, ToolSearchCallItem) or item.execution == "client"
            if executable:
                if item.status == "incomplete":
                    raise ValueError("An incomplete executable call cannot be delivered")
                local_calls += 1
            if item.call_id is not None:
                if item.call_id in old_calls or item.call_id in calls:
                    raise ValueError("Output call IDs must be unique and unused in history")
                calls.add(item.call_id)
            invoked += 1
        if isinstance(item, (FunctionCallItem, CustomToolCallItem)):
            definition = catalog.get((item.namespace, item.name))
            expected = "function" if isinstance(item, FunctionCallItem) else "custom"
            if definition is None or definition.type != expected:
                raise ValueError("Output call must identify an advertised namespace/name/kind")
            if isinstance(request.tool_choice, HostedToolChoice):
                raise ValueError("Output call differs from the named built-in choice")
            if isinstance(request.tool_choice, NamedToolChoice) and (
                (item.namespace, item.name, expected)
                != (
                    request.tool_choice.namespace,
                    request.tool_choice.name,
                    request.tool_choice.type,
                )
            ):
                raise ValueError("Output call differs from the named tool choice")
        elif isinstance(item, ToolSearchCallItem):
            if isinstance(request.tool_choice, NamedToolChoice) or (
                isinstance(request.tool_choice, HostedToolChoice)
                and request.tool_choice.type != "tool_search"
            ):
                raise ValueError("Output tool search differs from the named choice")
            if not any(
                isinstance(tool, ToolSearchTool) and tool.execution == item.execution
                for tool in request.tools
            ):
                raise ValueError("Output tool search was not advertised in this execution mode")
            if item.execution == "server" and (
                item.status == "completed"
                or (item.status is None and response.status == "completed")
            ):
                if item.call_id in server_searches:
                    raise ValueError("Ambiguous server tool search identity")
                server_searches[item.call_id] = item
        elif isinstance(item, ToolSearchOutputItem):
            if item.execution != "server" or item.call_id not in server_searches:
                raise ValueError("Provider search output must follow its server-executed call")
            server_searches.pop(item.call_id)
            catalog.update(_tool_catalog(item.tools))
        elif isinstance(item, WebSearchCallItem):
            if isinstance(request.tool_choice, NamedToolChoice) or (
                isinstance(request.tool_choice, HostedToolChoice)
                and request.tool_choice.type != "web_search"
            ):
                raise ValueError("Output web search differs from the named choice")
            if not any(isinstance(tool, WebSearchTool) for tool in request.tools):
                raise ValueError("Output web search was not advertised")
            invoked += 1
    if server_searches:
        raise ValueError("Server tool search omitted its typed result")
    if invoked and request.tool_choice == "none":
        raise ValueError("Tools were disabled")
    if local_calls > 1 and not request.parallel_tool_calls:
        raise ValueError("Parallel tool calls were disabled")
    if (
        not invoked
        and response.status == "completed"
        and (
            request.tool_choice == "required"
            or isinstance(request.tool_choice, (NamedToolChoice, HostedToolChoice))
        )
    ):
        raise ValueError("Provider omitted a required tool call")
    return response
