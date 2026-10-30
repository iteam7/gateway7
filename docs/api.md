# HTTP APIs and OpenAI SDK compatibility

Connect your application to Gateway7 through `POST /chat` or the supported part of the OpenAI Chat Completions API.
Both paths use the same client permissions, middleware and selected provider.
The initial examples below use the local synthetic demo, so they need no provider account or paid API call.
Streaming and function-tool turns require the OpenAI provider configuration described below.

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

Gateway7 supports ordinary text completions for every configured provider.
The OpenAI provider additionally supports streamed upstream Chat Completions and guarded function-tool turns.

| Endpoint or field | Supported behavior |
| --- | --- |
| `GET /v1/models` | Lists the authenticated client's configured model IDs; does not contact the provider |
| `POST /v1/chat/completions` | One assistant response, as JSON or checked SSE |
| `model` | Required; must be allowed for this client on the configured provider |
| `messages` | Nonempty history; string text, plus the function-tool history described below |
| Message roles | `system`, `developer`, `user`, `assistant`, `tool`; `developer` becomes `system` |
| `max_tokens` or `max_completion_tokens` | One field at most; integer from 1 to 4096; omitted means 256; explicit `null` is rejected |
| `stream` | Boolean; `true` requires the OpenAI provider |
| `stream_options` | With `stream: true` only; supports boolean `include_usage` |
| `tools` | Up to 128 `type: function` definitions, with name, optional description, JSON-object parameters and optional strict flag |
| `tool_choice` | `auto`, `none`, `required`, or a named function choice |
| `parallel_tool_calls` | Omitted or `false`; at most one function call per response |
| Generation controls | Finite `temperature` 0–2, `top_p` 0–1, frequency/presence penalties −2–2, signed 64-bit integer `seed`, and 1–4 nonempty `stop` strings of at most 1024 characters each |
| `n` | Omitted or integer `1` |
| `store` | Omitted or `false` |

Tools, tool history and generation controls require the OpenAI provider.
Fake, Claude and Gemini configurations reject those capabilities and `stream: true` before contacting their provider.
Unknown fields still return HTTP 400, including `response_format`, `reasoning_effort`, legacy `functions`/`function_call`, media content and Responses API options.
The gateway does not save completions or implement embeddings or completion retrieval.

A JSON response includes `id`, `object: "chat.completion"`, creation time, the selected `model` and one assistant choice.
The finish reason is `stop`, `length` or `tool_calls`.
`length` means generation reached its output limit; the gateway does not invent a successful stop for a truncated provider stream.
When valid provider usage is available, `usage` has `prompt_tokens`, `completion_tokens` and `total_tokens`.
Otherwise it is `null`, which must not be interpreted as zero consumption.

### Upstream streaming and checked SSE

With the OpenAI provider, `stream: true` makes the actual upstream Chat Completions request stream.
Gateway7 reads bounded SSE events, assembles the complete response and runs all response middleware before starting the client's response.
Only the checked result is encoded as `text/event-stream`.
This preserves whole-response blocking and redaction; the client does not receive tokens while the model is generating them.
The upstream response is limited to 1 MiB and each SSE event to 64 KiB; provider, middleware, overall request and response-send deadlines still apply.

Each client chunk has the same completion ID, creation time and selected model.
The stream contains the assistant role, checked text or structured tool-call deltas, the provider's normalized finish reason, and `data: [DONE]`.
If `stream_options.include_usage` is true, a final chunk with `choices: []` carries known usage or `null` before `[DONE]`.
Errors or policy denials before delivery retain their normal JSON error body and HTTP status; no unchecked text or tool arguments are sent first.

After starting the OpenAI configuration in the [setup guide](setup.md#openai-with-a-env-file), use its gateway client token and allowed model.
This complete SDK call selects streaming:

```python
import os
from openai import DefaultHttpx2Client, OpenAI

with OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key=os.environ["GATEWAY7_CLIENT_TOKEN"],
    max_retries=0,
    timeout=65.0,
    http_client=DefaultHttpx2Client(trust_env=False, follow_redirects=False),
) as client:
    with client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": "Reply with the word pong"}],
        max_completion_tokens=256,
        stream=True,
        stream_options={"include_usage": True},
    ) as stream:
        for chunk in stream:
            if chunk.choices:
                print(chunk.choices[0].delta.content or "", end="", flush=True)
            elif chunk.usage is not None:
                print("\nTotal tokens:", chunk.usage.total_tokens)
```

The environment variable in this example must hold the gateway client token; the provider key stays on the server.
The sample model must be available to the provider account and allowed for that client.
The real-provider call can incur charges.

### Function-tool turns

Declare tools in the request and preserve the returned `assistant.tool_calls` in the next request's history.
An assistant call-only message has `content: null` and `finish_reason: tool_calls`.
After executing that call, the harness adds a `role: tool` message with string content and the same `tool_call_id`.
Missing, duplicated or mismatched call/result identifiers are rejected.
Argument and parameter-schema JSON objects are bounded to 64 KiB and nesting depth 64; there is at most one call per model turn.
Gateway7 forwards and checks tool turns; the harness executes the function.

For SSE, the call is a structured `delta.tool_calls` entry with its index, ID, function name and JSON arguments.
It is never converted into plain assistant text.
Every active middleware must [declare tool support](plugins.md#tool-payload-capability); a legacy text-only chain rejects a tool turn before contacting the provider.
Reference middleware inspect tool arguments and definition text as well as ordinary messages.
Structured matches are blocked rather than rewritten with a regex; tool-result text follows the existing text policy on the next request.

The [OpenCode walkthrough](setup.md#opencode-v2) provides the bounded harness profile and a repeatable synthetic check.
Local tests exercise the locked official Python SDK, and that walkthrough exercises an actual OpenCode V2 binary against an injected OpenAI transport.
These checks do not establish access to a real provider account or compatibility with all OpenCode releases and features.

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
