"""One-attempt, text-only HTTP adapters with bounded, sanitized failures."""

from __future__ import annotations

import ipaddress
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx

from gateway7.errors import ProviderError
from gateway7.models import ChatResponse

if TYPE_CHECKING:
    from gateway7.config import ProviderConfig
    from gateway7.models import ChatRequest


MAX_RESPONSE_BYTES = 1_048_576


def _validated_origin(kind: str, value: str) -> str:
    """Never allow credentials, redirects, arbitrary origins or URL key fields."""
    try:
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
            if url.scheme != "http" or not ipaddress.ip_address(url.hostname).is_loopback:
                raise ValueError
            # Accessing port validates malformed and out-of-range values.
            if url.port == 0:
                raise ValueError
        elif kind == "claude":
            if (
                url.scheme != "https"
                or url.hostname != "api.anthropic.com"
                or url.port not in (None, 443)
            ):
                raise ValueError
        else:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Invalid provider origin") from None
    return value.rstrip("/")


def _usage(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or any(
        not isinstance(name, str) or type(count) is not int or count < 0
        for name, count in value.items()
    ):
        return None
    return value


class HTTPProvider:
    """Adapters own their HTTP session; the gateway owns its lifetime."""

    def __init__(self, config: ProviderConfig, key: str) -> None:
        self._kind = config.kind
        self._origin = _validated_origin(config.kind, config.base_url)
        self._model = config.model
        if not key or not key.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValueError("Invalid provider key")
        self._headers = (
            {"authorization": f"Bearer {key}"}
            if config.kind == "fake"
            else {"x-api-key": key, "anthropic-version": "2023-06-01"}
        )
        self._client = httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=False,
            trust_env=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete(self, request: ChatRequest) -> ChatResponse:
        if self._kind == "fake":
            path = "/chat"
            payload = request.model_dump(mode="json")
        else:
            path = "/v1/messages"
            payload = {
                "model": self._model,
                "max_tokens": request.max_tokens,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                    if message.role != "system"
                ],
            }
            system = [message.content for message in request.messages if message.role == "system"]
            if system:
                payload["system"] = "\n\n".join(system)
        try:
            # A single request: retries and redirects are intentionally absent.
            async with self._client.stream(
                "POST", self._origin + path, json=payload, headers=self._headers
            ) as response:
                if response.status_code != 200:
                    raise ProviderError()
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=16_384):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ProviderError()
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ProviderError()
            if self._kind == "fake":
                text = data.get("text")
                usage = _usage(data.get("usage"))
            else:
                content = data.get("content")
                if not isinstance(content, list) or not content:
                    raise ProviderError()
                if any(
                    not isinstance(block, dict)
                    or block.get("type") != "text"
                    or not isinstance(block.get("text"), str)
                    for block in content
                ):
                    raise ProviderError()
                text = "".join(block["text"] for block in content)
                raw_usage = data.get("usage")
                usage = (
                    _usage({name: raw_usage.get(name) for name in ("input_tokens", "output_tokens")})
                    if isinstance(raw_usage, dict)
                    else None
                )
            if not isinstance(text, str) or not text:
                raise ProviderError()
            return ChatResponse(text=text, usage=usage)
        except Exception:
            # Never include provider bodies, URLs, headers or raw exceptions.
            raise ProviderError() from None


def build_provider(config: ProviderConfig, key: str) -> HTTPProvider:
    return HTTPProvider(config, key)
