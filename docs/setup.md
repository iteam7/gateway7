# Set up and run Gateway7

Use the [quickstart](quickstart.md) for a local Docker demo with a dashboard.
This page covers Python installation, real providers and deployment settings.
Commands use Bash on Linux, macOS or Windows with WSL.

## Install from a checkout

Install Git, Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Gateway7 supports Python 3.11–3.13.

```sh
git clone https://github.com/iteam7/gateway7.git
cd gateway7
uv sync --locked
uv run --locked gateway7 demo
```

Leave that terminal open.
In a second terminal, enter the same checkout and send a request:

```sh
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
uv run --locked gateway7 chat \
  --message 'Contact synthetic@example.com or +7 999 123-45-67; SECRET-TEST'
```

Expect the text `pong — Contact [EMAIL] or [PHONE]; [removed]`, with synthetic usage of 12 input and 4 output tokens.
The demo starts its own local provider and needs no provider key.
Press Ctrl-C in the first terminal to stop both processes.

`uv.lock` fixes the dependency versions.
Keep `--locked` so a lock mismatch produces an error instead of changing the environment silently.
After installing the Gateway7 wheel, use `gateway7` directly from any directory; the demo includes its own defaults.
See the [CLI reference](cli.md) for all commands.

## Docker Compose

Install Docker Engine or Docker Desktop with Compose v2.
From the checkout, select the synthetic demo explicitly:

```sh
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml up --build --detach --wait
```

