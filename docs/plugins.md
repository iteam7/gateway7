# Writing a Gateway7 plugin

Gateway7 runs trusted Python plugins as async middleware.
In the default buffered path, each middleware can change the request, await the next handler, and change the returning response.
One ordered list defines both directions: `A -> B -> provider -> B -> A`.
The separate [early-stream preparation contract](#early-stream-preparation) admits only explicitly compatible request-only processing.
[DEC-016](decisions.md#dec-016) records this API migration; restart-based installation remains [DEC-010](decisions.md#dec-010).

Start with the [plugin generator and offline test runner](authoring.md) for an installable company package with synthetic fixtures.
The original two-file checkout example is checked by the demonstration below.

## Smallest installation

For a package you can deploy, follow [normal installation and the local HTTP walkthrough](authoring.md#install-normally-and-serve).
To inspect the original two-file course example, run from the repository root after [setup](setup.md):

```sh
uv run --locked python -m demo.run
```

The runner copies `examples/sample_plugin.py` to `company_plugins/sample.py` in a disposable folder and makes that folder importable.
It retains the synthetic provider and limits, and configures these instances:

```yaml
plugins:
  mask:
    module: gateway7.plugins.phone_mask
    enabled: true
    required: true
    settings: {}
  sample:
    module: company_plugins.sample
    enabled: true
    required: false
    settings:
      marker: "[checked-by-sample]"
middleware: [mask, sample]
```

After restarting its gateway, the runner checks that the forwarded user message and returned answer both end with `[checked-by-sample]`.
It verifies the [US-03](https://github.com/iteam7/gateway7/issues/32) / AC-01 two-file constraint inside that disposable folder; no core edit or package rebuild is needed.
Your checkout is unchanged.
This runner explicitly starts `demo.upstream`, a synthetic recorder with `/requests`; the interactive `gateway7 demo` uses a different private upstream with no recorder endpoint.
The [demo guide](demo.md) explains the checks and their safe traces.

## Descriptor and hooks

Each module exports `PLUGIN`, with `api_version=2`, a strict frozen Pydantic settings model, and a synchronous factory returning the middleware instance.
The descriptor `id` names the plugin type; YAML keys name configured instances.
An authenticated client's `additional_middleware` appends enabled configured instances to the global chain without replacing it; see [additional client policies](authentication.md#apply-additional-client-policies).
Instances share one lifecycle across chains, and per-request hook state remains separate.
Several instances can share one module with different settings.
The complete runnable example is [examples/sample_plugin.py](https://github.com/iteam7/gateway7/blob/main/examples/sample_plugin.py).

The instance implements this required async method for the buffered Chat path:

```python
async def handle(
    self, request: ChatRequest, context: PluginContext, call_next: NextHandler
) -> ChatResponse | Deny:
    response = await call_next(request)
    return response
```

| Value | Contract |
| --- | --- |
| `ChatRequest` | Ordered text/tool history, typed function definitions and validated generation settings |
| `ChatResponse` | Assistant text or typed function calls, normalized provider usage and finish reason |
| `PluginContext` | Core-owned request identifier, overall monotonic deadline, and mutable state isolated to this request and instance |
| `NextHandler` | Awaitable call accepting the next validated request and returning the downstream response |
| `Deny()` | Short-circuit with the core's safe `policy_denied` error |

To succeed, middleware must await `call_next(request)` exactly once and return a valid `ChatResponse`.
A request-side policy may return `Deny()` without forwarding; a response-side policy may also return `Deny()`, after provider work has occurred.
The next handler is valid only during its middleware invocation and in the same asyncio task.
Repeated, escaped or concurrent next calls are errors; a swallowed downstream failure cannot be turned into success.
The gateway validates payloads at boundaries, including values produced through Pydantic's unchecked `model_copy`.
The core preserves the provider's original usage and finish reason independently of middleware edits.
The authenticated model selection is pinned outside the plugin request contract and cannot be changed by middleware.

Optional async `startup()` and `shutdown()` manage instance resources.
Shutdown visits instances in reverse initialization order and still closes the provider when a plugin's cleanup raises an exception or `CancelledError`.
Each cleanup hook has the configured cooperative timeout; failures are logged without exception details.
Cleanup hooks run in an owned task and must not depend on the startup task's identity.
External cancellation waits for this cleanup and is then re-raised; if startup or the service body already failed, that original failure or cancellation takes precedence over cleanup interruptions.
Instances are shared across requests; immutable settings and concurrency-safe resources belong on the instance, and temporary mutable data belongs in `context.state`.

## Tool-payload capability

`PluginDescriptor` has an additive `supports_tools: bool = False` field; the middleware API remains version 2.
A text-only plugin can omit it and continues to work for ordinary chat.
On the Chat path, a request carrying tool definitions or tool history is rejected before the provider if any active middleware has not opted in.
The pipeline also rejects an unexpected tool response before returning it through an incapable plugin.

Set `supports_tools=True` only after the middleware handles nullable assistant content, `role: tool`, call/result IDs, function definitions and JSON arguments.
Preserve call IDs, function names and tool identity; validate any argument transformation structurally.
The core pins provider-owned usage and finish reason, and preserves only the middleware-approved response calls.
The stream transport preference, selected model and provider credentials remain outside plugin-visible payloads.

The reference phone, email and content-policy middleware opt in.
They inspect schema keys and string values in function parameters, descriptions and decoded argument objects.
For configured inspection phases, a mask/redact match in those structured fields denies the turn rather than corrupting JSON or changing an executable argument.
The content policy's `log` action continues to record only match metadata.
Ordinary message text and string tool-result content retain their existing masking/redaction behavior.
In the default buffered path, response checks finish before any text or executable call is released, including with upstream streaming.
Early delivery does not admit whole-response policies and still holds executable calls until final validation.

Generated company middleware remain text-only by default.
Extend the implementation and add synthetic tool fixtures before opting in; [the authoring guide](authoring.md#function-tool-fixtures) describes the added cases.

## Early-stream preparation

For OpenAI Chat Completions, a client can explicitly request `X-Gateway7-Stream-Mode: early` with `stream: true`.
Omitting the header, or selecting `buffered`, retains full-response middleware before client delivery.
The header accepts exactly one value, `buffered` or `early`; invalid or repeated values return HTTP 400.
Early mode with a nonstreaming request or an unsupported provider also returns HTTP 400 before provider work.
The mode is pinned outside plugin-editable payloads and is not forwarded upstream.

An instance may additionally implement:

```python
async def prepare_early_stream(
    self, request: ChatRequest, context: PluginContext
) -> ChatRequest | Deny:
    ...
```

This is an additive API v2 hook, not a new API version or a descriptor flag.
The loader validates the async signature; every active middleware must provide the hook.
It must perform the same request checks and transformations as the request portion of `handle`, then return a validated request or `Deny()`.
It receives no `call_next`, response or provider credentials.
The gateway runs preparation hooks in configured request order and invokes the provider only after every hook permits forwarding.
Tool payloads still require `supports_tools=True` and the existing structured checks.

Raise `EarlyStreamUnsupported` from `gateway7.plugin_api` when the configured instance requires any response processing.
The reference phone, email and content-policy plugins permit this hook only with `phase: request`; `response` and `both` are rejected.
The core does not infer third-party compatibility from a setting named `phase`.
A missing hook returns HTTP 400 with zero provider calls; an incompatible configuration does so when its preparation hook is reached.
A preparation hook returning `Deny()` retains HTTP 403 with zero provider calls, including when it precedes a later incompatible hook.
The gateway neither skips a policy nor silently falls back to buffering.

Only text from validated provider events can be released early; the complete response has not yet passed terminal validation.
Function-call IDs, names and arguments are withheld until the complete call and provider completion pass the normal structural and tool-choice checks.
Before SSE headers, failures retain their normal JSON error status.
After text delivery, a later failure cannot retract the prefix: the stream sends a safe top-level `error` event when delivery remains possible, or closes on timeout/disconnect, without a successful finish or `data: [DONE]`.
HTTP 200 alone therefore does not establish successful completion.

The early path awaits downstream sends before reading further provider fragments, so a slow client applies backpressure rather than growing a producer queue.
The existing body, provider, hook and overall deadlines remain in force; a pipeline slot stays occupied until its job and cancellation cleanup actually finish.
This contract describes early Chat delivery only; the separate native hook contract below does not establish general Codex compatibility.

## Native Responses hooks

`POST /v1/responses` uses separate native DTOs and optional API v2 hooks, not `handle`, `ChatRequest` conversion or the Chat `supports_tools` flag as a substitute for native support.
For JSON and default checked SSE, every active middleware must implement both preparation and response checking:

```python
from gateway7.plugin_api import Deny, ResponsesContext
from gateway7.responses_models import ResponsesRequest, ResponsesResponse


async def prepare_responses(
    self, request: ResponsesRequest, context: ResponsesContext
) -> ResponsesRequest | Deny:
    ...


async def check_responses(
    self, response: ResponsesResponse, context: ResponsesContext
) -> ResponsesResponse | Deny:
    ...


async def prepare_early_responses(
    self, request: ResponsesRequest, context: ResponsesContext
) -> ResponsesRequest | Deny:
    ...
```

These are instance-method signatures, not a complete policy implementation or instructions to return payloads unchecked.
`ResponsesContext` carries request ID, deadline, request/instance-local state and instance name, but no model-selection, header or consent authority.
The core preflights required hooks across the chain: a missing native hook rejects with HTTP 400 and zero provider attempts, rather than skipping an unknown plugin.
`prepare_responses` runs in configured order, followed by one provider attempt and `check_responses` in reverse order, before JSON serialization or checked native SSE delivery.
`Deny()` produces `policy_denied`; a request denial makes no provider call, while a response denial cannot undo the attempt or any consented provider-hosted tool execution.
Raise `ResponsesUnsupported` for a configuration the hook cannot safely process; a reached refusal returns HTTP 400, while an earlier request denial retains HTTP 403.

Native hooks may transform only approved free-text fields.
The core revalidates actual DTO state and protects array order, field presence, native IDs/call IDs, namespaces, types, controls, executable arguments/custom input, opaque values, usage and terminal metadata.
Matches requiring an ID, schema, structured argument, raw executable input or annotation-bearing text rewrite are denied rather than silently changing identity, corrupting JSON or shifting citation offsets.
The reference email, phone and content-policy hooks inspect all typed plaintext for their configured phases, including metadata, schema keys/values, reasoning summaries/text and decoded function arguments.
Only the exact typed encrypted/media fields are excluded from plaintext traversal; adjacent text and ordinary JSON keys with similar names remain inspected.
The [two independent consent headers](api.md#explicit-opaque-and-hosted-tool-consent) remain immutable outside plugin payloads and are never forwarded upstream.
Opaque content cannot be inspected by these text policies, and response policies are not a pre-execution guard for provider-hosted search.

`prepare_early_responses` is an additive request-only preparation signature; response-dependent configurations must raise `ResponsesUnsupported` rather than omit their response work.
Explicit native early mode requires `stream: true`, OpenAI, both buffered native hooks and `prepare_early_responses`; preparation uses the early hook in configured order and does not run whole-response checking hooks.
A missing required hook rejects before provider work; with hooks present, an earlier `Deny()` keeps HTTP 403 ahead of a later configuration refusal's HTTP 400.
The two consent grants remain immutable outside every hook and are not enlarged by early delivery.
The public typed delivery seam is `ResponsesTextSink` from `gateway7/responses_events.py`: an awaitable callback accepting one `ResponsesTextDelta`, not an unqualified Chat text callback.
Parser records preserve response/item identity, output/content indices, phase and source sequence, together with a permanent leading-prefix eligibility proof.
Only the assistant message/output-text part at output/content indices `0/0` can contribute an early prefix; once other items/parts, held non-text metadata or leading-part closure end that window, later text waits for final validation without changing the canonical profile.
Executable tools, refusal, reasoning and opaque events remain held until strict final validation; early preparation is not a substitute for response policy where that policy is required.
See the [native early API contract](api.md#opt-in-to-native-early-text) for eligibility, completion reconciliation and sanitized native failure behavior.
Production typed-provider wiring and end-to-end/container/live verification are not established by these component interfaces or by implementing a hook alone.
Native preparation and checking share each instance's cumulative own-work budget, while the overall deadline includes provider work; `context.state` is cleared on exit.

## Order, enable and required

In the buffered path, with `middleware: [mask, alpha, beta]`, request work runs mask, alpha, beta; response work returns beta, alpha, mask.
Changing the one list changes both directions.
The sample's markers make this visible: upstream sees `ping[A][B]`, and the answer ends with `[B][A]`.

| Configuration | Startup and execution |
| --- | --- |
| Unknown or duplicate middleware instance | Startup fails |
| Missing module, incompatible API, invalid settings or invalid `handle` | Startup fails with a safe instance diagnostic |
| Optional disabled instance | Descriptor/settings are still validated; no instance is created or invoked |
| Required instance | Must be enabled and present in the middleware list |
| Error in any active middleware | Stops processing, including optional middleware |

Request-side denial, exception or timeout prevents all later middleware and provider calls.
Response-side failure prevents delivery of the answer but cannot undo the provider call or its cost.
`required` protects configuration; it does not enable a fail-open error mode.

## Deadlines and diagnosis

`limits.request_timeout_seconds` bounds the complete request.
The retained setting `limits.hook_timeout_seconds` is each middleware's cumulative own-work budget: request preprocessing plus response postprocessing.
Time spent awaiting `call_next` is excluded from that budget, including the provider's time, but remains inside the overall deadline.
Early preparation has no response segment: each hook has its own-work timeout, while provider reads and downstream sends remain bounded by the overall deadline.
An expired timer invalidates a result even if middleware catches cancellation.

Execution events identify the request, middleware instance, direction, outcome and duration.
A start event without completion locates an in-flight step; the same request identifier connects the client response to the trace.
Gateway logs contain no prompt, answer, provider credential or arbitrary exception message.
The demonstration separately prints only its synthetic fixture transformations.

Deadlines are cooperative asyncio cancellation, not a hard kill of blocking Python code.
Installed modules remain trusted code sharing process memory, environment, files and network.
The public plugin arguments exclude provider credentials, but the process is not a sandbox.
[Task #84](https://github.com/iteam7/gateway7/issues/84) retains its Windows-specific repeated-run verification requirement.

## Migration from API version 1

Replace `api_version=1` with `api_version=2`, combine `on_request` and `on_response` into `handle`, and replace `Continue` with passing the request to `call_next` or returning the response.
Replace `chains.request` and `chains.response` with `middleware`.
Old descriptors and the old YAML shape fail startup rather than silently changing execution.
Independent response ordering is removed: review an existing response-only policy's position in the combined list.
Restart is required; this is a breaking plugin/configuration change within the pre-1.0 project.

## Trust, state and detector limits

Do not retain prompts or original values in instance fields, globals, restoration maps or logs.
The core discards request-owned state on completion without promising secure memory erasure.
There is no plugin-upload HTTP endpoint, hot loading, retry or plugin process isolation.

The phone middleware masks ASCII-digit numbers in the three fixture shapes throughout all roles and history: `+7 NNN NNN-NN-NN`, `8 (NNN) NNN-NN-NN`, and `+7NNNNNNNNNN`.
The replacement is `[PHONE]`, with no restoration.
The order/date fixture remains unchanged; this detector does not establish general PII coverage or an agreed production phone-format policy.
