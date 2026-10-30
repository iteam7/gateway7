"""One-attempt HTTP adapters with bounded, sanitized provider failures.

The adapters implement provider wire formats directly; plugins only see the
provider-neutral models. No provider SDK, retries, redirects or proxy discovery
can send a second copy of a request or leak the server key to another origin.
"""

from __future__ import annotations

import ipaddress
import json
import re
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

import httpx

from gateway7.errors import ProviderError, ProviderErrorReason
from gateway7.models import ChatResponse, ToolCall
from gateway7.openai_stream import OpenAIStream

if TYPE_CHECKING:
    from gateway7.config import ProviderConfig
    from gateway7.models import ChatRequest


MAX_RESPONSE_BYTES = 1_048_576
MAX_USAGE_TOKENS = 2**63 - 1
FinishReason = Literal["stop", "length", "tool_calls"]
_REAL_HOSTS = {
    "claude": "api.anthropic.com",
    "openai": "api.openai.com",
    "gemini": "generativelanguage.googleapis.com",
}


def _validated_origin(kind: str, value: str) -> str:
    """Never allow credentials, redirects, arbitrary origins or URL key fields."""
    try:
        # urlsplit strips certain control characters. Reject them before parsing.
        if (
            "?" in value
            or "#" in value
            or any(ord(character) <= 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError
        url = urlsplit(value)
        if (
            url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise ValueError
        if kind == "fake":
            if (
                url.scheme != "http"
                or url.hostname is None
                or not ipaddress.ip_address(url.hostname).is_loopback
            ):
                raise ValueError
            # Accessing port validates malformed and out-of-range values.
            if url.port == 0:
                raise ValueError
        elif kind in _REAL_HOSTS:
            if (
                url.scheme != "https"
                or url.hostname != _REAL_HOSTS[kind]
                or url.port not in (None, 443)
            ):
                raise ValueError
        else:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Invalid provider origin") from None
    return value.rstrip("/")


def validate_provider_config(config: ProviderConfig) -> None:
    """Validate without reading credentials, creating a client or using network."""
    _validated_origin(config.kind, config.base_url)
    if config.kind != "fake" and config.model == "fake":
        raise ValueError("Real provider requires an explicit model")


def _usage(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or any(
        not isinstance(name, str) or type(count) is not int or not 0 <= count <= MAX_USAGE_TOKENS
        for name, count in value.items()
    ):
        return None
    return value


def _normalized_usage(value: Any, input_name: str, output_name: str) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    return _usage({"input_tokens": value.get(input_name), "output_tokens": value.get(output_name)})


def _response_usage(kind: str, data: dict[str, Any]) -> dict[str, int] | None:
    """Read accounting independently of answer/finish validation after HTTP 200."""
    if kind == "fake":
        return _usage(data.get("usage"))
    if kind == "claude":
        return _normalized_usage(data.get("usage"), "input_tokens", "output_tokens")
    if kind == "openai":
        return _normalized_usage(data.get("usage"), "prompt_tokens", "completion_tokens")
    raw_usage = data.get("usageMetadata")
    usage = _normalized_usage(raw_usage, "promptTokenCount", "candidatesTokenCount")
    if usage is not None and isinstance(raw_usage, dict) and "thoughtsTokenCount" in raw_usage:
        thoughts = raw_usage["thoughtsTokenCount"]
        if (
            type(thoughts) is not int
            or not 0 <= thoughts <= MAX_USAGE_TOKENS - usage["output_tokens"]
        ):
            return None
        # Gemini reports reasoning separately from candidate text tokens.
        usage["output_tokens"] += thoughts
    return usage


def _claude_response(data: dict[str, Any]) -> tuple[str, FinishReason]:
    if data.get("stop_reason") not in ("end_turn", "max_tokens", "stop_sequence"):
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    content = data.get("content")
    if not isinstance(content, list) or not content:
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    text_parts = []
    for block in content:
        if not isinstance(block, dict):
            raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
        kind = block.get("type")
        if kind == "text" and isinstance(block.get("text"), str):
            text_parts.append(block["text"])
        elif kind == "thinking" and isinstance(block.get("thinking"), str):
            # Newer Claude models may think by default. Never expose reasoning
            # or its signature through the plain-text answer contract.
            continue
        elif kind == "redacted_thinking" and isinstance(block.get("data"), str):
            continue
        else:
            raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    return "".join(text_parts), "length" if data["stop_reason"] == "max_tokens" else "stop"


def _openai_response(data: dict[str, Any]) -> tuple[str, FinishReason, list[ToolCall]]:
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    choice = choices[0]
    reason = choice.get("finish_reason")
    if reason not in ("stop", "length", "tool_calls"):
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    message = choice.get("message")
    if (
        not isinstance(message, dict)
        or message.get("role") != "assistant"
        or message.get("refusal") is not None
        or message.get("function_call") is not None
        or message.get("audio") is not None
    ):
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    raw_calls = message.get("tool_calls")
    if raw_calls is None:
        raw_calls = []
    if not isinstance(raw_calls, list) or len(raw_calls) > 1:
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    try:
        calls = [ToolCall.model_validate(call, strict=True) for call in raw_calls]
    except (TypeError, ValueError):
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE) from None
    text = message.get("content")
    if text is None and calls:
        text = ""
    if not isinstance(text, str) or (not text and not calls):
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    if bool(calls) != (reason == "tool_calls"):
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    return text, reason, calls


def _gemini_response(data: dict[str, Any]) -> tuple[str, FinishReason]:
    feedback = data.get("promptFeedback")
    if feedback is not None and (not isinstance(feedback, dict) or feedback.get("blockReason")):
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    candidates = data.get("candidates")
    if (
        not isinstance(candidates, list)
        or len(candidates) != 1
        or not isinstance(candidates[0], dict)
    ):
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    candidate = candidates[0]
    if candidate.get("finishReason") not in ("STOP", "MAX_TOKENS"):
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    content = candidate.get("content")
    if not isinstance(content, dict) or content.get("role") != "model":
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
    text_parts = []
    for part in parts:
        if (
            not isinstance(part, dict)
            or not isinstance(part.get("text"), str)
            or any(
                name in part
                for name in (
                    "inlineData",
                    "fileData",
                    "functionCall",
                    "functionResponse",
                    "executableCode",
                    "codeExecutionResult",
                    "toolCall",
                    "toolResponse",
                )
            )
            or ("thought" in part and type(part["thought"]) is not bool)
        ):
            raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
        if not part.get("thought", False):
            text_parts.append(part["text"])
    return "".join(text_parts), "length" if candidate["finishReason"] == "MAX_TOKENS" else "stop"


class HTTPProvider:
    """Adapters own their HTTP session; the gateway owns its lifetime."""

    def __init__(
        self,
        config: ProviderConfig,
        key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        validate_provider_config(config)
        self._kind = config.kind
        self._origin = _validated_origin(config.kind, config.base_url)
        self._model = config.model
        if not key or not key.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValueError("Invalid provider key")
        if config.kind in ("fake", "openai"):
            self._headers = {"authorization": f"Bearer {key}"}
        elif config.kind == "claude":
            self._headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        else:
            self._headers = {"x-goog-api-key": key}
        options: dict[str, Any] = {} if transport is None else {"transport": transport}
        self._client = httpx.AsyncClient(
            timeout=config.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            **options,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _request(
        self, request: ChatRequest, model: str | None = None, *, stream: bool = False
    ) -> tuple[str, dict[str, Any]]:
        selected_model = self._model if model is None else model
        if (
            not isinstance(selected_model, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", selected_model) is None
        ):
            raise ProviderError()
        generation = {
            name: getattr(request, name)
            for name in (
                "temperature",
                "top_p",
                "frequency_penalty",
                "presence_penalty",
                "seed",
                "stop",
            )
            if getattr(request, name) is not None
        }
        has_tools = bool(request.tools) or any(
            message.role == "tool" or message.tool_calls for message in request.messages
        )
        if self._kind != "openai" and (
            stream
            or has_tools
            or generation
            or request.tool_choice is not None
            or request.parallel_tool_calls is not None
        ):
            raise ProviderError(ProviderErrorReason.REJECTED)
        if self._kind == "fake":
            return "/chat", {
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ],
                "max_tokens": request.max_tokens,
            }
        messages = []
        for core_message in request.messages:
            item: dict[str, Any] = {"role": core_message.role, "content": core_message.content}
            if core_message.tool_calls:
                item["tool_calls"] = [
                    call.model_dump(mode="json") for call in core_message.tool_calls
                ]
            if core_message.tool_call_id is not None:
                item["tool_call_id"] = core_message.tool_call_id
            messages.append(item)
        if self._kind == "openai":
            payload: dict[str, Any] = {
                "model": selected_model,
                "messages": messages,
                "max_completion_tokens": request.max_tokens,
                "stream": stream,
                "store": False,
                **generation,
            }
            if stream:
                payload["stream_options"] = {"include_usage": True}
            if request.tools:
                payload["tools"] = [
                    tool.model_dump(mode="json", exclude_none=True) for tool in request.tools
                ]
                payload["parallel_tool_calls"] = False
            if request.tool_choice is not None:
                payload["tool_choice"] = (
                    request.tool_choice
                    if isinstance(request.tool_choice, str)
                    else request.tool_choice.model_dump(mode="json")
                )
            if request.parallel_tool_calls is not None:
                payload["parallel_tool_calls"] = request.parallel_tool_calls
            return "/v1/chat/completions", payload
        system = [message["content"] for message in messages if message["role"] == "system"]
        conversation = [message for message in messages if message["role"] != "system"]
        if not conversation:
            raise ProviderError()
        if self._kind == "claude":
            payload = {
                "model": selected_model,
                "max_tokens": request.max_tokens,
                "messages": conversation,
            }
            if system:
                payload["system"] = "\n\n".join(system)
            return "/v1/messages", payload
        # Gemini calls assistant turns "model". Combine adjacent same-role
        # messages so normalized histories remain a valid conversation.
        contents: list[dict[str, Any]] = []
        for message in conversation:
            role = "model" if message["role"] == "assistant" else "user"
            part = {"text": message["content"]}
            if contents and contents[-1]["role"] == role:
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": role, "parts": [part]})
        payload = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": request.max_tokens, "candidateCount": 1},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system)}]}
        return f"/v1beta/models/{selected_model}:generateContent", payload

    async def complete(
        self, request: ChatRequest, *, model: str | None = None, stream: bool = False
    ) -> ChatResponse:
        usage = None
        streamed = OpenAIStream(MAX_RESPONSE_BYTES) if stream else None
        try:
            path, payload = self._request(request, model, stream=stream)
            # A single request: retries and redirects are intentionally absent.
            async with self._client.stream(
                "POST", self._origin + path, json=payload, headers=self._headers
            ) as response:
                if response.status_code != 200:
                    if response.status_code in (401, 403):
                        reason = ProviderErrorReason.AUTHENTICATION
                    elif response.status_code == 429:
                        reason = ProviderErrorReason.RATE_LIMIT
                    elif 500 <= response.status_code < 600:
                        reason = ProviderErrorReason.UNAVAILABLE
                    else:
                        reason = ProviderErrorReason.REJECTED
                    raise ProviderError(reason)
                if streamed is not None:
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                    if content_type.lower() != "text/event-stream":
                        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
                    async for chunk in response.aiter_bytes():
                        streamed.feed(chunk)
                    data = streamed.finish()
                else:
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(chunk) > MAX_RESPONSE_BYTES - len(body):
                            raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
                        body.extend(chunk)
                    try:
                        data = json.loads(body)
                    except (ValueError, UnicodeError, RecursionError):
                        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE) from None
                    if not isinstance(data, dict):
                        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
            usage = _response_usage(self._kind, data)
            calls: list[ToolCall] = []
            if self._kind == "fake":
                text = data.get("text")
                # The synthetic fixture contract predates finish metadata. Real
                # adapters require an explicit provider completion reason.
                finish_reason = data.get("finish_reason", "stop")
            elif self._kind == "claude":
                text, finish_reason = _claude_response(data)
            elif self._kind == "openai":
                text, finish_reason, calls = _openai_response(data)
                allowed_names = {tool.function.name for tool in request.tools}
                if calls and (
                    request.tool_choice == "none"
                    or any(call.function.name not in allowed_names for call in calls)
                ):
                    raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
                if isinstance(request.tool_choice, str):
                    if request.tool_choice == "required" and not calls:
                        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
                elif request.tool_choice is not None:
                    if not calls or calls[0].function.name != request.tool_choice.function.name:
                        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
            else:
                text, finish_reason = _gemini_response(data)
            if (
                not isinstance(text, str)
                or (not text and not calls)
                or finish_reason not in ("stop", "length", "tool_calls")
            ):
                raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
            return ChatResponse(
                text=text, usage=usage, finish_reason=finish_reason, tool_calls=calls
            )
        except ProviderError as error:
            raise ProviderError(
                error.reason, usage=streamed.usage if streamed is not None else usage
            ) from None
        except httpx.TimeoutException:
            raise ProviderError(
                ProviderErrorReason.TIMEOUT, usage=streamed.usage if streamed is not None else usage
            ) from None
        except httpx.DecodingError:
            raise ProviderError(
                ProviderErrorReason.INVALID_RESPONSE,
                usage=streamed.usage if streamed is not None else usage,
            ) from None
        except httpx.TransportError:
            raise ProviderError(
                ProviderErrorReason.TRANSPORT,
                usage=streamed.usage if streamed is not None else usage,
            ) from None
        except Exception:
            # Unexpected failures retain a bounded fallback. Never include
            # bodies, URLs, headers or raw exceptions in diagnostics.
            raise ProviderError(usage=streamed.usage if streamed is not None else usage) from None


def build_provider(
    config: ProviderConfig, key: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> HTTPProvider:
    return HTTPProvider(config, key, transport=transport)
