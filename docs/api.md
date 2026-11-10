# HTTP APIs and OpenAI SDK compatibility

Connect your application through `POST /chat`, the supported Chat Completions subset, or the separate [native Responses contract](#native-responses-http).
These routes share client permissions, configured middleware instances and the selected provider, with distinct typed payloads and hooks.
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
The [official SDK guide](https://github.com/openai/openai-python) explains these client options.
The gateway server itself does not require the SDK.

## Supported compatibility subset

Gateway7 supports ordinary text completions for every configured provider.
The OpenAI provider additionally supports streamed upstream Chat Completions and guarded function-tool turns.

| Endpoint or field | Supported behavior |
| --- | --- |
| `GET /v1/models` | Lists the authenticated client's configured model IDs; does not contact the provider |
| `POST /v1/chat/completions` | One assistant response, as JSON or SSE; full-response checks remain the streaming default |
| `model` | Required; must be allowed for this client on the configured provider |
| `messages` | Nonempty history; string text, plus the function-tool history described below |
| Message roles | `system`, `developer`, `user`, `assistant`, `tool`; `developer` becomes `system` |
| `max_tokens` or `max_completion_tokens` | One field at most; integer from 1 to 4096; omitted means 256; explicit `null` is rejected |
| `stream` | Boolean; `true` requires the OpenAI provider |
| `stream_options` | With `stream: true` only; supports boolean `include_usage` |
| `X-Gateway7-Stream-Mode` header | Omitted or `buffered` keeps full-response checks; `early` explicitly selects the restricted early-text mode below |
| `tools` | Up to 128 `type: function` definitions, with name, optional description, JSON-object parameters and optional strict flag |
| `tool_choice` | `auto`, `none`, `required`, or a named function choice |
| `parallel_tool_calls` | Omitted or `false`; at most one function call per response |
| Generation controls | Finite `temperature` 0–2, `top_p` 0–1, frequency/presence penalties −2–2, signed 64-bit integer `seed`, and 1–4 nonempty `stop` strings of at most 1024 characters each |
| `n` | Omitted or integer `1` |
| `store` | Omitted or `false` |

Tools, tool history and generation controls require the OpenAI provider.
Fake, Claude and Gemini configurations reject those capabilities and `stream: true` before contacting their provider.
On Chat Completions, unknown fields still return HTTP 400, including `response_format`, `reasoning_effort`, legacy `functions`/`function_call`, media content and native Responses options.
The gateway does not save completions or implement embeddings or completion retrieval.

A JSON response includes `id`, `object: "chat.completion"`, creation time, the selected `model` and one assistant choice.
The finish reason is `stop`, `length` or `tool_calls`.
These are adapter-normalized reasons, not a promise to preserve every raw upstream value: a valid OpenAI function call paired with upstream `stop` becomes `tool_calls` after validation.
`length` means generation reached its output limit; the gateway does not invent a successful stop for a truncated provider response.
An OpenAI `length` response without a tool call preserves partial or empty text, including explicitly null content normalized to an empty string, even for `required` or named `tool_choice`.
Invalid or incomplete calls still fail validation rather than becoming executable truncated results.
When valid provider usage is available, `usage` has `prompt_tokens`, `completion_tokens` and `total_tokens`.
Otherwise it is `null`, which must not be interpreted as zero consumption.

### Upstream streaming and checked SSE

With the OpenAI provider, `stream: true` makes the actual upstream Chat Completions request stream.
With no `X-Gateway7-Stream-Mode` header, or with its value set to `buffered`, Gateway7 reads bounded SSE events, assembles the complete response and runs all response middleware before starting the client's response.
Only the checked result is encoded as `text/event-stream`.
This preserves whole-response blocking and redaction; the client does not receive tokens while the model is generating them.
The upstream response is limited to 1 MiB and each SSE event to 64 KiB; provider, middleware, overall request and response-send deadlines still apply.
During tool-call assembly, omitted or null optional delta fields (`id`, `type`, `function`, `name` and `arguments`) leave previously accumulated state unchanged.
The completed call must still have a valid identifier, function name and JSON-object arguments and match the requested tool choice.

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
Choose a per-run request/token and spending budget before any live check; `max_completion_tokens` bounds one request, not an agent session's total cost.

### Opt in to early Chat Completions text

The implemented early-text path is under independent review; it is not evidence of completed early-stream harness or Responses/Codex compatibility.
For `POST /v1/chat/completions`, send exactly one `X-Gateway7-Stream-Mode: early` header together with `stream: true` to select it.
In the SDK call above, the request option is `extra_headers={"X-Gateway7-Stream-Mode": "early"}`; do not add a stream-mode field to the JSON body.
The header selects gateway behavior and is not forwarded to the provider.
Omitting it or sending `X-Gateway7-Stream-Mode: buffered` retains the full-response checks and ordinary pre-delivery HTTP 403 policy denials described above.

Only OpenAI streaming requests with an explicitly compatible request-only middleware chain can use early text.
Every active middleware must support `prepare_early_stream` and accept its configured request-only behavior; unknown compatibility is rejected rather than inferred or bypassed.
The reference policies accept this path only with `phase: request`; `phase: response` and `phase: both` are incompatible even when their rules would not match.
The unchanged `config/openai.yaml` is therefore incompatible: an otherwise allowed early request returns HTTP 400, while `BLOCK-ME-TEST` is denied first by its request guard with HTTP 403 (`policy_denied`).
Both outcomes make zero provider calls.
Do not remove privacy policies from a shared configuration to make the header work; use buffered delivery whenever response checks are required.
See the [setup guidance](setup.md#choose-streaming-delivery-mode) before selecting a separate request-only configuration.

Unknown, empty, combined or duplicate stream-mode header values return HTTP 400 before provider work.
Selecting `early` for a non-streaming request, native `/chat` or an unsupported provider also returns HTTP 400 without a provider call.
A missing preparation hook returns HTTP 400 before provider work.
When hooks are present, they run in configured order: a reached incompatible hook returns HTTP 400, but an earlier request-hook denial returns ordinary JSON HTTP 403 (`policy_denied`) first.
Neither outcome invokes the provider or bypasses a policy.

Nonempty text can reach the client before upstream EOF; empty role-only deltas do not start delivery.
The gateway awaits each downstream send before advancing provider consumption, so slow clients apply direct backpressure without an unbounded producer queue.
Tool-call fragments are never released early: calls, the normalized finish reason, requested usage and `[DONE]` wait for complete provider-response validation.
Early text does not pass through full-response middleware, and already delivered text cannot be retracted if later validation fails.

Before HTTP headers are sent, failures retain ordinary JSON error bodies and statuses, including HTTP 504 for the overall deadline.
After delivery begins, HTTP 200 cannot be changed: a later failure emits a sanitized top-level SSE `error` recognized by the OpenAI SDK when the connection and deadline permit, or aborts the stream.
A failed stream does not invent a successful finish reason or send `[DONE]`; clients must treat errors or premature EOF as incomplete delivery, even after receiving text.
Provider TLS verification, size bounds, deadlines, admission limits and cancellation cleanup remain in force; a slot stays occupied until the admitted work and cleanup finish.

### Function-tool turns

For Chat Completions, declare tools in the request and preserve the returned `assistant.tool_calls` in the next request's history.
An assistant call-only message has `content: null` and `finish_reason: tool_calls`.
After executing that call, the harness adds a `role: tool` message with string content and the same `tool_call_id`.
Missing, duplicated or mismatched call/result identifiers are rejected.
Argument and parameter-schema JSON objects are bounded to 64 KiB and nesting depth 64; there is at most one call per model turn.
Gateway7 forwards and checks tool turns; the harness executes the function.

For SSE, the call is a structured `delta.tool_calls` entry with its index, ID, function name and JSON arguments.
It is never converted into plain assistant text.
Every active middleware must [declare tool support](plugins.md#tool-payload-capability); a legacy text-only chain rejects a tool turn before contacting the provider.
Reference middleware inspect request tool arguments and definition text as well as ordinary messages.
In buffered mode they also inspect returned tool arguments.
Structured matches are blocked rather than rewritten with a regex; tool-result text follows the existing text policy on the next request.
Early mode retains request-side checks and final tool-call validation, but it has no response-policy inspection; keep buffered mode if returned arguments require those checks.

The [OpenCode walkthrough](setup.md#opencode-v2) provides the bounded harness profile and a repeatable synthetic check.
Local tests exercise the locked official Python SDK, and that walkthrough exercises an actual OpenCode V2 binary against an injected OpenAI transport.
These checks do not establish access to a real provider account or compatibility with all OpenCode releases and features.

## Native Responses HTTP

`POST /v1/responses` implements a closed, stateless native HTTP subset for the OpenAI provider, as JSON or default checked SSE, with the separate [native early-text opt-in contract](#opt-in-to-native-early-text).
It preserves ordered native items rather than flattening them into Chat Completions messages or silently dropping unknown fields.
The implementation is under independent review; the synthetic acceptance coverage does not establish live Codex readiness or full OpenAI Responses compatibility.
The authoritative closed shapes are in `gateway7/responses_models.py`; see [request controls and limits](#request-controls-and-limits) for the maintained request contract.

### Request controls and limits

| Field | Accepted contract |
| --- | --- |
| `model` | Required authenticated model ID, pinned outside middleware and sent unchanged to the configured provider |
| `input` | String or ordered list of supported native history items |
| `instructions` | Optional string or `null` |
| `max_output_tokens` | Integer 1–4096; omitted means 1024, not the Chat Completions default |
| `stream` | Boolean; omitted or `false` returns JSON; `true` consumes upstream native SSE and returns checked native SSE by default |
| `store` | Omitted or `false`; the upstream request always carries `false` |
| `tools` | Up to 128 closed function, custom, namespace, tool-search or web-search definitions |
| `tool_choice` | `auto`, `none`, `required`, or an advertised function/custom choice with optional namespace, or an advertised `web_search`/`tool_search` choice |
| `parallel_tool_calls` | Boolean, default `true`; native ordered parallel calls are separate from Chat's one-call limit |
| `reasoning` | Closed `effort`, `summary` and `context` controls |
| `text` | Optional verbosity and `text` or named `json_schema` format with a required boolean `strict` field |
| `include` | Only `reasoning.encrypted_content`, `web_search_call.action.sources` and `message.input_image.image_url`; no duplicates |
| `prompt_cache_key`, `client_metadata`, `service_tier` | Optional cache key, string-to-string client metadata, and the DTO's enumerated service tiers |
| `stream_options` | Only `reasoning_summary_delivery: sequential_cutoff` and boolean `include_obfuscation`, with the DTO's nullable optional fields |

The existing request-body limit applies, including media and metadata: 65,536 bytes by default.
Input and output item lists are bounded to 4096 items; function arguments and JSON-object schemas remain bounded to 64 KiB with the existing JSON-depth checks.
Unknown fields or item/tool kinds, duplicate JSON keys and unsupported stateful controls are rejected rather than narrowed into an accepted request.
This request subset does not accept `previous_response_id`, `conversation`, `background`, `store: true`, retrieval/cancellation APIs, WebSockets, realtime sessions or arbitrary hosted tools.
Request `metadata`, `temperature`, `top_p` and `truncation` are not accepted merely because some similarly named provider response echo fields are typed.
There is one gateway-owned provider attempt, no automatic retry, failover or model substitution; ordinary TLS, transport, admission and deadline boundaries remain in force.

### Native history, tools and identity

Messages keep their native `system`, `developer`, `user` or `assistant` role, content parts and optional assistant `phase` (`commentary` or `final_answer`).
Supported history also includes reasoning, function/custom calls and their outputs, client/server tool-search calls/results, and typed web-search records.
Output order, namespaces, response/item identities and call/result correlation are retained.
An output item's `id` is distinct from its executable `call_id`; return a result using `call_id`, not the SSE `item_id` or the response ID.
History must contain matching preceding calls and results of the right kind; duplicate identities, orphaned or missing results and malformed or mismatched call/result data are rejected.
A matched historical call/result pair does not require a current tool declaration; advertisement checks apply to newly returned provider calls, not historical pairs.
Client tool-search results can advertise typed function/custom/namespace definitions for subsequent calls.

Function arguments remain their original string after JSON-object validation.
Custom tools retain raw `input` strings and their `text` or `grammar` definition (`lark` or `regex`); the gateway neither parses custom input as function JSON nor executes or validates it against the grammar.
Reasoning summaries, visible reasoning text and typed message metadata remain native data, not hidden assistant-text concatenation.
Local function/custom calls and client tool search are executed by the harness, not Gateway7.
Provider-hosted execution has the separate consent boundary below.

### Explicit opaque and hosted-tool consent

Both consent headers default to `false` and accept only one literal lowercase `true` or `false` value; duplicates, whitespace variants and other values return HTTP 400 before provider work.
They are snapshotted outside middleware-editable payloads and are never forwarded upstream or accepted as JSON consent fields.

| Header | What `true` acknowledges |
| --- | --- |
| `X-Gateway7-Allow-Opaque` | Exact typed encrypted reasoning, encrypted function-argument/result fields and inline image/audio fields may pass unchanged even though text policy cannot inspect their contents |
| `X-Gateway7-Allow-Hosted-Tools` | Advertised `web_search` and server-executed `tool_search` may execute at the provider before Gateway7 can check their returned records |

Opaque consent is required for encrypted reasoning history or output, `include: ["reasoning.encrypted_content"]`, inline media and the other exact opaque DTO fields.
Media is limited to validated inline base64 data URLs; Gateway7 does not fetch remote image/audio URLs or accept file references in their place.
Consented values are preserved byte-for-byte as strings, not decrypted, decoded for text policy or rewritten.
Adjacent plaintext, metadata, identifiers, schemas and decoded function arguments still undergo configured policy checks; naming an ordinary JSON key `encrypted_content` does not exempt it.
Without the relevant request consent, opaque or hosted input is rejected before provider work; unexpected unconsented provider output fails response validation.
Opaque consent does not grant hosted execution, and hosted consent does not grant opaque transport.
Hosted-tool consent acknowledges a real limitation: response policies can withhold a search record or answer, but cannot prevent or undo the provider-side search that already happened.
It is not a pre-execution approval guarantee for hosted tools or a general privacy-inspection guarantee for encrypted/media content.

### JSON results and checked native SSE

JSON responses retain native `object: response`, provider response ID/model, ordered `output` and terminal `status`, rather than Chat `choices` or a gateway-generated `chatcmpl-` identity.
Known usage fields and cache/reasoning details are retained only when reported; partial objects stay partial, and unknown usage is `null`, never fabricated zero counts.
This preservation can be broader than a particular SDK's strict response types; it is not a promise that every native variant passes every SDK release's strict decoder.

**Implemented response-only fields and token statistics.**
Validated nullable response echoes `max_tool_calls`, `prompt_cache_retention`, `safety_identifier`, `top_logprobs` and `user` are retained with omission/null fidelity; they do not become accepted request or history fields.
Response-only `output_text.logprobs` preserves omission, explicit `null`, `[]` and nonempty typed lists in final part/item/response snapshots, without widening the request/history content schema.
In the buffered path, retained free-form plaintext echoes and token strings/top-token alternatives undergo configured response-policy checks under the [native hook contract](plugins.md#native-responses-hooks).
Nonempty statistics protect both their records and associated text from unsafe edits: a blocking match or masking/redaction requiring such a change denies the turn rather than leaking stale token strings or inconsistent statistics.
Omitted, null or empty statistics do not by themselves disable leading-text early delivery; the existing item-0/part-0, prefix-window, annotation and metadata restrictions still apply.
Nonempty statistics remain withheld until strict final validation, without an early-token guarantee for every profile.
Separately, encoded SSE byte preflight is triggered by key presence for any of these five response echoes or `output_text.logprobs`, including null echoes and null/empty statistics; early completion counts already-sent bytes (`prior_bytes`) against the body limit.
Existing upstream whole-response bounds and checked SSE event/body byte checks are not relaxed for these fields or statistics.

For `stream: true` with the stream-mode header omitted or set to `buffered`, the gateway consumes bounded upstream native events and completes all response hooks before sending client headers.
The encoder then constructs checked events with native `event:` names, monotonic `sequence_number`, stable item references and snapshots consistent with the approved final output.
This is checked playback, not provider-fragment replay or generation-time delivery.
The native terminal event family is `response.completed`, `response.incomplete` or `response.failed`; it never uses Chat's `data: [DONE]` marker.
Incomplete responses retain their actual incomplete reason rather than being relabeled completed; an incomplete executable call is not released.
In this default checked mode, function/custom argument events and all output-item events are emitted only after strict final validation and response policy, not while executable arguments are still arriving.
The encoder can represent a checked failed native response with a sanitized error, but the production adapter currently maps upstream failed responses and stream errors to safe JSON HTTP 502 before delivery; do not rely on receiving a failed SSE event for every provider failure.
Response policy denial remains ordinary JSON HTTP 403 with no prior SSE content.
The upstream response and event limits remain 1 MiB and 64 KiB respectively.

### Canonical upstream response projection

Projection applies only to raw provider JSON responses and SSE `event.response` objects, exposing a canonical response subset rather than arbitrary upstream metadata passthrough.
Strict original-byte limits, UTF-8/JSON decoding, duplicate-key rejection, finite-number checks and whole-source JSON-type/depth validation precede projection, including branches later discarded.
The projection retains every present modelled response-root field and its value: supported identity, status, errors, ordered output/items, history correlation, function/custom tools, reasoning, consented opaque values and actual partial usage remain subject to existing validation and safe delivery rules.
Already-modelled echoes, including application `metadata` and the response-only fields above, are not discarded or normalized by projection; their omission/null/presence rules remain unchanged.
Unsupported administrative response-root echoes outside the canonical field set are omitted without a separate administrative-name allowlist; only root `reasoning` configuration receives a second projection.
That configuration retains existing `effort`, `summary` and nullable `context` under strict validation, preserving omission, `null`, `{}` and retained field values/presence.
Response-root `headers`, `end_turn` and `usage_metadata` are unsupported and rejected on presence, including `null`, `false` or empty values, never silently removed.
Unknown event-root keys/types, including the `response.headers` event, and unknown nested output/item/content/tool/reasoning-item fields remain rejected; reasoning output/encryption is not projected.
Discarded administration/moderation/billing metadata reaches neither clients nor diagnostics, and downstream metadata-dependent policies cannot inspect it or rely on its presence.
Clients receive only validated canonical objects and generated native events, never replayed raw upstream objects.
For supported `response.output_text.delta` events only, optional string `obfuscation` transport padding at the event root is discarded and never replayed; downstream events do not preserve upstream size-obfuscation padding.
Requests, history, direct response DTOs and nested semantic schemas remain strict; this is not arbitrary `extra="allow"`, generic unknown-field dropping, full OpenAI protocol compatibility or verified full native-packet/live/Codex success.

### Opt in to native early text

The landed app/parser/encoder/pipeline contract accepts exactly one `X-Gateway7-Stream-Mode: early` header with `stream: true`, the OpenAI provider and explicitly compatible request-only native hooks.
Production provider typed wiring is still being integrated; end-to-end early acceptance, gateway/container runs and live or paid verification are not established here.
The opaque and hosted-tool consents remain separate, immutable and default-denied; early mode grants neither consent and forwards no gateway control headers upstream.
Omitting the mode header or selecting `buffered` preserves full-response policy checks and ordinary JSON HTTP 403 denial without earlier content.

Every active middleware must provide the [native hooks](plugins.md#native-responses-hooks), including `prepare_early_responses`, and accept its request-only configuration.
Missing hooks/capabilities, a non-streaming request or an unsupported provider reject with HTTP 400 before provider work.
With hooks present, configured order still governs the first failure: a reached response-dependent hook refuses with HTTP 400, while an earlier request-hook `Deny()` returns HTTP 403 (`policy_denied`); both make zero provider calls.
The unchanged `config/openai.yaml` remains response-dependent, not an early-compatible configuration; do not remove its privacy policies to obtain earlier text.
Early mode does not run whole-response checking hooks, so use buffered mode whenever returned content requires those policies.

The public Python record API is defined in `gateway7/responses_events.py`: `ResponsesStreamHead`, `ResponsesTextDelta` and `ResponsesTextSink`.
`ResponsesStream.drain_text_deltas()` returns detached validated records carrying response identity, item ID, output/content indices, assistant phase, source sequence number, text and the parser's `leading_prefix` proof.
Native wire events retain their identities and indices with a monotonic delivery sequence; they are not a verbatim replay of provider event framing or source sequence numbers.

Only an uninterrupted leading assistant message at `output_index: 0`, with `output_text` at `content_index: 0`, is eligible for early text.
Any other item or part, held non-text metadata, or closure of the leading part permanently closes that prefix window; incomplete head metadata, annotation/logprob handling or window bounds can also cause holdback.
Otherwise supported reasoning-first, tool-first, refusal-first, interleaved and multiple-message profiles may therefore hold text until final validation.
Losing early eligibility does not reject, flatten or reindex those profiles: the full canonical output, order, IDs, phases and content positions are preserved.
Holdback does not re-enable whole-response policy hooks: the explicitly selected early mode remains request-only even when no prefix can be sent.
There is no first-token latency promise for every profile.

Only eligible assistant text and its native start framing may be released before terminal validation.
All executable tool payloads and tool-item events, refusal, reasoning and opaque-content events remain held until strict request-aware final validation; holding a hosted-tool record does not prevent consented upstream execution.
At completion, the encoder reconciles the already sent prefix with the canonical response, then emits its remaining text, held items and actual terminal state without replaying the prefix or inventing `completed`.
Before headers, errors retain ordinary JSON statuses; after a prefix, a late failure produces a sanitized native `response.failed` when delivery remains possible, or aborts on deadline/disconnect, without false `response.completed` or Chat `data: [DONE]`.
HTTP 200 cannot then be changed, and text already sent cannot be retracted.

The generic app streaming lifecycle awaits downstream sends for backpressure and owns the admitted job through deadline, disconnect and cancellation cleanup.
This reuses the existing lifecycle guards rather than promising higher throughput or unbounded production ahead of a slow client.
Codex invocation instructions remain pending a reviewed runner and actual gateway/container proof; component review is not production or harness acceptance.

### Send a bounded native request

Start the [OpenAI configuration](setup.md#openai-with-a-env-file), then supply its gateway client token to this optional client example:

```sh
curl --fail-with-body --silent --show-error http://127.0.0.1:8000/v1/responses \
  -H "Authorization: Bearer $GATEWAY7_CLIENT_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "model": "gpt-4.1-mini",
  "input": [{"role": "user", "content": [{"type": "input_text", "text": "Reply with pong"}]}],
  "max_output_tokens": 128,
  "store": false,
  "stream": false
}
JSON
```

The provider key stays on the server; the model must be available to that account and allowed for this client.
This can incur charges even on failure: choose and monitor a per-run request/token and spending budget, and do not interpret the per-request output cap as a run-wide billing limit.
Set `stream: true` for checked native SSE; no opaque or hosted consent is needed for this plaintext request.
Every active middleware must implement the [native hooks](plugins.md#native-responses-hooks); Chat-only/generated middleware is not silently skipped.
No live Codex installation, CLI profile or readiness claim is implied by this HTTP example.

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
It is returned in the `X-Request-ID` header on the application APIs and in error bodies.
Native `/chat` success bodies also include `request_id`; Chat Completions uses a `chatcmpl-` ID built from it, while Responses retains its provider response ID.

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
On both APIs, a `policy_denied` error also contains `error.middleware`, the server-configured instance that returned the denial, so the operator can identify the policy without exposing its terms or the message.
An outer middleware propagating the denial does not replace that instance name.
Authentication failures also include `WWW-Authenticate: Bearer`.

Gateway7 does not queue or automatically retry requests.
When all pipeline slots are occupied, `overloaded` is returned before middleware or a provider call.
The default limit is 64 active pipelines per process, shared by `/chat`, Chat Completions and Responses.

A failed answer may still have consumed provider tokens.
The gateway retains valid usage from a decoded successful provider HTTP response in its metrics, even if answer validation or response middleware later rejects delivery.
Before delivery starts, the client receives an error without answer text or usage fields.
With opt-in early text, a prefix may already have been delivered; the terminal error or abort does not retract it.
See [usage and failure metrics](observability.md#metric-contract) for diagnosis.

| Anonymous endpoint | Purpose |
| --- | --- |
| `GET /health` | Process liveness |
| `GET /ready` | Local startup/shutdown readiness; no provider request |
| `GET /metrics` | Prometheus metrics |

These endpoints do not require a client token and should stay within the trusted deployment network.
Readiness does not verify provider credentials or model access.
See [authentication](authentication.md) for client setup and [observability](observability.md) for provider failure reasons.
