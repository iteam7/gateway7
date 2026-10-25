# Modular LLM Gateway — Team 7

Gateway7 applies company-authored Python middleware to messages and model answers.
Choose OpenAI, Anthropic Claude or Google Gemini in server configuration; clients authenticate with their own gateway token and can use only permitted models.
One ordered middleware list wraps the provider, with responses processed in reverse order.

The included policies mask phone numbers and email addresses, block or log literal policy matches, and redact response text.
The CLI, Docker image, Prometheus metrics and provisioned Grafana dashboard support a reproducible local pilot.

## Start with Docker Compose

```sh
docker compose up --build --detach --wait
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
curl --fail-with-body http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $GATEWAY7_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Contact synthetic@example.com or +7 999 123-45-67"}]}'
```

No provider account or provider API key is needed for this default synthetic mode.
The public token above authenticates only the local synthetic demo.
The response contains `[EMAIL]` and `[PHONE]` instead of the submitted fixtures.
Open Grafana at `http://127.0.0.1:3000/d/gateway7-overview` and Prometheus at `http://127.0.0.1:9090`.
Grafana is a local, read-only viewer with no administrator login.

Stop the stack with `docker compose down`; add `--volumes` only to discard its monitoring history.
The [setup guide](docs/setup.md#real-providers) covers real provider credentials and the Compose override.

## Run without Docker

Install Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
uv sync --locked
uv run --locked gateway7 demo
```

In another terminal:

```sh
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
uv run --locked gateway7 chat --message 'Contact synthetic@example.com; SECRET-TEST'
uv run --locked gateway7 validate --config config/openai.yaml
```

The [OpenAI SDK guide](docs/api.md) shows how existing clients can use `/v1/chat/completions`.

`demo` runs until Ctrl-C, starts its own private synthetic upstream and retains no input history.
`validate` checks provider configuration and trusted middleware without requiring a key or calling a provider.
The separate-process regression walkthrough remains available as `uv run --locked python -m demo.run`.

## Create a company middleware

```sh
uv run --locked gateway7 plugin init company_mask --directory .
uv run --locked gateway7 plugin test --config company_mask/gateway.yaml --fixtures company_mask/fixtures.json
```

The generated package includes request/response middleware and synthetic positive/negative fixtures.
The [authoring workflow](docs/authoring.md) covers ordinary installation, offline reports and deployment.

## Project guides

- [Setup, Docker and real providers](docs/setup.md)
- [CLI reference](docs/cli.md)
- [HTTP API and OpenAI SDK](docs/api.md)
- [Client authentication and model permissions](docs/authentication.md)
- [Middleware generator and offline tests](docs/authoring.md)
- [Reference middleware and policy coverage](docs/middleware-catalog.md)
- [Plugin authoring and API v2 migration](docs/plugins.md)
- [Metrics, Grafana and troubleshooting](docs/observability.md)
- [Customer demonstration](docs/demo.md)
- [Architecture](docs/architecture/README.md)
- [Documentation site](https://iteam7.github.io/gateway7/)
- [Contributing](CONTRIBUTING.md), [Definition of Done](docs/definition-of-done.md), [MIT license](LICENSE)

This ITPD project is a local pilot: one configured provider, authenticated text chat and trusted in-process middleware.
The default ports bind to localhost. A shared deployment needs TLS and a trusted boundary around its monitoring endpoints.
Offline adapter checks and the synthetic demo do not establish live-provider success or Customer acceptance.
