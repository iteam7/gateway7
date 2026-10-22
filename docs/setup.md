# Set up and run Gateway7

The Python choice is recorded in [DEC-013](decisions.md#dec-013).
After cloning, run all remaining commands from the repository root.
The initial demonstration needs no provider account, database, frontend or container runtime.

## Prerequisites and installation

- Python 3.12 is the pinned development runtime; the package supports Python 3.11–3.13.
- Install Git to obtain a clean checkout.
- Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Allow package-registry access for the first install and local loopback sockets for the two demo processes.

```sh
git clone https://github.com/iteam7/gateway7.git
cd gateway7
uv sync --locked
```

`pyproject.toml` declares direct dependencies; `uv.lock` pins the complete resolution.
Do not remove `--locked` to work around an unexpected manifest/lock mismatch.

## One-command demonstration

```sh
uv run --locked python -m demo.run
```

The command starts a recording fake provider and the actual gateway as separate HTTP processes on local ports, uses only public synthetic fixtures, exercises restart and plugin installation, then stops its processes.
It exits nonzero if a check fails.
See the [demo walkthrough](demo.md) for the expected observations and criterion mapping.

## Configuration

The committed `.env.example` contains the environment-variable names and a public synthetic key for the local fake provider.
Gateway7 reads variables from the process environment; it does **not** automatically load `.env` files.
Never replace public examples with a real credential or commit `.env`.
The server config path is `--config PATH`, or `GATEWAY_CONFIG` when starting the app without the CLI; the default is `config/demo.yaml`.

| YAML field | Purpose |
| --- | --- |
| `provider.kind` | One selected adapter: `fake` or `claude` |
| `provider.base_url` | Server-controlled endpoint, never supplied by the client |
| `provider.key_env` | Name of the required environment variable; the YAML does not hold its value |
| `provider.model` | Server-selected model; ignored by the deterministic fake provider |
| `limits` | Total request deadline, each middleware's own-work budget and request-body size cap |
| `plugins` | Instance names mapped to module, enabled/required flags and validated settings |
| `middleware` | One ordered instance list; responses return through it in reverse |

Unknown configuration fields and invalid plugin settings fail startup.
A missing key fails startup with the setting's name and no secret value.
See [plugin authoring](plugins.md) for installation, disable and required-filter behavior.
API version 2 replaces `chains.request` / `chains.response` and the old hooks; follow the [migration steps](plugins.md#migration-from-api-version-1) for existing plugins.
`limits.hook_timeout_seconds` now budgets a middleware's combined preprocessing and postprocessing, excluding its wait for the next handler.
The overall request deadline still includes all middleware and provider work.

## Run the two services manually

In terminal 1, start the **synthetic-data-only** fake upstream:

```sh
export DEMO_PROVIDER_KEY=gateway7-synthetic-demo-only
uv run --locked python -m uvicorn demo.upstream:app --host 127.0.0.1 --port 8001
```

In terminal 2, start Gateway7:

```sh
export FAKE_LLM_API_KEY=gateway7-synthetic-demo-only
uv run --locked python -m gateway7 --config config/demo.yaml --host 127.0.0.1 --port 8000
```

In terminal 3, send the same request as the root README, with no client provider credential:

```sh
curl --fail-with-body http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Reply with the word pong"}]}'
curl --fail-with-body http://127.0.0.1:8001/requests
```

The first call returns HTTP 200 with `text` equal to `pong — deterministic upstream`, a request identifier and usage metadata.
The fake provider accepts the request only when the server sent the expected key; its record exposes accepted-key status and request content, never the header value.
Its `/requests` endpoint is a local test recorder and must only receive synthetic fixtures.
Stop both processes with Ctrl-C.

The demo binds loopback by default and has no developer authentication, TLS termination or production secret manager.
Do not expose this development service or the recorder to an untrusted network.

### Windows PowerShell

The commands above need a POSIX shell, such as Git Bash.
In PowerShell, set each variable with `$env:` and send the request with `Invoke-RestMethod`.

In terminal 1:

```powershell
$env:DEMO_PROVIDER_KEY = "gateway7-synthetic-demo-only"
uv run --locked python -m uvicorn demo.upstream:app --host 127.0.0.1 --port 8001
```

In terminal 2:

```powershell
$env:FAKE_LLM_API_KEY = "gateway7-synthetic-demo-only"
uv run --locked python -m gateway7 --config config/demo.yaml --host 127.0.0.1 --port 8000
```

In terminal 3:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/chat -Method Post -ContentType 'application/json' `
  -Body '{"messages":[{"role":"user","content":"Reply with the word pong"}]}'
Invoke-RestMethod http://127.0.0.1:8001/requests | ConvertTo-Json -Depth 6
```

Windows PowerShell 5.1 decodes the JSON as ISO-8859-1, so the dash in `pong — deterministic upstream` may display as `â€”`; PowerShell 7 shows it unchanged.

## Real Claude check

`config/claude.yaml` selects the Claude Messages adapter.
Supply `ANTHROPIC_API_KEY` privately in the shell or through your server's secret injection, then run:

```sh
uv run --locked python -m gateway7 --config config/claude.yaml --host 127.0.0.1 --port 8000
```

Send the README request and record whether it returns HTTP 200 with `pong`, ignoring case.
That actual provider call, with a valid account and model access, is [US-01](https://github.com/iteam7/gateway7/issues/30) / AC-05.
No such call was available during this implementation; offline adapter tests do not pass AC-05.
The config's model is an example and may need an authorized model available to your account.

The adapter uses `POST /v1/messages`, `x-api-key` and `anthropic-version` headers, and top-level system content as described in the [official Claude Messages reference](https://platform.claude.com/docs/en/api/messages/create), checked on 15 October 2026.
It performs one call, with no retries or failover.

## Checks and tests

```sh
uv run --locked python -m compileall -q gateway7 demo
uv run --locked pytest -q
uv run --locked python -m demo.run
```

The Python workflow runs the locked setup and checks on pull requests and `main`.
The existing Markdown and Lychee workflows remain separate documentation gates.
Neither a green local run nor an AI code review replaces the required human PR review, customer verdict or release.

Record `git rev-parse HEAD`, the OS/runtime versions and the command results with a clean-checkout run.
The fake demo checks the local plugin path; complete the separate real-provider check before claiming the whole US-01–03 core task passed.

### Known Windows verification limit

[Task #84](https://github.com/iteam7/gateway7/issues/84) describes an early Windows timer firing that a cancellation-suppressing plugin could previously bypass.
The middleware runner checks whether the timer expired before accepting a result or entering the next handler.
Linux regression coverage does not replace that task's repeated Windows verification; the proposed Windows CI remains in [PR #78](https://github.com/iteam7/gateway7/pull/78).

## Supported HTTP contract

`POST /chat` accepts a JSON object with `messages` and optional `max_tokens` from 1 to 4096.
Every message has a supported role (`system`, `user`, `assistant`) and plain-text `content`; unknown fields, tool calls, attachments and streaming are rejected.
`GET /health` is available once startup validation succeeds.
Safe errors include a request identifier and stable error code; they omit submitted input and arbitrary exception text.
The configured body and time limits bound normal cooperative work, not arbitrary trusted Python code.
