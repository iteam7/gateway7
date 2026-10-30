"""Private synthetic HTTP fixture for the packaged demo, without text retention."""

import hmac
import json
import os

from fastapi import FastAPI, HTTPException, Request

from gateway7.models import ChatRequest

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: Request) -> dict[str, object]:
    key = os.environ.get("GATEWAY7_DEMO_KEY", "")
    if not key.startswith("gateway7-synthetic-") or not hmac.compare_digest(
        request.headers.get("authorization", "").encode(),
        f"Bearer {key}".encode(),
    ):
        raise HTTPException(status_code=401, detail="Synthetic key rejected")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            raise HTTPException(status_code=413, detail="Demo body too large")
    try:
        parsed = ChatRequest.model_validate(json.loads(body))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid demo request") from None
    content = parsed.messages[-1].content
    if parsed.requires_tools or content is None:
        raise HTTPException(status_code=400, detail="Demo provider supports text-only requests")
    return {
        "text": "pong — " + content,
        "usage": {"input_tokens": 12, "output_tokens": 4},
    }
