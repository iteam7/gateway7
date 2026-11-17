# Build your first middleware

Start with a request guard, prove its behavior with synthetic fixtures, then try the same project over local HTTP.
The generated project contains its own contract and agent instructions; a Gateway7 core checkout is not needed to edit it.
This guide targets the unreleased Gateway7 `0.5.0.dev0`, middleware API **2**, project manifest **1** and fixture schema **2**.

## Generate a project

Activate the environment containing the reviewed Gateway7 wheel and `uv`.
For contributors starting from a Gateway7 checkout, run `uv sync --locked` there first and activate `.venv/bin/activate` on POSIX or `.venv\Scripts\Activate.ps1` in PowerShell.
Keep that environment active, then move to a separate authoring folder:

```sh
gateway7 plugin init company_guard --template guard --directory .
cd company_guard
gateway7 plugin inspect .
gateway7 plugin test .
uv pip install --group dev
ruff format --check .
ruff check .
mypy
python -m unittest discover -s tests -v
```

Expect inspection to describe the source plugin, **12/12 cases passed**, clean Ruff/strict mypy checks and **2 unit tests** passing.
`uv pip install --group dev` installs the generated tool group into the active environment without resolving or replacing the reviewed Gateway7 wheel.
Use `ruff format .` to repair formatting before repeating `--check`.
No provider account or real credential is needed.
`init` refuses to overwrite an existing target.
Names contain a lowercase initial letter followed by lowercase letters, digits or underscores, up to 48 characters; Python keywords and Windows device names are rejected.
The target's parent directory must already exist.

| Choose a template | Policy | Positive fixture profiles |
| --- | --- | --- |
| `--template guard` | Reject a request containing `PRIVATE-TEST` before a provider call | Chat, typed Chat tools, native Responses, early Chat and early Responses |
| `--template redact` (default) | Replace `PRIVATE-TEST` with `[removed]` in requests and complete responses | Chat, typed Chat tools and native Responses |

The redactor generates **10 cases**, including explicit early-mode refusals.
A negative test proves refusal, not early-stream support.
The request guard does not filter model answers.

| File | Purpose |
| --- | --- |
| `gateway7_plugin_company_guard/plugin.py` | Frozen settings, a pure text transform and the API-2 descriptor |
| `gateway.yaml` | Plugin settings and middleware chain |
| `fixtures.json` | Synthetic behavior and per-profile expectations |
| `tests/test_policy.py` | Small editable unit checks |
| `pyproject.toml` | Installable package and `[tool.gateway7.plugin]` metadata |
| `CONTRACT.md`, `AGENTS.md`, `README.md` | Versioned local contract, agent workflow and commands |

The project metadata selects the module, YAML, fixtures and declared profiles:

```toml
[tool.gateway7.plugin]
schema_version = 1
module = "gateway7_plugin_company_guard.plugin"
config = "gateway.yaml"
fixtures = "fixtures.json"
profiles = ["chat", "chat-tools", "responses", "chat-early", "responses-early"]
```

Config and fixture paths are relative to the project root and confined to it.
`test`, `inspect` and `dev` accept a project directory and default to the current directory.
The selected module must be enabled in the global middleware chain.
These authoring commands explicitly use that project's source; ordinary `validate` and `serve` require an installed package.
There is no generated lockfile: run these commands in the active Gateway7 environment rather than assuming `uv run --locked` applies to the generated project.

## Change one rule