Use the [first-request example](quickstart.md#send-your-first-request) to check the result.

| Service | Local address | Purpose |
| --- | --- | --- |
| Gateway | `http://127.0.0.1:8000` | Chat APIs, model list and health endpoints |
| Prometheus | `http://127.0.0.1:9090` | Collect and query gateway metrics |
| Grafana | `http://127.0.0.1:3000/d/gateway7-overview` | Ready-to-use monitoring dashboard |

This stack runs `gateway7 demo` with the public token `gateway7-synthetic-client-token`, even if `.env` selects a real provider.
Its synthetic provider runs inside the gateway container and listens only on loopback.
It makes no call to a real provider.

```sh
docker compose -f compose.yaml logs --tail=50 gateway
docker compose -f compose.yaml down
```

Stopping the stack keeps the named monitoring volumes.
`docker compose -f compose.yaml down --volumes` also deletes their history.
If a port is busy, stop the other local service or change the host port in `compose.yaml` and use the new address in your requests.

The gateway image runs as user 10001 with locked runtime dependencies and no development tools.
Compose gives it a read-only filesystem, a temporary `/tmp` and localhost-only published ports.
The build excludes credentials and local Python environments.
Python, uv, Prometheus and Grafana have version pins; the images are not pinned by immutable digest.

Grafana allows anonymous read-only access on localhost and creates no administrator account.
For a shared deployment, add HTTPS termination and restrict access to the monitoring network.
Chat authentication does not protect `/health`, `/ready` or `/metrics`.

## OpenCode V2

The checked scenario uses the exact package `@opencode/cli@2.2.2`, whose executable is `opencode2` and whose version output is `opencode v2.2.2`.
The `opencode-ai` package is a different release line and is not the tested V2 harness.
Gateway7 supports its OpenAI-compatible Chat route with function tools and serial calls.
Upstream generation is streamed, but OpenCode receives SSE only after the gateway has checked the complete model response.

### Reproduce the harness check without a provider account

From a prepared Python checkout, install the pinned CLI into a disposable directory with Node.js and npm:

```sh
gateway7_opencode_tools="$(mktemp -d)"
npm install --prefix "$gateway7_opencode_tools" --no-audit --no-fund @opencode/cli@2.2.2
uv run --locked python scripts/smoke_opencode.py \
  --opencode "$gateway7_opencode_tools/node_modules/.bin/opencode2"
```

The check creates its own loopback Gateway7 server, isolated OpenCode config/data directories and synthetic text file.
It runs the real OpenCode binary through the production OpenAI adapter with an injected local transport; no request is sent to external OpenAI.
The provider fixture sends 17-byte HTTP fragments and splits function arguments across SSE events.
The allowed case executes `read` once, replays its result in a second provider request, and returns `GATEWAY7_AGENT_OK`.
The denied case puts a policy term in the returned tool argument and verifies one provider request, zero tool executions and a client error.
The report records the CLI version and binary hash, actual provider-stream flags and both scenario verdicts, without credentials or raw request bodies.

This check passed on 30 October 2026 with the version above.
It verifies a real harness against synthetic upstream responses; it does not verify access to a real OpenAI model or every OpenCode release and feature.
The complete checked profile is the `opencode_config` function in `scripts/smoke_opencode.py`.
It sets primary and small models to `gateway7/gpt-4.1`, output limit 1024, no reasoning or temperature control, and `parallelToolCalls: false`.
Its primary agent allows file reading and denies other tool permissions; V2 also advertises its built-in `skill` definition.

### Point the checked profile at your OpenAI gateway

First start the [real OpenAI configuration](#openai-with-a-env-file).
To reuse the checked model ID, set both `provider.model` and `auth.clients.developer.models` in `config/openai.yaml` to `gpt-4.1`, then recreate the gateway.
Your OpenAI account must have access to that model.
This live account/model combination was not exercised by the synthetic check and can incur charges.

Keep `gateway7_opencode_tools` from the installation above and run the following from the Gateway7 checkout:

```sh
export GATEWAY7_OPENCODE_PROJECT="$(mktemp -d)"
uv run --locked python - <<'PYCONFIG'
import json
import os
from pathlib import Path
from scripts.smoke_opencode import opencode_config

project = Path(os.environ["GATEWAY7_OPENCODE_PROJECT"])
profile = opencode_config("http://127.0.0.1:8000/v1")
(project / "opencode.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
(project / "agent-fixture.txt").write_text("GATEWAY7_AGENT_OK\n", encoding="utf-8")
PYCONFIG
read -r -s -p 'Gateway client token: ' GATEWAY7_CLIENT_TOKEN
printf '\n'
export GATEWAY7_CLIENT_TOKEN
cd "$GATEWAY7_OPENCODE_PROJECT"
"$gateway7_opencode_tools/node_modules/.bin/opencode2" --standalone run \
  --model gateway7/gpt-4.1 --agent gateway7-smoke --format json \
  --title 'Gateway7 file-read check' \
  'Read agent-fixture.txt with the read tool and return its control string.'
```

Enter the gateway client token, not `OPENAI_API_KEY`.
The generated file references `{env:GATEWAY7_CLIENT_TOKEN}` and contains no secret.
Check the JSON events for a completed `read` and the final marker; a text answer alone does not prove a tool round trip.
The underlying model decides whether to call a tool, so live output can differ from the deterministic fixture.
For longer coding sessions, deliberately configure sufficient request-body and overall timeout limits; the bounded profile above is a read-only integration check.

## Real providers

### OpenAI with a `.env` file

From a new checkout, copy the template:

```sh
cp -n .env.example .env
chmod 600 .env
```

Open `.env` in your editor and fill in two values:

- `OPENAI_API_KEY`: your OpenAI API key.
- `GATEWAY7_CLIENT_TOKEN`: a different random token from your password manager, 16–512 visible ASCII characters without spaces.

The template already selects the live Compose files and `config/openai.yaml`.
Use single quotes around a `.env` value containing literal `$` or `#` characters.
If you already have `.env`, keep your secrets and copy the four presets from `.env.example`: `COMPOSE_FILE`, `COMPOSE_PATH_SEPARATOR`, `GATEWAY_CONFIG_FILE` and `GATEWAY_KEY_ENV`.
Stop any demo using port 8000, then run:

```sh
docker compose up --build --detach --wait
docker compose exec -T gateway gateway7 smoke --token-env GATEWAY7_CLIENT_TOKEN
```

No exports, Python installation or YAML edits are needed for the sample.
The second command reuses the container's gateway client token and sends at most one potentially billable chat request.
It reports status, safe request IDs and token usage without printing credentials or the model's answer.
Open Grafana at `http://127.0.0.1:3000/d/gateway7-overview`.
Use `docker compose logs --tail=50 gateway` to inspect safe logs and `docker compose down` to stop the stack.

Compose reads `.env` from this checkout: `COMPOSE_FILE` selects the base and live override, and `COMPOSE_PATH_SEPARATOR` fixes the file-list separator across platforms.
Values exported in your shell take precedence over `.env`; remove stale exports when switching configurations.
An explicit `-f compose.yaml` overrides that file selection and starts the synthetic demo.
The gateway itself reads process variables; Compose loads the file and passes only the selected provider key, client token and proxy variable into the container.
Keep `.env` private: Git ignores it, the image build excludes it and it is not mounted into the container.
Avoid printing the expanded live Compose config because it can contain credentials.

After editing `.env`, recreate the gateway to apply the values:

```sh
docker compose up --detach --wait --force-recreate gateway
docker compose exec -T gateway gateway7 smoke --token-env GATEWAY7_CLIENT_TOKEN
```

### Choose a provider and model

Select one provider for each running gateway.
The sample files already define a model, an authenticated client and the reference middleware chain.

| Config file | Model in the sample | Provider key variable |
| --- | --- | --- |
| `config/openai.yaml` | `gpt-4.1-mini` | `OPENAI_API_KEY` |
| `config/claude.yaml` | `claude-haiku-5-5` | `ANTHROPIC_API_KEY` |
| `config/gemini.yaml` | `gemini-3.8-flash` | `GEMINI_API_KEY` |

Your provider account must have access to the selected model.
If you change it, update both `provider.model` and the client's `auth.clients.developer.models` list.
The gateway does not discover or switch models for you.
For Claude or Gemini with `.env`, change `GATEWAY_CONFIG_FILE` and `GATEWAY_KEY_ENV` to the matching file and variable, and add that provider key to the file.
Keep the same two Compose file selectors and the separate gateway client token.
For a network proxy or a custom outbound HTTP transport, see [provider transports](provider-transports.md).
Setting a proxy URL alone does not enable proxy routing.

### Select and validate a config

The `.env` example already selects OpenAI.
Validate the sample with a Python checkout:

```sh
uv run --locked gateway7 validate --config config/openai.yaml
```

Expect `Configuration valid: provider=openai; middleware=4` for the OpenAI sample.

With a built image, validate the selected Compose configuration without installing Python locally:

```sh
docker compose -f compose.yaml -f compose.live.yaml run --rm --no-deps \
  gateway validate --config /etc/gateway7/gateway.yaml
```

Validation needs no credentials and makes no provider call.
It checks configuration and imports trusted plugin factories; those factories may have their own side effects.
A valid config does not prove that an account or model is available.

### Supply server credentials

Skip this section if you filled in `.env` above.
Use a secret manager or private environment injection in a shared deployment.
For a local Bash session, the prompts below read values without echoing them or putting them in shell history.
Create a separate random client token in your password manager: 16–512 visible ASCII characters, without spaces.
Select OpenAI as shown, or use the matching config and key variable from the provider table:

```sh
export GATEWAY_CONFIG_FILE=./config/openai.yaml
export GATEWAY_KEY_ENV=OPENAI_API_KEY
read -r -s -p 'Provider API key: ' "$GATEWAY_KEY_ENV"
printf '\n'
export "$GATEWAY_KEY_ENV"
read -r -s -p 'Gateway client token: ' GATEWAY7_CLIENT_TOKEN
printf '\n'
export GATEWAY7_CLIENT_TOKEN
```

The client token must differ from the provider key.
Keep credential values out of YAML and committed files.
The gateway does not parse `.env`; Compose loads it for the Docker flow above.
Avoid printing the expanded live Compose config because it can contain injected credentials.

### Start the server and send a request

For the `.env` Compose flow, use the commands above.
For a process-environment setup, stop the demo first if it uses port 8000.
Choose one launch method:

```sh
# Python: keep this terminal open.
uv run --locked gateway7 serve --config "$GATEWAY_CONFIG_FILE"
```

```sh
# Docker: start the live gateway and monitoring stack.
docker compose -f compose.yaml -f compose.live.yaml up --build --detach --wait
```

The live override mounts the selected YAML read-only and passes the selected provider key and `GATEWAY7_CLIENT_TOKEN` to the server.
`GATEWAY_KEY_ENV` must match the YAML `provider.key_env`.
For an explicit proxy transport, it also forwards `GATEWAY7_PROXY_URL`; see the [proxy configuration](provider-transports.md#configure-the-built-in-proxy) before starting the stack.
The live stack does not start the synthetic provider.

In a client terminal, enter the installed Python checkout and paste the same gateway client token:

```sh
read -r -s -p 'Gateway client token: ' GATEWAY7_TOKEN
printf '\n'
export GATEWAY7_TOKEN
uv run --locked gateway7 smoke --model gpt-4.1-mini --max-tokens 256
```

Use the selected model ID if you changed the OpenAI sample or chose another provider.
`smoke` checks liveness, local readiness and authenticated model access, then sends at most one short chat request without retries.
With a real provider configured, this can consume paid tokens, including when the final check fails.
Its JSON report includes `passed`, individual `checks`, `chat_attempts`, duration, safe request IDs and reported token usage; it omits the answer and credentials.
Exit 0 means the checks passed; any other exit needs investigation before the demonstration.
The [CLI reference](cli.md#check-a-running-gateway) covers options and failure reporting.

Confirm the selected server configuration yourself: smoke cannot distinguish a real provider from a synthetic server by its response alone.
`/ready` alone confirms initialization, not OpenAI account, model or proxy access.
Use [the API guide](api.md) to connect an application without the Gateway7 CLI.
See [authentication](authentication.md) for additional clients, model access and token rotation.

For a live Compose stack, keep both config arguments when reading logs or stopping it:

```sh
docker compose -f compose.yaml -f compose.live.yaml logs --tail=50 gateway
docker compose -f compose.yaml -f compose.live.yaml down
```

The samples allow 60 seconds for a whole request and 30 seconds for provider transport operations.
Provider failures return a safe HTTP 502; the gateway's overall deadline returns HTTP 504.
Some models can use tokens without producing a supported final answer, especially with a small output budget.
Missing or invalid usage is returned as `null`.
Use the [provider failure reasons](observability.md#provider-failure-reasons) to diagnose errors.

### Rehearse the live demonstration

With the unchanged OpenAI `.env` Compose stack, show the contact-handling case and the request policy:

```sh
docker compose exec -T gateway gateway7 chat --token-env GATEWAY7_CLIENT_TOKEN \
  --message 'Draft a short support reply for synthetic@example.com, phone +7 999 123-45-67.' \
  --max-tokens 256
docker compose exec -T gateway gateway7 chat --token-env GATEWAY7_CLIENT_TOKEN \
  --message 'BLOCK-ME-TEST' --max-tokens 256
```

The first command makes another potentially billable call; its wording can vary.
The second must report HTTP 403 and exit 1 without a provider call because the sample's request guard blocks that exact marker.
Check the configured rule before using it on a modified deployment; otherwise it may reach the provider.
Show [Grafana](observability.md#what-the-dashboard-shows) and correlate the request ID from the smoke report with safe gateway logs.

Prove masking and response redaction with the [deterministic regression fixtures](middleware-catalog.md#ordering-and-verification) before the meeting.
An email missing from a model's answer does not prove it was masked before sending; a model also need not repeat the response-redaction marker.
Use synthetic contacts and keep prompt bodies out of logs.

Record the tested commit with `git rev-parse HEAD` and keep its image and configuration available.
After changing credentials or YAML, recreate the gateway and run smoke again as shown in the [`.env` recipe](#openai-with-a-env-file).
Each smoke invocation can make one paid call.
If the new configuration fails, restore the saved image/configuration and recreate it before rechecking.
Use the [architecture](architecture/README.md#customer-view), [middleware authoring](authoring.md) and this live recipe as the short documentation route during the demonstration.

## Configuration and HTTP contract

| Setting | What it controls |
| --- | --- |
| `provider.kind` | `fake`, `openai`, `claude` or `gemini` |
| `provider.base_url` | Official HTTPS origin for a real provider; literal loopback HTTP for a fake provider |
| `provider.key_env` | Name of the server environment variable holding the provider key |
| `provider.model` | Default model, which must also be allowed for the client |
| `provider.timeout_seconds` | Provider transport timeout; default 30 seconds |
| `limits.request_timeout_seconds` | Whole-request deadline; default 10 seconds, 60 in the real-provider samples |
| `limits.hook_timeout_seconds` | A middleware's combined request/response work budget; default 2 seconds, excluding waits for the next handler |
| `limits.max_body_bytes` | Request body limit; default 65,536 bytes |
| `limits.max_concurrent_requests` | Active pipelines per process; default 64, configurable from 1 to 10,000 |
| `auth` | Client token environment names and model allowlists |
| `plugins` | Named middleware instances and their validated settings |
| `middleware` | Request order; responses pass through the chain in reverse |

Unknown fields, invalid settings and missing required middleware stop startup.
`serve` also loads credentials and runs plugin startup hooks before becoming ready.
Changing plugins, credentials or client access requires a restart.

Capacity is checked after authentication and payload/model validation, just before middleware starts.
When all slots are busy, a new chat request gets HTTP 503 with code `overloaded`; it is not queued and makes no provider call.
The slot stays busy until the pipeline task finishes, including cancellation cleanup.
Health, metrics and model-list requests do not use these slots.
Each process has its own limit; this setting is not a per-client quota or a limit on connections and body reads.

Timeouts depend on cooperative async code.
A plugin that blocks Python or ignores cancellation can keep running and hold its slot.
Plugins are trusted Python code in the gateway process, not isolated services or sandboxed code.

The [HTTP API reference](api.md) covers native chat, the supported OpenAI-compatible subset and error bodies.
`/health` reports process liveness; `/ready` reports local startup/shutdown state without calling a provider.
`/metrics` exposes Prometheus text.
Real-provider traffic uses the official HTTPS origins with server-held keys in headers; custom origins and redirects are not used.
Proxy routing is an explicit [provider transport](provider-transports.md) setting; implicit HTTP proxy and certificate environment settings are ignored.
Gateway7 does not retry, route between providers or fail over automatically.

## Checks and tests

From an installed development checkout:

```sh
uv run --locked ruff format --check gateway7
uv run --locked ruff check gateway7
uv run --locked mypy gateway7
uv run --locked pytest -q
uv run --locked python -m demo.run
uv build --wheel
```

With the default Compose demo running, check the complete local stack:

```sh
python scripts/smoke_compose.py
```

The smoke checks both chat APIs, client/model access, policy behavior, metrics, Prometheus and Grafana.
The Python CI workflow also checks a normally installed wheel and generated plugin outside the checkout, then builds and tests the Compose stack on Ubuntu.
These synthetic checks do not verify real-provider account access or replace a test on another operating system.
See [CONTRIBUTING.md](https://github.com/iteam7/gateway7/blob/main/CONTRIBUTING.md#checks-and-documentation) for documentation checks and contributor workflow.
