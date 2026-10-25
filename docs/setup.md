# Set up and run Gateway7

Gateway7 can run as an installed CLI or as a Docker Compose stack with Prometheus and Grafana.
The Python choice is recorded in [DEC-013](decisions.md#dec-013).
Start in synthetic mode to exercise the complete middleware and monitoring path without an account.

## Install from a checkout

Use Git, Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
The package supports Python 3.11–3.13; development uses 3.12.

```sh
git clone https://github.com/iteam7/gateway7.git
cd gateway7
uv sync --locked
uv run --locked gateway7 demo
```

`pyproject.toml` declares dependencies and `uv.lock` fixes their resolution.
Do not remove `--locked` to hide an unexpected lock mismatch.
In another terminal, set `GATEWAY7_TOKEN=gateway7-synthetic-client-token` in the environment, then `uv run --locked gateway7 chat --message 'Contact synthetic@example.com'` returns an answer containing `[EMAIL]`.
The demo uses packaged defaults, creates a private loopback fixture and stops it on shutdown; it works outside the repository after wheel installation.
See the [CLI reference](cli.md) for serving, validation, stdin and exit codes.

## Docker Compose

Install Docker Engine with Compose v2, or Docker Desktop with Compose v2, then run from the checkout:

```sh
docker compose config --quiet
docker compose up --build --detach --wait
```

| Service | Local address | Purpose |
| --- | --- | --- |
| Gateway | `http://127.0.0.1:8000` | `POST /chat`, `/v1/chat/completions`, `/v1/models` and operational endpoints |
| Prometheus | `http://127.0.0.1:9090` | Scrapes gateway metrics every 5 seconds |
| Grafana | `http://127.0.0.1:3000/d/gateway7-overview` | Provisioned dashboard and Prometheus datasource |

The default command is `gateway7 demo`; it calls a synthetic upstream inside the gateway container, listening only on loopback.
No provider account, provider API key or fixture-recorder port is needed.
The demo protects chat/model endpoints with the public synthetic token `gateway7-synthetic-client-token`.
The gateway image runs as UID/GID 10001, installs locked runtime dependencies without development tools, and copies a non-editable installation into the final image.
Compose gives the gateway a read-only filesystem and temporary `/tmp`, drops Linux capabilities and publishes ports only on localhost.
The build context includes only the required source and packaging files; credentials and local environments are excluded.

The Dockerfile pins Python and uv versions; Compose pins Prometheus and Grafana versions.
Tags can be republished upstream; these are version pins, not immutable image digests.
Grafana uses anonymous Viewer access, disables the initial administrator account and login form, and treats dashboards/datasources as repository-owned configuration.
Client authentication and model allowlists protect chat access. A shared deployment still needs TLS termination and a trusted boundary around monitoring endpoints.

```sh
python scripts/smoke_compose.py
docker compose logs --tail=50 gateway
docker compose down
```

The smoke check verifies missing/wrong client tokens, model permissions, native and OpenAI-compatible requests, masking/redaction, and zero provider calls for denied requests, then exercises Prometheus and Grafana provisioning.
Named volumes retain metrics and Grafana state across restarts.
To intentionally delete that history, run `docker compose down --volumes`.
If ports 8000, 9090 or 3000 are occupied, stop the conflicting local service or edit the corresponding host-side port mapping; update the smoke URLs accordingly.

## Real providers

Choose one server configuration per gateway instance.
The gateway has thin, nonstreaming HTTP adapters for the following APIs:

| Configuration | Provider API | Server credential variable |
| --- | --- | --- |
| `config/openai.yaml` | OpenAI Chat Completions | `OPENAI_API_KEY` |
| `config/claude.yaml` | Anthropic Claude Messages | `ANTHROPIC_API_KEY` |
| `config/gemini.yaml` | Google Gemini `generateContent` | `GEMINI_API_KEY` |

Each sample enables request blocking, phone/email masking in both directions and response redaction.
Replace the explicit example model ID with one your account can access when necessary.
The origin defaults to the provider's official HTTPS origin; custom origins, redirects, proxy-environment settings and key-in-URL authentication are rejected or disabled.
Only the server adapter attaches the key to an outbound header.
There is no automatic retry, provider routing or failover.

Set the selected provider credential and a distinct `GATEWAY7_CLIENT_TOKEN` privately in the server environment or secret injection, then:

```sh
uv run --locked gateway7 validate --config config/openai.yaml
uv run --locked gateway7 serve --config config/openai.yaml
```

In the client terminal, put the gateway client token value in `GATEWAY7_TOKEN`, then:

```sh
uv run --locked gateway7 chat --message 'Reply with the word pong' --max-tokens 1024
```

For Compose, set the selected provider key and `GATEWAY7_CLIENT_TOKEN` in your shell, then select the configuration and provider variable name:

```sh
export GATEWAY_CONFIG_FILE=./config/openai.yaml
export GATEWAY_KEY_ENV=OPENAI_API_KEY
docker compose -f compose.yaml -f compose.live.yaml up --build --detach --wait
```

Use the same two `-f` arguments for subsequent `logs` or `down` commands.
The override switches the gateway to `serve`, mounts the selected YAML read-only and passes only the selected provider variable and `GATEWAY7_CLIENT_TOKEN` from the host environment; it does not start the synthetic upstream.
For Claude or Gemini, change the config path and `GATEWAY_KEY_ENV` to the corresponding credential-variable name in the table.
The YAML `provider.key_env` and `GATEWAY_KEY_ENV` must select the same provider variable.
See [client authentication](authentication.md) for token rules, model permissions and restart-based rotation.
The application does not read `.env` files itself; Docker Compose's own environment-file behavior is separate.
Never put credentials in YAML, command-line arguments or committed files, and avoid printing an expanded live Compose configuration because it contains injected environment values.

The examples allow a 60-second overall request deadline and a 30-second provider transport timeout.
A provider transport error, rate limit, rejected credential or unsupported answer becomes a safe HTTP 502; the overall gateway deadline becomes HTTP 504.
A model can consume tokens without producing a supported final text answer, particularly with too-small generation budgets.
The response exposes normalized provider-reported `input_tokens`/`output_tokens` when valid; absent or invalid usage remains `null`.

Adapter payloads are checked against the [OpenAI Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [Claude Messages reference](https://platform.claude.com/docs/en/api/messages/create), and [Gemini generateContent reference](https://ai.google.dev/api/generate-content).
Offline HTTP fixtures exercise these adapters; they do not establish real account access.
The actual keyed Claude/Gemini `pong` response in [US-01 AC-05](https://github.com/iteam7/gateway7/issues/30) and Customer verdicts remain separate verification.

## Configuration and HTTP contract

| Field | Purpose |
| --- | --- |
| `provider.kind` | One of `fake`, `openai`, `claude`, `gemini` |
| `provider.base_url` | Optional official origin for real providers; fake requires literal loopback HTTP |
| `provider.key_env` | Server environment-variable name; no credential value in YAML |
| `provider.model` | Default model; each request must select a model permitted for its authenticated client |
| `provider.timeout_seconds` | Transport timeout, default 30 seconds |
| `limits.request_timeout_seconds` | Deadline covering reading, middleware, provider and response work |
| `limits.hook_timeout_seconds` | Each middleware's cumulative own-work budget, excluding downstream waiting |
| `limits.max_body_bytes` | HTTP request body cap |
| `auth` | Client token environment-variable names and model allowlists; real providers require authentication |
| `plugins` | Named module instances with strict validated settings and enabled/required flags |
| `middleware` | Request order; response processing reverses this order |

Unknown fields, invalid plugin settings, missing required filters and unavailable credentials fail startup safely.
`gateway7 validate` checks the configuration without requiring a credential; `serve` additionally starts plugin lifecycles and resolves the key before readiness.
See the [middleware catalog](middleware-catalog.md) and [API v2 migration](plugins.md#migration-from-api-version-1).

`POST /chat` accepts `messages`, optional authorized `model`, and optional `max_tokens` from 1 to 4096.
`POST /v1/chat/completions` and `GET /v1/models` support the documented [OpenAI SDK subset](api.md).
Messages use roles `system`, `user` or `assistant` with plain-text `content`; unsupported fields, tools, attachments and streaming are rejected.
`GET /health` is process liveness; `GET /ready` is startup/shutdown readiness, without a billable provider probe.
`GET /metrics` exports Prometheus text. These operational endpoints are unauthenticated; chat and model endpoints require the client bearer token.
Errors contain a stable code and request ID, without raw input, token values or provider details.
The configured limits bound cooperative async work; trusted Python plugins are not a process sandbox.

## Checks and tests

```sh
uv run --locked ruff format --check gateway7
uv run --locked ruff check gateway7
uv run --locked mypy gateway7
uv run --locked pytest -q
uv run --locked python -m demo.run
uv build --wheel
```

The Python workflow additionally installs the gateway wheel outside the checkout, generates/tests/normally installs a plugin package, makes authorized SDK calls to that installed server, and builds/runs the full Compose stack on Ubuntu.
Markdown and link checks remain separate documentation gates.
Neither an automated check nor AI review replaces human PR approval, live-provider verification or Customer acceptance.

[Task #84](https://github.com/iteam7/gateway7/issues/84) still requires repeated Windows timeout verification; Linux checks do not establish that result.
The proposed Windows CI change remains in [PR #78](https://github.com/iteam7/gateway7/pull/78).
