# Generate, test and install a middleware

Build a small Python package, check its behavior with synthetic data, then install it in the gateway environment.
The generated example replaces `PRIVATE-TEST` with `[removed]` in request history and in the answer.
No provider account is needed for the offline tests or local HTTP walkthrough.

## Generate a project

Use the current Gateway7 checkout or an installed wheel from that checkout.
If you are starting in the repository, prepare and activate its environment:

```sh
uv sync --locked
. .venv/bin/activate
```

These examples use a POSIX shell; in PowerShell, activate with `.venv\Scripts\Activate.ps1`.
If you already use an installed wheel, activate that environment instead.
Keep the same environment active for the following steps.
Run them in the folder where you want the new package:

```sh
gateway7 plugin init company_mask --directory .
gateway7 plugin test --config company_mask/gateway.yaml --fixtures company_mask/fixtures.json
```

Expect **2/2 cases passed** and exit code 0.
The command refuses an existing target; choose a new name if `company_mask` already exists.
Names start with a lowercase letter and contain only lowercase letters, digits or underscores, up to 48 characters.
Python keywords and reserved Windows device names are rejected.

| File inside `company_mask/` | What to edit |
| --- | --- |
| `gateway7_plugin_company_mask/plugin.py` | Middleware behavior and settings |
| `gateway.yaml` | Plugin settings and chain order |
| `fixtures.json` | Synthetic inputs and expected results |
| `pyproject.toml` | Package metadata and dependencies |
| `README.md` | Commands for this generated project |

The offline worker can load it beside `gateway.yaml` before installation.
`validate` and `serve` need the package installed; they do not load it from the current folder.

## Read expected and actual results

For a JSON report, add `--json`:

```sh
gateway7 plugin test --config company_mask/gateway.yaml --fixtures company_mask/fixtures.json --json
```

The report compares provider-call count, the request sent to the fixture provider, the final response and any error.
It includes `passed`, `total`, `failed` and `cases`, with expected and actual values for each check.

| Exit code | Meaning |
| --- | --- |
| 0 | All cases pass |
| 1 | At least one expected result differs from the actual result |
| 2 | Invalid setup, worker failure, interruption or timeout |

Try a failing expectation in a copy of the file:

```sh
python - <<'PY'
import json
from pathlib import Path
path = Path("company_mask/fixtures.json")
data = json.loads(path.read_text())
data["cases"][0]["expected"]["response"]["text"] = "Deliberately wrong"
path.with_name("fixtures-fail.json").write_text(json.dumps(data))
PY
gateway7 plugin test --config company_mask/gateway.yaml --fixtures company_mask/fixtures-fail.json
```

Expect one failed case, exit code 1, and actual text `Answer [removed]` beside the wrong expectation.
Keep the original passing fixtures.
Reports print fixture text, so use synthetic data only.

## Fixture schema

Save this complete example as `company_mask/fixtures-small.json`:

```json
{
  "schema_version": 1,
  "cases": [
    {
      "name": "mask both directions",
      "request": {
        "messages": [{"role": "user", "content": "PRIVATE-TEST"}]
      },
      "provider_response": {"text": "Answer PRIVATE-TEST"},
      "expected": {
        "provider_calls": 1,
        "request": {
          "messages": [{"role": "user", "content": "[removed]"}]
        },
        "response": {"text": "Answer [removed]"}
      }
    }
  ]
}
```

```sh
gateway7 plugin test --config company_mask/gateway.yaml --fixtures company_mask/fixtures-small.json
```

Expect **1/1 cases passed**.
`expected.request` is the text after request middleware; `expected.response` is the answer after response middleware.
Add `usage` to a provider response and expected response when you want to check token-usage preservation.
The generated larger suite also covers all history roles and unchanged benign text.

For a request block, use `"expected": {"provider_calls": 0, "error": "policy_denied"}`.
For a response block, expect one provider call and the same error.
A case must expect either a response or a safe error code, with 0 or 1 provider calls.
Set `provider_error: true` to simulate an upstream failure.
Unknown fields, duplicate JSON keys and duplicate case names are rejected.

A suite supports 1–64 cases in a file up to 1 MiB; reports are capped at 4 MiB.
The whole-suite timeout is 30 seconds by default; `--timeout` accepts 1–300 seconds.
The configured middleware and request timeouts also apply to each case.

## Function-tool fixtures

