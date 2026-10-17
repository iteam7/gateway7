"""Loopback-only fixture server. Its inspection endpoint is for synthetic data."""

from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import json
import os

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from gateway7.models import ChatRequest


ANSWER = "pong — deterministic upstream"
USAGE = {"input_tokens": 12, "output_tokens": 4}
MAX_BODY_BYTES = 65_536


@asynccontextmanager
async def lifespan(app: FastAPI):
    key = os.environ.get("DEMO_PROVIDER_KEY", "")
    if not key.startswith("gateway7-synthetic-"):
        raise RuntimeError("DEMO_PROVIDER_KEY must be an explicitly synthetic demo value")
    app.state.demo_key = key
    app.state.requests = []
    yield
    app.state.requests.clear()
    app.state.demo_key = ""


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
async def health():
    return {"status": "ok", "fixture": True}


@app.get("/requests")
async def requests(request: Request):
    # No headers or credentials are retained, even for inspection.
    return {"requests": request.app.state.requests}


@app.post("/chat")
async def chat(request: Request):
    supplied = request.headers.get("authorization", "").encode("utf-8")
    expected = f"Bearer {request.app.state.demo_key}".encode("utf-8")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Demo key rejected")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Demo body too large")
    try:
        parsed = ChatRequest.model_validate(json.loads(body))
    except (ValueError, ValidationError):
        raise HTTPException(status_code=400, detail="Invalid demo request") from None
    request.app.state.requests.append(
        {"body": parsed.model_dump(mode="json"), "key_accepted": True}
    )
    # Bound the diagnostic store; all demo inputs must be synthetic.
    del request.app.state.requests[:-100]
    return {"text": ANSWER, "usage": USAGE}
