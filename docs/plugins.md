# Writing a Gateway7 plugin

Gateway7 loads trusted Python modules at startup through `importlib`.
Installation changes a module file and YAML configuration; restart the process to apply it.
This is the concrete extension mechanism selected with [DEC-013](decisions.md#dec-013) and the restart boundary in [DEC-010](decisions.md#dec-010).
The core contains no phone-number policy.

## Smallest installation

Run these commands from the repository root after [setup](setup.md):

```sh
mkdir -p company_plugins
cp examples/sample_plugin.py company_plugins/sample.py
```

Python discovers `company_plugins` as a namespace package from the working directory; no `__init__.py` or core edit is needed.
Keep the existing provider, limits and phone plugin in `config/demo.yaml`, then add this instance under `plugins` and append its name to `chains.request`:

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
chains:
  request: [mask, sample]
  response: []
```

Stop and restart Gateway7 with the same config path.
Send a user message to `/chat` and inspect the fake upstream's `/requests` record: the user message ends with `[checked-by-sample]`.
For [US-03](https://github.com/iteam7/gateway7/issues/32) / AC-01, `git status --short` should show only `company_plugins/sample.py` (or its untracked parent directory) and `config/demo.yaml`.
Use `git status --short --untracked-files=all` to show the file itself.
The repeatable [demo](demo.md) uses a disposable directory and checks the changed file set without modifying your checkout.

## Descriptor and hooks

Each module exports one `PLUGIN`, defined with `gateway7.plugin_api.PluginDescriptor`:

```python
PLUGIN = PluginDescriptor(
    id="sample",
    api_version=1,
    settings_model=Settings,
    create=create,
)
```

`id` is the module's stable **plugin type**, such as `sample`.
The YAML map key is a configured **instance**, such as `sample_a`; chains refer to instance names.
Several instances may use the same type/module with different validated settings.
`Settings` is a Pydantic model with `strict=True`, `extra="forbid"` and `frozen=True`; `create(settings)` constructs an instance.

An instance may implement either or both async hooks:

```python
async def on_request(self, request, context):
    return Continue(payload=request)

async def on_response(self, response, context):
    return Continue(payload=response)
```

| Value | Contract |
| --- | --- |
| `ChatRequest` | `messages`: ordered plain-text `Message` objects with role `system`, `user` or `assistant`; `max_tokens`: integer, default 256, from 1 to 4096 |
| `ChatResponse` | `text`: assistant text; `usage`: normalized integer counts when known, otherwise `None` |
| `PluginContext` | Core-owned `request_id`, monotonic `deadline`, and a mutable `state` dictionary scoped to this request and this configured instance |
| `Continue(payload)` | Pass a valid request/response of the correct phase to the next hook |
| `Deny(code="policy_denied")` | Stop with a safe policy error; never use exception or denial text to send input back to callers |

The runner validates hook results again: Pydantic's `model_copy(update=...)` alone does not validate an update.
An exception, malformed result or expired deadline stops the operation; request-hook failures cause zero upstream calls.
Response-hook rejection happens after provider work and cannot undo its cost.
Optional async `startup()` and `shutdown()` methods manage instance resources, not per-request data.

## Order, enable and required

Request and response order are independent.
For the same sample module configured as instances A and B, request order `[A, B]` appends `[A][B]`; response order `[B, A]` appends `[B][A]` to the deterministic answer.
There is no implicit reverse order, retry or parallel hook execution within a request.

| Configuration | Startup and execution |
| --- | --- |
| Unknown instance or duplicate entry in a chain | Startup fails |
| Missing module, incompatible descriptor or invalid settings | Startup fails and names the instance, including when it is disabled |
| Enabled instance referenced in a phase without that hook | Startup fails |
| Optional instance with `enabled: false` | Its declared module/descriptor/settings are still checked; it is not created or run and is filtered from the effective chains |
| `required: true` | Cannot be disabled; must appear in each chain for which it implements a hook |
| Failure of any active hook | Fail closed, whether or not `required` was set |

`required` protects configuration against accidentally removing a mandatory filter.
It does not introduce a fail-open error mode for optional plugins.
A missing disabled module is still an error because [US-03](https://github.com/iteam7/gateway7/issues/32) / AC-02 requires a named configured plugin to exist.

## Trust, state and detector limits

Installed plugins execute inside the gateway process.
The ordinary hook contract does not contain the provider key, but this is **not a sandbox**: Python code can read the environment, memory, files and network.
Only deploy reviewed company code and configuration; there is no plugin-upload HTTP endpoint.

Instances are shared across requests.
Keep settings immutable and shared service resources concurrency-safe; put temporary counters and similar values in `context.state`.
Do not retain raw prompts or original values in instance fields, globals, restoration maps or logs.
The core discards request-owned state at completion; it does not promise secure memory erasure.

Deadlines use cooperative asyncio cancellation.
Write bounded async work and propagate cancellation; blocking CPU work or code suppressing cancellation can stall the whole service.
There is no hard kill, process isolation or guarantee that a cancelled provider call stopped upstream.

The bundled phone plugin masks ASCII-digit numbers in exactly these shapes throughout all message roles and history: `+7 NNN NNN-NN-NN`, `8 (NNN) NNN-NN-NN`, and `+7NNNNNNNNNN`.
The replacement is always `[PHONE]`; there is no restoration feature.
Word boundaries reduce matches inside identifiers, and the order/date fixture is preserved.
This narrow detector demonstrates the existing acceptance fixtures; it does not establish general PII coverage or an agreed production phone-format policy.