The generated middleware declares no tool capability and remains usable for ordinary text chat.
Adding `supports_tools=True` to `PLUGIN` is an explicit promise to inspect and preserve the extended [tool payload contract](plugins.md#tool-payload-capability).
The flag alone does not make a text-only implementation safe.

Before opting in, add offline cases covering a call-only `ChatResponse` with empty `text`, one typed `tool_calls` entry and `finish_reason: tool_calls`.
Include nullable assistant history followed by a string `role: tool` result with the matching `tool_call_id`, allowed argument JSON, and a denial for synthetic sensitive data in arguments or definition text.
Verify that call IDs and function names survive unchanged, that invalid argument edits fail validation, and that provider usage remains original when a response is denied or transformed.
Use only synthetic paths, arguments and tool results: offline reports include fixture values.

Upstream streaming changes provider transport, while middleware still receives the complete normalized response.
Do not yield partial unchecked text or execute functions from a plugin; the harness owns execution after the gateway approves the call.

## Install normally and serve

Install into the active Gateway7 environment with [uv](https://docs.astral.sh/uv/):

```sh
uv pip install --no-deps ./company_mask
gateway7 validate --config company_mask/gateway.yaml
```

Expect `Configuration valid: provider=fake; middleware=1`.
The server now loads the installed package from any folder.
`--no-deps` keeps the current Gateway7 build; it must already be installed in this environment.
The loader checks plugin API v2 when it loads the package.
Package installation may download build requirements; only `plugin test` is an offline check.

### Try the installed package without a provider account

Use three terminals with the same Gateway7 environment active, in the folder containing `company_mask`.
Ports 18000 and 18001 must be free.
Create a separate local config, keeping the generated plugin and original fixtures:

```sh
python - <<'PY'
from pathlib import Path
import yaml

source = Path("company_mask/gateway.yaml")
config = yaml.safe_load(source.read_text())
config["provider"].update(
    base_url="http://127.0.0.1:18001", key_env="GATEWAY7_DEMO_KEY"
)
config["auth"] = {
    "enabled": True,
    "clients": {
        "demo": {"token_env": "GATEWAY7_AUTHORING_TOKEN", "models": ["fake"]}
    },
}
with source.with_name("gateway-local.yaml").open("x") as output:
    yaml.safe_dump(config, output, sort_keys=False)
PY
```

This refuses to overwrite an existing `gateway-local.yaml`; reuse that file when restarting.
In the first terminal, start the packaged echo fixture on loopback:

```sh
GATEWAY7_DEMO_KEY=gateway7-synthetic-authoring-upstream \
  python -m uvicorn gateway7.demo:app --host 127.0.0.1 --port 18001 --no-access-log
```

In the second terminal, validate and start the gateway with the installed plugin:

```sh
gateway7 validate --config company_mask/gateway-local.yaml
GATEWAY7_DEMO_KEY=gateway7-synthetic-authoring-upstream \
GATEWAY7_AUTHORING_TOKEN=gateway7-synthetic-authoring-client \
  gateway7 serve --config company_mask/gateway-local.yaml --host 127.0.0.1 --port 18000
```

Wait for both servers to print `Uvicorn running on`, then send a request in the third terminal:

```sh
GATEWAY7_TOKEN=gateway7-synthetic-authoring-client \
  gateway7 chat --url http://127.0.0.1:18000 --model fake --message 'PRIVATE-TEST'
```

Expect:

```json
{"text": "pong — [removed]", "usage": {"input_tokens": 12, "output_tokens": 4}}
```

The echo confirms that the installed middleware changed the request before the provider received it.
The two-way offline fixture separately checks response filtering.
These credentials and token counts are public synthetic values; neither process calls a real provider or records request text.
After success or any error, stop both server terminals with Ctrl-C; the command-scoped credentials do not remain in the shell environment.

### Use a real provider or update the plugin

For a real model, copy the `provider`, `auth` and `limits` sections from [provider setup](setup.md#real-providers) into `company_mask/gateway.yaml`, keeping its `plugins` and `middleware` sections.
Supply the server credentials, validate the file, then run `gateway7 serve --config company_mask/gateway.yaml`.
Use the [API guide](api.md) for an authenticated client request.
The original generated fake-provider YAML is for fixtures; `serve` does not start an upstream for you.

After a code change, rerun the fixtures, reinstall the package, and restart the server:

```sh
gateway7 plugin test --config company_mask/gateway.yaml --fixtures company_mask/fixtures.json
uv pip install --reinstall --no-deps ./company_mask
```

Stop the running gateway with Ctrl+C, then run the same `serve` command again.
Settings changes also need a restart; there is no hot loading.
An exact dependency sync may remove extra company packages, so include their installation in your deployment steps.

## Offline execution boundary

The worker always uses the supplied fixture answer, even if the YAML selects a real provider.
It does not import or initialize a configured [provider transport](provider-transports.md#offline-middleware-tests).
It reads no provider key or client token and starts with a small operating-system environment.
It blocks Python socket and subprocess calls before loading the plugin, discards plugin stdout/stderr, and stops on the suite timeout or interruption.

This catches accidental network access; it is not a security sandbox for hostile Python or native code.
Only test and install trusted plugins.
`validate` and `serve` load that code with the gateway's normal environment and permissions.
Keep original text and credentials out of logs and shared instance state.
For implementation details, use the [middleware API reference](plugins.md#descriptor-and-hooks).
