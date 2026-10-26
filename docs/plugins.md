# Writing a Gateway7 plugin

Gateway7 runs trusted Python plugins as async middleware.
Each middleware can change the request, await the next handler, and change the returning response.
One ordered list defines both directions: `A -> B -> provider -> B -> A`.
[DEC-016](decisions.md#dec-016) records this API migration; restart-based installation remains [DEC-010](decisions.md#dec-010).

Start with the [plugin generator and offline test runner](authoring.md) for an installable company package with synthetic fixtures.
The two-file checkout example below remains available for the original course demonstration.

## Smallest installation

From the repository root after [setup](setup.md):

```sh
mkdir -p company_plugins
cp examples/sample_plugin.py company_plugins/sample.py
```

Python discovers `company_plugins` as a namespace package from the working directory.
Keep the provider and limits in `config/demo.yaml`, and use these instances and middleware list:

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

Restart with the same config path, send a user message to `/chat`, and inspect the fake provider's `/requests` record.
The forwarded user message and the returned answer both end with `[checked-by-sample]`.
No core edit or package rebuild is needed.
For [US-03](https://github.com/iteam7/gateway7/issues/32) / AC-01, inspect `git status --short --untracked-files=all`: only the new module and configuration should change.
The [demo](demo.md) checks that two-file installation in a disposable directory.

## Descriptor and hooks

Each module exports `PLUGIN`, with `api_version=2`, a strict frozen Pydantic settings model, and a synchronous factory returning the middleware instance.
The descriptor `id` names the plugin type; YAML keys name configured instances.
Several instances can share one module with different settings.
The complete runnable example is [examples/sample_plugin.py](https://github.com/iteam7/gateway7/blob/main/examples/sample_plugin.py).

The instance implements one async method:

```python
async def handle(
    self, request: ChatRequest, context: PluginContext, call_next: NextHandler
) -> ChatResponse | Deny:
    response = await call_next(request)
    return response
```

| Value | Contract |
| --- | --- |
| `ChatRequest` | Ordered plain-text messages and validated generation settings |
| `ChatResponse` | Assistant text, normalized provider usage when known, and a normalized finish reason |
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

## Order, enable and required

With `middleware: [mask, alpha, beta]`, request work runs mask, alpha, beta; response work returns beta, alpha, mask.
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
