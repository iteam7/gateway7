# HTTP APIs and OpenAI SDK compatibility

Gateway7 offers its native `POST /chat` endpoint and a text-only subset of the OpenAI Chat Completions API.
Both use the same authentication, model permissions, middleware chain, deadlines and provider adapter.
The OpenAI-compatible base URL is `http://127.0.0.1:8000/v1` for the local demo.

## Call from the OpenAI Python SDK

Start `gateway7 demo` and set the public synthetic demo client token:

```sh
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
```

The development environment includes the official OpenAI Python SDK; the gateway runtime does not require it.
Run this client with `uv run --locked python` from a checkout, or install the SDK in your own client environment:

```python
import os
from openai import DefaultHttpx2Client, OpenAI

with OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key=os.environ["GATEWAY7_TOKEN"],
    max_retries=0,
    timeout=65.0,
    http_client=DefaultHttpx2Client(trust_env=False, follow_redirects=False),
) as client:
    print([model.id for model in client.models.list().data])
    answer = client.chat.completions.create(
        model="fake",
        messages=[{"role": "user", "content": "Contact synthetic@example.com; SECRET-TEST"}],
        max_completion_tokens=1024,
    )
    print(answer.choices[0].message.content)
```

`api_key` here is the **gateway client token**, not the provider credential.
This client sends requests to the local gateway even when the gateway's selected provider is Claude or Gemini.
Set `model` to an ID allowed for this client; `/v1/models` lists that client's configured choices.
The SDK can retry failed requests by default, so the example explicitly disables client retries.
The explicit HTTP client also disables environment proxies and redirects; this example targets the locked SDK version used by this project.

## Supported compatibility subset

| Endpoint/field | Supported behavior |
| --- | --- |
| `GET /v1/models` | Configured model IDs allowed for the authenticated client; no upstream model discovery |
| `POST /v1/chat/completions` | One nonstreaming text completion |
| `model` | Required; must be on the client's allowlist for the single configured provider |
| `messages` | Nonempty list with plain string content and roles `system`, `developer`, `user`, `assistant` |
| `developer` role | Normalized to the internal system role |
| `max_tokens` or `max_completion_tokens` | One of these fields, 1–4096; omitted means 256 |
| `stream` | Omitted or `false` |
| `n` | Omitted or `1` |
| `store` | Omitted or `false` |

Unsupported fields are rejected with HTTP 400; they are not silently ignored.
This includes streaming, tools, image/audio content, response-format controls, sampling options and multiple choices.
Responses include the normal completion envelope, selected model, one assistant choice and the provider's normalized `stop` or `length` finish reason.
Known usage becomes `prompt_tokens`, `completion_tokens` and their total; missing/invalid provider usage remains `null`.
No response is persisted by Gateway7, and there are no list/retrieve/delete completion endpoints.
The Responses API and embeddings API are not implemented.

Compatibility tests use the installed official Python SDK over local HTTP, plus strict payload/error fixtures.
The supported request/response shape follows the [official Chat Completions reference](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create); client setup follows the [official Python SDK guide](https://developers.openai.com/api/reference/python).
This is compatibility with the documented subset, not a claim that every OpenAI client feature works.

## Native chat

```sh
curl --fail-with-body http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $GATEWAY7_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"fake","messages":[{"role":"user","content":"Reply pong"}],"max_tokens":256}'
```

The native endpoint accepts `messages`, optional `model` and optional `max_tokens`.
Its roles are `system`, `user` and `assistant`; the response contains `text`, normalized `usage` and `request_id`.
If the native request omits `model`, the configured provider model is used and must still be allowed for that client.
Model selection is pinned before middleware execution; plugins cannot change the authorized model.

## Errors and operational endpoints

| HTTP status | Meaning |
| --- | --- |
| 400 | Unsupported/invalid OpenAI-compatible payload |
| 401 | Missing, malformed or unknown gateway bearer token |
| 403 | Model permission denied or middleware policy denied |
| 413 | Request body exceeds the configured limit |
| 422 | Invalid native `/chat` payload |
| 500 | Middleware/internal processing failure |
| 502 | Provider transport, credential, rate-limit or unsupported-response error |
| 503 | Gateway not ready |
| 504 | Overall request deadline exceeded |

`/v1/*` errors use an OpenAI-style `error` object with safe `message`, `type`, `param` and `code`, plus a request ID.
The `WWW-Authenticate: Bearer` header accompanies authentication errors.
No error echoes the bearer token, request text or raw provider response.
All upstream failure categories retain HTTP 502 and the `provider_error` code on both APIs.
The [fixed diagnostic reasons](observability.md#provider-failure-reasons) appear only in gateway logs and the provider failure metric; they do not add response fields or trigger retries.
`/health`, `/ready` and `/metrics` are unauthenticated operational endpoints; keep them within the trusted deployment network.
See [authentication](authentication.md) and [observability](observability.md) for configuration and diagnosis.
