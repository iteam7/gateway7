# Gateway7

<!-- Preserve links to the previous page heading. -->
<!-- markdownlint-disable MD033 -->
<div id="modular-llm-gateway--team-7"></div>
<!-- markdownlint-enable MD033 -->

**Add your team's policies between an application and an LLM.**
Gateway7 keeps provider keys on the server, checks each client's model access, and runs your Python middleware on requests and answers.
Use OpenAI, Claude or Gemini through one configured provider per instance.

## Start with Docker Compose

With Git, curl and Docker Compose v2 installed:

```sh
git clone https://github.com/iteam7/gateway7.git
cd gateway7
docker compose up --build --detach --wait
curl --fail-with-body http://127.0.0.1:8000/chat \
  -H 'Authorization: Bearer gateway7-synthetic-client-token' \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Contact synthetic@example.com; SECRET-TEST"}]}'
```

The answer contains `[EMAIL]` and `[removed]`.
This local demo uses a synthetic provider and a public demo token; no provider account or API key is needed.
Open `http://127.0.0.1:3000/d/gateway7-overview` for Grafana, then stop with `docker compose down`.
The [quickstart](docs/quickstart.md) explains the result, ports and cleanup.

## Run without Docker

Use Python 3.12 and uv: `uv sync --locked`, then `uv run --locked gateway7 demo`.
Follow [Python setup](docs/setup.md#install-from-a-checkout) for a complete first request.

## Create a company middleware

Generate a small Python package, test it with offline fixtures, then install it and restart the gateway.
The [authoring guide](docs/authoring.md) walks through each command.

## Project guides

| I want to… | Start here |
| --- | --- |
| Connect an application with curl or the OpenAI SDK | [HTTP API](docs/api.md) |
| Give clients tokens and model permissions | [Client access](docs/authentication.md) |
| Mask personal data or block a request | [Policy examples](docs/middleware-catalog.md) |
| Use a real provider and run the service | [Setup](docs/setup.md#real-providers) · [Monitoring](docs/observability.md) |

Gateway7 supports nonstreaming text chat and trusted, in-process middleware.
One ordered chain handles requests; answers pass through it in reverse.
For shared use, configure TLS and protect the anonymous monitoring endpoints.

[Documentation](https://iteam7.github.io/gateway7/) · [Architecture](docs/architecture/README.md) · [Product vision](docs/product-vision.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
