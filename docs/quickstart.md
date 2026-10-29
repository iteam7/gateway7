# Quickstart

Send a request through Gateway7, see text changed by middleware, and open the monitoring dashboard.
Allow about five minutes once the tools and container images are available; the first download and build can take longer.
This demo uses a local synthetic provider, so you need no provider account or API key.

## Before you start

Install Git, Docker with Compose v2, and curl.
The commands below use Bash on Linux, macOS or Windows with WSL.
Ports 8000, 9090 and 3000 must be free.
For a Python-only run, use [Install from a checkout](setup.md#install-from-a-checkout).

## Start Gateway7

```sh
git clone https://github.com/iteam7/gateway7.git
cd gateway7
docker compose -f compose.yaml up --build --detach --wait
```

This starts Gateway7, Prometheus and Grafana on your computer.
The explicit Compose file keeps this demo synthetic even if you have a `.env` file for [OpenAI](setup.md#real-providers).
Check that the gateway is ready:

```sh
curl --fail --silent --show-error http://127.0.0.1:8000/ready
```

Expect HTTP 200 and `{"status":"ready"}`.

## Send your first request

The token below is a public demo value, not a real credential.

```sh
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
curl --fail-with-body --silent --show-error http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $GATEWAY7_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Contact synthetic@example.com or +7 999 123-45-67; SECRET-TEST"}]}'
```

The response includes:

```json
{
  "text": "pong — Contact [EMAIL] or [PHONE]; [removed]",
  "usage": {"input_tokens": 12, "output_tokens": 4}
}
```

It also includes a generated `request_id` for finding the request in gateway logs.
Phone and email middleware changed the request before forwarding it.
Response middleware replaced `SECRET-TEST` in the answer.
The synthetic provider returns fixed token counts; this run makes no paid model call.

## Open the dashboard

Open `http://127.0.0.1:3000/d/gateway7-overview` in your browser for the Gateway7 overview.
No login is needed for this local, read-only dashboard.
Prometheus collects data every five seconds.
Send the request again after two collections to see request rates and latency charts.
See [Metrics and Grafana](observability.md) for queries and troubleshooting.

## Stop the demo

```sh
docker compose -f compose.yaml down
```

This keeps the monitoring history.
Use `docker compose -f compose.yaml down --volumes` when you also want to delete that local history.

## Next steps

- [Connect an application](api.md) through the native API or OpenAI SDK.
- [Use a real provider](setup.md#real-providers) with server-held credentials.
- [Create your own middleware](authoring.md) and test it with synthetic examples.
- [Explore the reference middleware](middleware-catalog.md) for masking, blocking and response checks.
