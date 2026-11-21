# Plugin cookbook

Start with the [first middleware guide](authoring.md), then choose the smallest policy that fits the task.
Each recipe edits the generated package through public APIs and keeps its synthetic fixture matrix as evidence.
Read the local `CONTRACT.md` for the exact Gateway7 version before changing it.

## Reject one request marker

Generate a request guard:

```sh
gateway7 plugin init company_guard --template guard
cd company_guard
gateway7 plugin test .
```

Set `plugins.sample.settings.term` in `gateway.yaml` to a synthetic marker such as `SYNTHETIC-SECRET`.
Change the corresponding fixture inputs and keep an ordinary request as a positive case.
The transform returns the unchanged text and a positive hit count when the marker appears.
`phase="request", action="block"` denies before provider work; a request denial must expect `provider_calls: 0`.
Do not claim that this guard filters the response.

## Redact requests and complete answers

Generate a separate `--template redact` project.
Its transform returns replaced text and the number of matches:

```python
def transform(text: str) -> tuple[str, int]:
    return text.replace(settings.term, settings.replacement), text.count(settings.term)
```

The factory returns `TextPolicyMiddleware(transform, phase="both", action="redact")`.
Keep fixtures for every history role, benign text, answer-only matches, original provider usage and protected tool fields.
Avoid storing input or output in an instance attribute; the same middleware can serve concurrent clients.
An empty replacement, regex policy or domain-specific identifier needs its own strict settings validation and synthetic boundary cases.
The helper validates transformed text before delivery.

## Extend a typed tool policy

Copy a generated `chat-tools` case rather than replacing calls with plain text.
Include an assistant call with a stable `id`, function name and JSON argument string, then a `role: tool` message with the matching `tool_call_id`.
Check both an unchanged benign call and a sensitive value in the definition, arguments or tool result.
The helper denies matches that would require rewriting protected executable arguments or identity.
Preserve call IDs, function names, original usage and the `tool_calls` finish reason.
The middleware approves or denies data; it never executes the function.
A `supports_tools=True` declaration without positive typed fixtures is insufficient evidence.

## Keep native Responses native

Copy the generated `responses` case, including its typed response output, IDs and usage.
Use native hooks through the helper rather than converting a native request into Chat history.
Assert unchanged ordered output and function-call identity alongside your text transformation or denial.
Opaque/hosted-tool consent and protected fields stay gateway-owned.
A Chat-only test does not verify native behavior.
See the [native hook contract](plugins.md#native-responses-hooks) when a policy needs functionality outside the text helper.

## Enable early text only for request policies

Use `--template guard`; its declared `chat-early` and `responses-early` cases exercise typed deltas and final usage.
Add one positive allowed stream and one marker denial with zero provider calls.
Keep terminal markers and typed delta ordering in expectations.
Response-phase redaction must retain the starter's early-mode rejection before provider work.
Do not implement a no-op early hook to bypass an answer policy.
The [early-stream contract](plugins.md#early-stream-preparation) describes cancellation and protected tool delivery.

## Diagnose a failed check

```sh
gateway7 plugin inspect . --json
gateway7 plugin test . --json
uv pip install --group dev
ruff format --check .
ruff check .
mypy
python -m unittest discover -s tests -v
```

| Symptom | Next action |
| --- | --- |
| Project metadata/path diagnostic | Check `[tool.gateway7.plugin]` and keep selected files within the project |
| Module inactive in the chain | Enable the declared module and include its instance in global `middleware` |
| Factory or settings diagnostic | Read its safe code/path/hint; fix strict settings or the synchronous factory signature |
| Expected/actual mismatch, exit 1 | Locate that case, check provider-call count first, then forwarded and final typed values |
| Hook exists but profile is `not_tested` | Add a positive case for that actual profile |
| Profile has only denial cases | Keep the denial checks and add a permitted provider-backed fixture case |
| Worker timeout | Check bounded startup/hook behavior; increasing the suite timeout does not repair an infinite hook |
| Dev cannot bind | Allow local sockets or use `--port 0`; rerun inspect/test before retrying |

Use only synthetic input: fixture JSON reports contain expected and actual values.
An arbitrary plugin exception is intentionally summarized rather than echoed with possible private settings.

## Package a reviewed result

Run the entire matrix and unit suite, build a wheel, and install it into the target Gateway7 environment.
For a quick current-source HTTP check use `gateway7 plugin dev .`; for distribution evidence use ordinary `validate`/`serve` from a different directory with the wheel installed.
The source-only authoring commands must not be used as proof that a package was shipped.
Record the Gateway7 version, plugin version and positive tested profiles in the review.
Keep real-provider checks separate from the credential-free authoring loop and obtain the intended deployment credentials through [setup](setup.md#supply-server-credentials).
