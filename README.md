# Gateway7

<!-- Preserve links to the previous page heading. -->
<!-- markdownlint-disable MD033 -->
<div id="modular-llm-gateway--team-7"></div>
<!-- markdownlint-enable MD033 -->

**Add your team's policies between an application and an LLM.**
Gateway7 keeps provider keys on the server, checks each client's model access, and runs your Python middleware on requests and answers.
Use OpenAI, Claude or Gemini through one configured provider per instance.

## Start with Docker Compose

With Git and Docker Compose v2 installed, copy the OpenAI environment template:

```sh
git clone https://github.com/iteam7/gateway7.git
cd gateway7
cp -n .env.example .env
chmod 600 .env
```

In `.env`, fill in `OPENAI_API_KEY` and a different random `GATEWAY7_CLIENT_TOKEN` of 16–512 visible ASCII characters, without spaces.
The template already selects OpenAI and the reference middleware; no exports or YAML edits are needed.

```sh
docker compose up --build --detach --wait
docker compose exec -T gateway gateway7 smoke --token-env GATEWAY7_CLIENT_TOKEN
```

The smoke makes at most one short, potentially billable model request and reports status and token usage without printing the answer or secrets.
The sample uses `gpt-4.1-mini`; your OpenAI account must have access to it.
Open `http://127.0.0.1:3000/d/gateway7-overview` for Grafana, then stop with `docker compose down`.
The [setup guide](docs/setup.md#real-providers) covers environment precedence, other providers and proxies.
Keep `.env` private; it is ignored by Git and excluded from the image build.

## Try without a provider account

From the checkout, start the synthetic demo explicitly:

```sh
docker compose -f compose.yaml up --build --detach --wait
curl --fail-with-body http://127.0.0.1:8000/chat \
  -H 'Authorization: Bearer gateway7-synthetic-client-token' \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Contact synthetic@example.com; SECRET-TEST"}]}'
```

The answer contains `[EMAIL]` and `[removed]`.
This local demo uses a synthetic provider and a public demo token; no provider account or API key is needed.
The explicit `-f compose.yaml` selects the demo even if `.env` selects OpenAI.
Stop it with `docker compose -f compose.yaml down`.
The [quickstart](docs/quickstart.md) explains the result, ports and cleanup.

## Run without Docker

Use Python 3.12 and uv: `uv sync --locked`, then `uv run --locked gateway7 demo`.
Follow [Python setup](docs/setup.md#install-from-a-checkout) for a complete first request.

## Create a company middleware

With the reviewed Gateway7 build active, work in a separate folder:

```sh
gateway7 plugin init company_guard --template guard
gateway7 plugin test company_guard
gateway7 plugin dev company_guard
```

Expect 12 passing synthetic cases, then a loopback URL and a ready-to-run client command.
Ctrl-C stops the gateway and its synthetic upstream.
The generated package includes strict settings, typed multi-profile fixtures, unit checks and local agent instructions.
Use the [first-plugin guide](docs/authoring.md), [cookbook](docs/plugin-cookbook.md) and [agent workflow](docs/plugin-agent-guide.md), then build a normal wheel for deployment.

## Project guides

| I want to… | Start here |
| --- | --- |
| Connect an application with curl or the OpenAI SDK | [HTTP API](docs/api.md) |
| Give clients tokens and model permissions | [Client access](docs/authentication.md) |
| Create administrator logins and build text policies without code | [Administration workspace](docs/admin-controls.md) |
| Mask personal data or block a request | [Policy examples](docs/middleware-catalog.md) |
| Use a real provider and run the service | [Setup](docs/setup.md#real-providers) · [Monitoring](docs/observability.md) |

Gateway7 supports nonstreaming text chat and trusted, in-process middleware.
One ordered chain handles requests; answers pass through it in reverse.
For shared use, configure TLS and protect the anonymous monitoring endpoints.

[Documentation](https://iteam7.github.io/gateway7/) · [Architecture](docs/architecture/README.md) · [Product vision](docs/product-vision.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
