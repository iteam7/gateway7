"""Bounded OpenAI Chat SSE assembly before whole-response middleware checks."""

import codecs
import json
from typing import Any, cast

from gateway7.errors import ProviderError, ProviderErrorReason

MAX_EVENT_BYTES = 65_536


def _reject_constant(_: str) -> None:
    raise ValueError("Invalid JSON number")


class OpenAIStream:
    """Consume transport fragments without exposing unvalidated partial output.

    Semantic failures remain terminal, but bounded parsing continues so a later
    independent usage event can still account for the failed provider attempt.
    Invalid UTF-8 or a size limit ends consumption immediately.
    """

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self.usage: dict[str, int] | None = None
        self._usage_seen = False
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._bytes = 0
        self._event_bytes = 0
        self._line: list[str] = []
        self._data: list[str] = []
        self._after_cr = False
        self._first_character = True
        self._invalid = False
        self._done = False
        self._identity: dict[str, Any] = {}
        self._text: list[str] = []
        self._tool: dict[str, Any] | None = None
        self._finish: str | None = None

    def _error(self) -> ProviderError:
        return ProviderError(ProviderErrorReason.INVALID_RESPONSE, usage=self.usage)

    def feed(self, chunk: bytes) -> None:
        remaining = self.max_bytes - self._bytes
        accepted = chunk[:remaining]
        self._bytes += len(accepted)
        try:
            # Decode complete lines separately: malformed bytes or excess data
            # later in the same HTTP fragment must not erase earlier usage.
            for part in accepted.splitlines(keepends=True):
                self._characters(self._decoder.decode(part))
        except UnicodeError:
            raise self._error() from None
        if len(chunk) > remaining:
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
            self._event_bytes = 0
            return
        field, separator, value = line.partition(":")
        if field == "data":
            self._data.append(value.removeprefix(" ") if separator else "")

    def _account(self, data: dict[str, Any]) -> None:
        value = data.get("usage")
        if value is None:
            return
        usage: dict[str, int] | None = None
        if isinstance(value, dict):
            counts = (value.get("prompt_tokens"), value.get("completion_tokens"))
            if all(type(count) is int and 0 <= count <= 2**63 - 1 for count in counts):
                usage = {
                    "input_tokens": cast(int, counts[0]),
                    "output_tokens": cast(int, counts[1]),
                }
        if self._usage_seen and usage != self.usage:
            # Conflicting accounting is sticky unknown; it does not invalidate
            # otherwise valid content or choose whichever total arrived last.
            self.usage = None
        elif not self._usage_seen:
            self.usage = usage
        self._usage_seen = True

    def _event(self) -> None:
        if not self._data:
            return
        raw = "\n".join(self._data)
        self._data.clear()
        if self._done:
            self._invalid = True
            return
        if raw == "[DONE]":
            self._done = True
            return
        try:
            data = json.loads(raw, parse_constant=_reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            self._invalid = True
            return
        if not isinstance(data, dict):
            self._invalid = True
            return
        self._account(data)
        if self._invalid:
            return
        try:
            self._completion_event(data)
        except (ValueError, TypeError):
            self._invalid = True

    def _completion_event(self, data: dict[str, Any]) -> None:
        if data.get("error") is not None:
            raise ValueError
        for name in ("id", "model", "created", "object"):
            if name not in data:
                continue
            value = data[name]
            if name == "created":
                if type(value) is not int or value < 0:
                    raise ValueError
            elif not isinstance(value, str) or not value:
                raise ValueError
            if name == "object" and value != "chat.completion.chunk":
                raise ValueError
            if name in self._identity and self._identity[name] != value:
                raise ValueError
            self._identity[name] = value
        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            raise ValueError
        if not choices:
            if "usage" not in data:
                raise ValueError
            return
        if self._finish is not None:
            raise ValueError
        choice = choices[0]
        if not isinstance(choice, dict) or type(choice.get("index")) is not int:
            raise ValueError
        if choice["index"] != 0 or choice.get("logprobs") is not None:
            raise ValueError
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            raise ValueError
        if any(
            name not in ("role", "content", "tool_calls") and value is not None
            for name, value in delta.items()
        ):
            raise ValueError
        if "role" in delta and delta["role"] != "assistant":
            raise ValueError
        text = delta.get("content")
        if text is not None:
            if not isinstance(text, str):
                raise ValueError
            self._text.append(text)
        tools = delta.get("tool_calls")
        if tools is not None:
            if not isinstance(tools, list) or len(tools) > 1:
                raise ValueError
            for tool in tools:
                self._tool_delta(tool)
        reason = choice.get("finish_reason")
        if reason is not None:
            if reason not in ("stop", "length", "tool_calls"):
                raise ValueError
            self._finish = reason

    def _tool_delta(self, value: Any) -> None:
        if not isinstance(value, dict) or type(value.get("index")) is not int:
            raise ValueError
        if value["index"] != 0 or set(value) - {"index", "id", "type", "function"}:
            raise ValueError
        if self._tool is None:
            self._tool = {
                "id": None,
                "type": "function",
                "function": {"name": None, "arguments": ""},
            }
        for name in ("id", "type"):
            if name not in value:
                continue
            supplied = value[name]
            if not isinstance(supplied, str) or not supplied:
                raise ValueError
            if name == "type" and supplied != "function":
                raise ValueError
            if self._tool[name] is not None and self._tool[name] != supplied:
                raise ValueError
            self._tool[name] = supplied
        function = value.get("function")
        if not isinstance(function, dict) or set(function) - {"name", "arguments"}:
            raise ValueError
        function_name = function.get("name")
        if function_name is not None:
            if not isinstance(function_name, str) or not function_name:
                raise ValueError
            if self._tool["function"]["name"] not in (None, function_name):
                raise ValueError
            self._tool["function"]["name"] = function_name
        if "arguments" in function:
            arguments = function["arguments"]
            if not isinstance(arguments, str):
                raise ValueError
            self._tool["function"]["arguments"] += arguments

    def finish(self) -> dict[str, Any]:
        try:
            self._characters(self._decoder.decode(b"", final=True))
        except UnicodeError:
            raise self._error() from None
        # An event must be dispatched by its blank line, never inferred at EOF.
        if self._invalid or not self._done or self._finish is None or self._line or self._data:
            raise self._error()
        message: dict[str, Any] = {"role": "assistant", "content": "".join(self._text)}
        if self._tool is not None:
            message["tool_calls"] = [self._tool]
        return {
            "choices": [{"message": message, "finish_reason": self._finish}],
            "usage": None
            if self.usage is None
            else {
                "prompt_tokens": self.usage["input_tokens"],
                "completion_tokens": self.usage["output_tokens"],
            },
        }