In `plugin.py`, `create()` returns the public `TextPolicyMiddleware` helper.
Its synchronous transform returns `(replacement_text, hit_count)`.
The helper owns typed request/response traversal, protected-field checks and profile hooks; see the [helper reference](plugins.md#simple-text-policies).
For a request guard, zero hits allow the request and positive hits deny it:

```python
def create(settings: Settings) -> TextPolicyMiddleware:
    def transform(text: str) -> tuple[str, int]:
        hits = text.count(settings.term)
        return text, hits

    return TextPolicyMiddleware(transform, phase="request", action="block")
```

Add a failing synthetic fixture before changing the transform.
The [agent guide](plugin-agent-guide.md#make-a-red-then-green-change) gives an executable example that adds `SYNTHETIC-BLOCK`, observes exit 1, edits this function and observes exit 0.
Keep the original cases passing and run the unit tests again.
Use the [cookbook](plugin-cookbook.md) for two-way redaction, typed tools, native payloads and early streams.

## Try local HTTP

From the project directory:

```sh
gateway7 plugin dev . --port 0
```

The command starts one owned child containing a gateway and a synthetic upstream, each bound to `127.0.0.1` on an automatically allocated port.
It prints both URLs and a ready-to-run client command for your platform.
Copy the printed command into another terminal with the same Gateway7 environment active.
A benign message returns HTTP 200 with `pong — Hello synthetic`.
Change its message to `PRIVATE-TEST`: the guard returns HTTP 403, while the redactor returns `pong — [removed]`.
The printed token is generated synthetic data for this run only.
Press Ctrl-C in the server terminal to stop both listeners and reap the child.

`dev` runs the actual gateway HTTP parser, middleware pipeline and provider adapter against an owned local fixture.
It supports synthetic text, typed tools, native Responses and their selected streaming paths; the fixture is not a real model or a certification of all upstream profiles.
Use the fixture matrix for explicit profile evidence.
Each run reads current project source, without auto-reloading edits; restart it after changing code.
The command replaces provider credentials, client access and any management storage configuration in memory, disables inherited telemetry/transports, and leaves project files unchanged.
The worker receives a small environment without parent API keys.
This is trusted Python execution with local sockets, not a sandbox for hostile plugin code.

If startup fails, first run `plugin inspect .` and `plugin test .`.
Allow loopback sockets in the execution environment and use `--port 0` if a chosen port is occupied.
A plugin startup hook can still fail or exceed the bounded startup wait.

## Read expected and actual results

```sh
gateway7 plugin inspect . --json
gateway7 plugin test . --json --timeout 60
```

Inspection reports the module source, Gateway7/API versions, strict settings schema, available hooks, tool declaration and declared profiles.
It imports the trusted descriptor and constructs factories but makes no provider call and runs no startup hook.
Its `behavior_verified` field is false, and its `tested_profiles` list is empty.
Run fixtures to obtain behavior evidence.

Test report schema 2 contains `passed`, `total`, `failed`, `cases`, `issues`, a profile matrix and `capabilities`.
Each case compares expected/actual provider calls, forwarded request, final response or safe error, and early deltas where relevant.
A positive passing case with an actual provider call contributes to `tested_profiles`.
For early profiles, the case must also emit validated deltas before completion; successful empty-prefix preparation is checked separately and does not prove early emission.
A failed case, denial-only test or unsupported-mode refusal does not certify a profile.
Review the complete per-profile matrix before advertising support.
Errors identify a safe stage/code/path, relevant source location when available, and a corrective hint; they do not echo arbitrary import exceptions or settings values.
Reports include fixture text, so use synthetic values only.

| Exit | Meaning |
| --- | --- |
| `0` | All cases pass; inspection succeeds; or `dev` stops orderly after Ctrl-C |
| `1` | A fixture's expected and actual behavior differ |
| `2` | Invalid project, invalid fixture, unsupported contract, worker failure, interruption or timeout |

## Fixture schema

Keep the suite selected by `fixtures` in the project manifest.
This is a complete one-case guard suite:

```json
{
  "schema_version": 2,
  "cases": [
    {
      "name": "block synthetic request",
      "profile": "chat",
      "request": {"messages": [{"role": "user", "content": "PRIVATE-TEST"}]},
      "provider_response": {"text": "Must never be requested"},
      "expected": {"provider_calls": 0, "error": "policy_denied"}
    }
  ]
}
```

A case names its profile: `chat`, `chat-tools`, `responses`, `chat-early` or `responses-early`.
The request and provider response use that profile's actual public DTO shape.
Copy the corresponding generated case before extending it; native Responses are not flattened into Chat.
`expected.request` checks the request after middleware; `expected.response` checks the complete answer after middleware.
A case expects either a response or a safe error with 0 or 1 provider calls.
Early cases also supply typed `provider_deltas` and expected `deltas`.
Use `provider_error: true` for an upstream failure.
Unknown fields, duplicate JSON keys, duplicate case names and invalid nested DTOs are rejected.
Case names start with an ASCII letter and contain at most 128 letters, digits, spaces, dots, underscores or hyphens.
A suite supports 1–64 cases in a file up to 1 MiB; reports are capped at 4 MiB.
An optional suite `concurrency` value from 1–8 checks shared-instance behavior with one plugin lifecycle.
The whole-suite timeout defaults to 30 seconds; `--timeout` accepts 1–300 seconds.
Configured hook/request timeouts also apply.

## Function-tool fixtures

Both starters use the shared helper and explicitly declare `supports_tools=True`.
Their fixtures cover call-only answers, typed history, identity/usage preservation and sensitive protected fields.
Extend them for your policy's definitions, arguments and tool results.
A match in protected executable arguments or tool identity must be denied, not silently rewritten.
The declaration alone provides no compatibility evidence; keep positive and negative typed cases.
See [tool payload capability](plugins.md#tool-payload-capability) for the lower-level contract.

## Early-stream authoring

Use the request-only guard when you need early delivery.
The helper's `phase="request"` prepares the checked request before a provider call.
Two-way or response-dependent policies reject early mode before provider work, because unchecked answer text cannot be released safely.
Keep both early profiles in the manifest only after their positive cases pass, alongside no-call denial and terminal delta checks.
See [early-stream preparation](plugins.md#early-stream-preparation).

## Native Responses authoring

The generated `responses` cases exercise native request/check hooks and typed `ResponsesRequest`/`ResponsesResponse` values.
Preserve item/call IDs, ordering, statuses, tool structure, consent and original provider usage.
For `responses-early`, the guard's preparation hook is tested separately from the completed native response.
These fixture and local HTTP checks do not establish full Responses or live Codex compatibility.
See [native hooks](plugins.md#native-responses-hooks).

## Install normally and serve

After the fixtures and unit checks pass, build the plugin wheel:

```sh
uv build --wheel
uv pip install --no-deps dist/gateway7_plugin_company_guard-0.1.0-py3-none-any.whl
gateway7 validate --config gateway.yaml
```

Install into the same environment as the reviewed Gateway7 build.
Building may download build dependencies; synthetic fixture execution itself needs no provider or network.
The generated package requires `gateway7>=0.5.0.dev0,<0.6`; middleware API compatibility is checked independently at load time.
Validate from a different working directory using an absolute configuration path to verify normal installed loading.
The authoring worker never falls back to a stale installed copy if project source is missing.

### Try the installed package without a provider account

`plugin dev` deliberately uses current source.
For a final distribution check, install the wheel into a clean Gateway7 environment and use a separate authenticated synthetic-provider configuration with ordinary `serve`.
The installed-wheel smoke in CI performs this step after hiding the project package and verifies HTTP policy behavior, then stops both services.
It also demonstrates that a later local source edit affects `dev` while the previously installed wheel keeps its own behavior.

### Use a real provider or update the plugin

For deployment, copy the reviewed provider/auth/limits sections from [provider setup](setup.md#real-providers), keeping the plugin and chain sections.
Supply credentials through the normal private startup path, validate, and restart the gateway with the installed package.
For development, an explicit `uv pip install --no-deps -e .` is possible; repeat the final wheel check before shipping.
After a normal package update, reinstall the new wheel and restart serving processes.
No production import path is changed automatically by `test`, `inspect` or `dev`.

## Offline execution boundary

The fixture worker removes inherited credentials, uses a synthetic provider and blocks Python networking and subprocess APIs.
It starts/shuts down the configured plugin suite once and applies bounded suite/case timeouts.
Inspection uses the same explicit source boundary without running startup hooks.
These guards help prevent accidental external calls; they are not OS isolation against malicious Python, native extensions or resource exhaustion.
Review plugin code before importing it, and keep prompts, answers and real keys out of fixtures and reports.

## Update an earlier authoring project

The `0.5.0.dev0` authoring contract requires project manifest 1 and fixture schema 2.
Generate a fresh starter, move your reviewed pure policy and synthetic cases into it, select the actual profiles, then rerun inspect, fixtures, units and the wheel check.
The earlier `plugin test --config ... --fixtures ...` form and schema-1 fixture files are unsupported.
Middleware API 2 and provider transport API 1 are unchanged.
