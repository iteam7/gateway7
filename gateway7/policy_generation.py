"""Generate editable suggestions using a dedicated, credential-free local Ollama model."""

import asyncio
import os
from collections.abc import Callable
from typing import Any, Literal

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from gateway7.errors import GatewayError
from gateway7.policy_admin import PolicySpec, Template


class _Input(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class DraftRequest(_Input):
    description: str = Field(min_length=1, max_length=1024, pattern=r"\S")


class CasesRequest(_Input):
    template: Template
    term: str = Field(default="SYNTHETIC_TERM", min_length=1, max_length=128)


class _CasePlan(_Input):
    positive: Literal["alone", "sentence", "repeated"]
    negative: Literal["ordinary", "blank", "numeric"]
    boundary: Literal["adjacent", "punctuation", "end"]


async def _generate(schema: type[BaseModel], instruction: str, content: str) -> BaseModel:
    model = os.environ.get("GATEWAY7_DRAFT_OLLAMA_MODEL", "").strip()
    if not model:
        raise GatewayError("unavailable")
    payload = {
        "model": model,
        "stream": False,
        "format": schema.model_json_schema(),
        "options": {"temperature": 0, "num_predict": 512},
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": content},
        ],
    }
    try:
        async with asyncio.timeout(35), httpx.AsyncClient(timeout=30, trust_env=False) as client:
            async with client.stream(
                "POST", "http://127.0.0.1:11434/api/chat", json=payload
            ) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > 32768:
                        raise ValueError("Response too large")
                    body.extend(chunk)
        envelope = _Reply.model_validate_json(body)
        return schema.model_validate_json(envelope.message.content)
    except (httpx.HTTPError, ValueError, TimeoutError, RecursionError):
        raise GatewayError("provider_error") from None


class _Message(BaseModel):
    content: str = Field(max_length=8192)


class _Reply(BaseModel):
    message: _Message
    done: Literal[True]


def register_generation(app: FastAPI, require_management: Callable[[], Any]) -> None:
    @app.post("/operator/policy-draft/generate", include_in_schema=False)
    async def generate(payload: DraftRequest):
        require_management()
        spec = await _generate(
            PolicySpec,
            "Return a JSON policy for the description. Only use the supplied template schema. "
            "Use request phase unless specified. For phone_mask and email_mask use empty terms. "
            "literal_guard and literal_redact require literal terms. Never generate code.",
            payload.description,
        )
        return {"spec": spec.model_dump()}

    @app.post("/operator/policy-draft/generate-cases", include_in_schema=False)
    async def generate_cases(payload: CasesRequest):
        require_management()
        plan = await _generate(
            _CasePlan,
            "Select one synthetic fixture variation per category to test this template. "
            "Positive contains an example, negative contains no example, boundary probes edges.",
            payload.template,
        )
        assert isinstance(plan, _CasePlan)
        sample = {
            "phone_mask": "+7 000 000-00-00",
            "email_mask": "sample@example.invalid",
            "literal_guard": payload.term,
            "literal_redact": payload.term,
        }[payload.template]
        negative = {"ordinary": "No match.", "blank": "", "numeric": "42"}[plan.negative]
        if payload.template.startswith("literal_"):
            # Empty text is a negative example for every allowed set of nonempty terms.
            negative = ""
        return {
            "cases": [
                {
                    "kind": "positive",
                    "text": {
                        "alone": sample,
                        "sentence": f"Example: {sample}.",
                        "repeated": f"{sample} / {sample}",
                    }[plan.positive],
                },
                {
                    "kind": "negative",
                    "text": negative,
                },
                {
                    "kind": "boundary",
                    "text": {
                        "adjacent": f"x{sample}x",
                        "punctuation": f"({sample})",
                        "end": f"At end: {sample}",
                    }[plan.boundary],
                },
            ]
        }
