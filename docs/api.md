# HTTP APIs and OpenAI SDK compatibility

Connect your application to Gateway7 through `POST /chat` or the supported part of the OpenAI Chat Completions API.
Both paths use the same client permissions, middleware and selected provider.
The examples below use the local synthetic demo, so they need no provider account or paid API call.

## Connect to the local demo

Start the demo using the [setup guide](setup.md#install-from-a-checkout), and leave it running.
In a second terminal, set its address and public test token:

```sh
export GATEWAY7_URL=http://127.0.0.1:8000
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
```

List the models available to this client:

```sh
curl --fail-with-body --silent --show-error "$GATEWAY7_URL/v1/models" \
  -H "Authorization: Bearer $GATEWAY7_TOKEN"
```

The response contains one model with ID `fake`.
This is the demo's model name; it does not refer to a hosted LLM.
Send a text request with that model:

```sh
curl --fail-with-body --silent --show-error "$GATEWAY7_URL/v1/chat/completions" \
  -H "Authorization: Bearer $GATEWAY7_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "model": "fake",
  "messages": [
    {"role": "user", "content": "Contact synthetic@example.com; SECRET-TEST"}
  ],
  "max_completion_tokens": 256,
  "stream": false
}
JSON
```

Expect HTTP 200 with this text in `choices[0].message.content`:

```text
pong — Contact [EMAIL]; [removed]
```

The demo masks the email before the provider call and removes `SECRET-TEST` from the response.
Its fixed test usage is 12 input tokens and 4 output tokens; these are fixture values, not measurements from a real model.
For denial examples, continue with [client access checks](authentication.md#check-allowed-and-denied-requests).

## Call from the OpenAI Python SDK

Keep the demo running and the two variables above set.
From the checkout, run this complete example with the SDK included in the locked development environment:

```sh
uv run --locked python - <<'PY'
import os
from openai import DefaultHttpx2Client, OpenAI

with OpenAI(
    base_url=os.environ["GATEWAY7_URL"] + "/v1",
    api_key=os.environ["GATEWAY7_TOKEN"],
    max_retries=0,
    timeout=65.0,
    http_client=DefaultHttpx2Client(trust_env=False, follow_redirects=False),
) as client:
    print([model.id for model in client.models.list().data])
    answer = client.chat.completions.create(
        model="fake",
        messages=[
            {"role": "user", "content": "Contact synthetic@example.com; SECRET-TEST"}
        ],
        max_completion_tokens=256,
        stream=False,
    )
    print(answer.choices[0].message.content)
    print(answer.choices[0].finish_reason)
    if answer.usage is not None:
        print(answer.usage.prompt_tokens, answer.usage.completion_tokens,
              answer.usage.total_tokens)
PY
```

Expected output:

```text
['fake']
pong — Contact [EMAIL]; [removed]
stop
12 4 16
```

The `api_key` argument holds the **gateway client token**.
The provider API key stays on the gateway server.
For a deployed gateway, change the URL, client token and model to the values supplied by its operator.
The same client interface works when that gateway is configured for OpenAI, Claude or Gemini.
It does not select or switch providers itself.

This example uses the official Python SDK version fixed by the project's lockfile.
`max_retries=0` prevents the SDK from repeating a failed call, and the explicit HTTP client disables environment proxies and redirects.
The [official SDK guide](https://developers.openai.com/api/reference/python) explains these client options.
The gateway server itself does not require the SDK.

## Supported compatibility subset

Gateway7 accepts one complete text answer per request.
Streaming and other OpenAI API features are outside this subset.

| Endpoint or field | Supported behavior |
| --- | --- |
| `GET /v1/models` | Lists the authenticated client's configured model IDs; does not contact the provider |
| `POST /v1/chat/completions` | Returns one nonstreaming text completion |
| `model` | Required; must be allowed for this client on the configured provider |
| `messages` | A nonempty list; each item has a role and plain string `content` |
| Message roles | `system`, `developer`, `user`, `assistant`; `developer` is treated as `system` |
| `max_tokens` or `max_completion_tokens` | One field at most; integer from 1 to 4096; omitted means 256; `null` is rejected |
| `stream` | Omitted or `false` |
| `n` | Omitted or integer `1` |
| `store` | Omitted or `false` |

Other fields return HTTP 400, even if their values are empty.
For example, `tools`, `tool_choice`, `temperature`, `response_format` and `stream_options` are not supported.
Image/audio content, tools, multiple choices, the Responses API and embeddings are not implemented.
Gateway7 does not save completions and has no list, retrieve or delete completion endpoints.

A successful response includes `id`, `object: "chat.completion"`, a creation timestamp, the selected `model` and one assistant choice.
Its `finish_reason` is `stop` or `length`; `length` means the provider reached its output limit, so the text may be incomplete.
When valid provider usage is available, `usage` contains `prompt_tokens`, `completion_tokens` and `total_tokens`.
Otherwise `usage` is `null`; applications must handle that case without assuming zero consumption.

The shape follows the [official Chat Completions reference](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create) within the limits above.
Local HTTP tests exercise the official Python SDK and strict request/response fixtures.
Those checks do not establish compatibility with every SDK feature or access to a real provider account.

## Native chat

Use the smaller native format when your application does not need an OpenAI-shaped response.
With the same demo variables set:

```sh
curl --fail-with-body --silent --show-error "$GATEWAY7_URL/chat" \
  -H "Authorization: Bearer $GATEWAY7_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "model": "fake",
  "messages": [
    {"role": "user", "content": "Contact synthetic@example.com; SECRET-TEST"}
  ],
  "max_tokens": 256
}
JSON
```

The answer is the same masked and redacted text, now in `text`.
The response also has `usage` with `input_tokens`/`output_tokens` when known, and a `request_id`.
Unknown usage is `null`.

Native requests accept `messages`, optional `model` and optional `max_tokens` from 1 to 4096; the default is 256.
Messages use roles `system`, `user` or `assistant` and plain string content.
Other fields are rejected.
If `model` is omitted, the gateway uses `provider.model`, which must still be allowed for the client.
The selected model is fixed before middleware runs, so a plugin cannot change it.

## Errors and operational endpoints

Handle errors by their HTTP status and stable code.
Keep the request ID when asking the gateway operator to investigate.
It is returned in the `X-Request-ID` header on both APIs and in error bodies.
Native success bodies also include `request_id`; OpenAI success bodies use a `chatcmpl-` ID built from it.

| HTTP status | Code or meaning | Application action |
| --- | --- | --- |
| 400 | `invalid_request` on the OpenAI-compatible API | Remove unsupported fields or fix the payload |
| 401 | `unauthorized` | Supply the correct gateway bearer token |
| 403 | `model_forbidden` or `policy_denied` | Choose an allowed model or check the request policy |
| 404 / 405 | `not_found` / `method_not_allowed` | Check the exact path and HTTP method |
| 413 | `body_too_large` | Reduce the request body |
| 422 | `invalid_request` on native `/chat` | Fix the native payload |
| 500 | `plugin_error` or `internal_error` | Report the request ID to the operator |
| 502 | `provider_error` | Ask the operator to check provider diagnostics |
| 503 | `unavailable` or `overloaded` | Check readiness or reduce concurrent requests |
| 504 | `timeout` | The overall gateway deadline expired |

Use the paths exactly as shown; trailing slashes return 404.
On `/v1/*`, errors contain `error.message`, `error.type`, `error.param`, `error.code` and a top-level `request_id`.
`param` identifies a known invalid or unsupported field when possible; arbitrary field names and submitted values are hidden.
Native errors contain `error.code`, `error.message` and `request_id`.
Authentication failures also include `WWW-Authenticate: Bearer`.

Gateway7 does not queue or automatically retry requests.
When all pipeline slots are occupied, `overloaded` is returned before middleware or a provider call.
The default limit is 64 active pipelines per process, shared by both chat APIs.

A failed answer may still have consumed provider tokens.
The gateway retains valid usage from a decoded successful provider HTTP response in its metrics, even if answer validation or response middleware later rejects delivery.
The client still receives an error without answer text or usage fields.
See [usage and failure metrics](observability.md#metric-contract) for diagnosis.

| Anonymous endpoint | Purpose |
| --- | --- |
| `GET /health` | Process liveness |
| `GET /ready` | Local startup/shutdown readiness; no provider request |
| `GET /metrics` | Prometheus metrics |

These endpoints do not require a client token and should stay within the trusted deployment network.
Readiness does not verify provider credentials or model access.
See [authentication](authentication.md) for client setup and [observability](observability.md) for provider failure reasons.
