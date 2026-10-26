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
From the checkout, run:

```sh
docker compose config --quiet
docker compose up --build --detach --wait
```

Use the [first-request example](quickstart.md#send-your-first-request) to check the result.

| Service | Local address | Purpose |
| --- | --- | --- |
| Gateway | `http://127.0.0.1:8000` | Chat APIs, model list and health endpoints |
| Prometheus | `http://127.0.0.1:9090` | Collect and query gateway metrics |
| Grafana | `http://127.0.0.1:3000/d/gateway7-overview` | Ready-to-use monitoring dashboard |

The default stack runs `gateway7 demo` with the public token `gateway7-synthetic-client-token`.
Its synthetic provider runs inside the gateway container and listens only on loopback.
It makes no call to a real provider.

```sh
docker compose logs --tail=50 gateway
docker compose down
```

Stopping the stack keeps the named monitoring volumes.
`docker compose down --volumes` also deletes their history.
If a port is busy, stop the other local service or change the host port in `compose.yaml` and use the new address in your requests.

The gateway image runs as user 10001 with locked runtime dependencies and no development tools.
Compose gives it a read-only filesystem, a temporary `/tmp` and localhost-only published ports.
The build excludes credentials and local Python environments.
Python, uv, Prometheus and Grafana have version pins; the images are not pinned by immutable digest.

Grafana allows anonymous read-only access on localhost and creates no administrator account.
For a shared deployment, add HTTPS termination and restrict access to the monitoring network.
Chat authentication does not protect `/health`, `/ready` or `/metrics`.

## Real providers

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

### Select and validate a config

For OpenAI, set:

```sh
export GATEWAY_CONFIG_FILE=./config/openai.yaml
export GATEWAY_KEY_ENV=OPENAI_API_KEY
```

For Claude or Gemini, use the matching file and variable from the table.
Validate with the Python checkout:

```sh
uv run --locked gateway7 validate --config "$GATEWAY_CONFIG_FILE"
```

Expect `Configuration valid: provider=openai; middleware=4` for the OpenAI sample.

With the image built in the quickstart, you can validate without installing Python locally:

```sh
docker compose -f compose.yaml -f compose.live.yaml run --rm --no-deps \
  gateway validate --config /etc/gateway7/gateway.yaml
```

Validation needs no credentials and makes no provider call.
It checks configuration and imports trusted plugin factories; those factories may have their own side effects.
A valid config does not prove that an account or model is available.

### Supply server credentials

Use a secret manager or private environment injection in a shared deployment.
For a local Bash session, the prompts below read values without echoing them or putting them in shell history.
Create a separate random client token in your password manager: 16–512 visible ASCII characters, without spaces.

```sh
read -r -s -p 'Provider API key: ' "$GATEWAY_KEY_ENV"
printf '\n'
export "$GATEWAY_KEY_ENV"
read -r -s -p 'Gateway client token: ' GATEWAY7_CLIENT_TOKEN
printf '\n'
export GATEWAY7_CLIENT_TOKEN
```

The client token must differ from the provider key.
Keep credential values out of YAML and committed files.
Gateway7 does not load `.env` files; Docker Compose has its own environment-file behavior.
Avoid printing the expanded live Compose config because it can contain injected credentials.

### Start the server and send a request

Stop the demo first if it uses port 8000.
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
The live stack does not start the synthetic provider.

In a client terminal, enter the installed Python checkout and paste the same gateway client token:

```sh
read -r -s -p 'Gateway client token: ' GATEWAY7_TOKEN
printf '\n'
export GATEWAY7_TOKEN
uv run --locked gateway7 chat --message 'Reply with the word pong' --max-tokens 1024
```

This command makes a real provider call and can consume paid tokens.
A successful call returns JSON with `text` and provider-reported `usage`; model output can vary.
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
Real-provider traffic uses the official HTTPS origins with server-held keys in headers; custom origins, redirects and proxy-environment settings are not used.
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
