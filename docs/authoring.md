# Generate, test and install a middleware

The CLI creates a company-owned Python package and tests it through the real middleware runner before any provider account is needed.
The generated implementation replaces the literal `PRIVATE-TEST` with `[removed]` in all request-history messages and in the returned answer.
It is a starting point with an explicit, testable behavior.

## Generate a project

After installing Gateway7, run from any working directory:

```sh
gateway7 plugin init company_mask --directory .
gateway7 plugin test --config company_mask/gateway.yaml --fixtures company_mask/fixtures.json
```

The parent directory must already exist.
Names are lowercase Python identifiers, up to 48 characters; Python keywords and reserved Windows device names are rejected.
An existing target is never overwritten.

| Generated path | Purpose |
| --- | --- |
| `company_mask/gateway7_plugin_company_mask/plugin.py` | API v2 middleware, strict settings and `PLUGIN` descriptor |
| `company_mask/gateway7_plugin_company_mask/__init__.py` | Importable package |
| `company_mask/pyproject.toml` | Normal installable Python package, with Gateway7 dependency |
| `company_mask/gateway.yaml` | Instance settings and order using the generated module |
| `company_mask/fixtures.json` | Full-history/response transformation and benign-text examples |
| `company_mask/README.md` | Local commands, installation and trust boundary |

No project file depends on the Gateway7 repository path.
The offline worker imports packages next to the supplied configuration, so it can test the generated source before installation.
Normal `validate`/`serve` use the gateway's installed Python environment, so install the package before those commands.

## Read expected and actual results

```sh
gateway7 plugin test --config company_mask/gateway.yaml --fixtures company_mask/fixtures.json --json
```

Without `--json`, the report prints each case/check with expected and actual values.
JSON reports have `schema_version`, `passed`, `total`, `failed` and `cases`; each case contains `checks` with `field`, `passed`, `expected` and `actual`.
An invalid setup adds a safe `error` field.

| Exit | Meaning |
| --- | --- |
| 0 | Every fixture matched |
| 1 | At least one expected/actual check differed |
| 2 | Invalid configuration/fixtures, worker failure, interruption or suite timeout |

For a deliberate negative check, change an expected response in a copy of `fixtures.json` and rerun: the report must show the mismatch and return exit 1.
Do not update expectations merely to make a failing test green; first decide whether the policy or fixture is wrong.
Fixture reports intentionally expose synthetic expected/actual text, so never use real secrets or customer conversations as fixtures.

## Fixture schema

A minimal valid suite for the generated literal mask is:

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

`request` and `provider_response` use the core models; omitted token settings/finish reason use their model defaults.
`expected.request` is the processed request seen by the fixture provider.
`expected.response` is the final allowed answer after response middleware; include `usage` to test its preservation.
For a request-side block, use `expected: {"provider_calls": 0, "error": "policy_denied"}` without a response or provider request.
For a technical failure, use the expected safe error code. `provider_error: true` simulates an upstream failure.
Each case must expect exactly one response or one error, and `provider_calls` must be 0 or 1.

The schema rejects unknown fields, duplicate JSON keys and duplicate case names.
A suite has 1–64 cases and a maximum 1 MiB input file; reports are capped at 4 MiB.
The default whole-suite wall-clock limit is 30 seconds; set `--timeout` between 1 and 300 seconds when needed.
The configuration's normal per-request and per-middleware budgets are still applied within each case.

## Install normally and serve

Use the same Python environment that runs Gateway7.
From a Gateway7 checkout with its `.venv` already synchronized:

```sh
uv pip install --no-deps ./company_mask
uv run --locked gateway7 validate --config company_mask/gateway.yaml
```

This is a normal package installation, not an editable import from the working directory.
For another environment, pass its Python executable to `uv pip install --python PATH --no-deps ./company_mask`, or use that environment's `python -m pip install ./company_mask`.
Package installation may download build requirements; the credential-free/offline guarantee applies to `plugin test`, not to the package manager.
If a later clean dependency sync removes extra company packages, reinstall them as part of the deployment build.

Copy the selected real provider and `auth` sections from a maintained example into the generated `gateway.yaml`, retaining the generated plugin declaration and middleware order.
Set provider and client credentials privately, validate, then run:

```sh
gateway7 serve --config company_mask/gateway.yaml
```

The generated fake-provider configuration is for offline fixtures; `serve` does not automatically start a fixture upstream.
The [setup guide](setup.md#real-providers) explains live credentials and the [API guide](api.md) shows a client call.
After editing the plugin, reinstall its package and restart the gateway; there is no hot loading.

CI verifies this complete path outside the checkout: generate, offline pass, deliberate mismatch, invalid setup, normal package installation, validation and an authenticated OpenAI SDK call through the installed middleware.
It also verifies that a forbidden model produces no additional provider call.

## Offline execution boundary

The worker uses a deterministic in-memory fixture provider even when the supplied YAML names a real provider.
It does not resolve provider keys or client tokens, and it inherits only a small operating-system environment allowlist.
Python socket networking and subprocess creation are blocked before plugin import, construction and lifecycle hooks.
Plugin stdout/stderr are discarded; results are returned through the bounded structured report.
The parent enforces the wall-clock timeout and terminates an overrun or interrupted worker.

This catches accidental network calls and separates fixture state from the CLI process; it is not an operating-system security sandbox for hostile code or native extensions.
Only test trusted plugins. Running `validate` or `serve` imports trusted Python code in the gateway process with its ordinary environment.
Keep originals out of instance state/logs, use immutable settings, and follow the [middleware contract](plugins.md#descriptor-and-hooks) when adapting the generated example.
