# Metrics and Grafana

After the [quickstart](quickstart.md), open `http://127.0.0.1:3000/d/gateway7-overview` for the Gateway7 overview.
Send a few synthetic requests to see their HTTP results, provider calls and middleware timings.
Prometheus collects data every five seconds; rate charts need at least two samples.
The dashboard refreshes every five seconds and starts with the last 15 minutes.

Check the gateway directly from a terminal:

```sh
curl --fail --silent --show-error http://127.0.0.1:8000/ready
curl --fail --silent --show-error http://127.0.0.1:8000/metrics
```

Readiness means local startup succeeded; it does not test provider credentials or model access.
Metrics and health endpoints have no authentication, so keep them on a trusted network.

## What the dashboard shows

| Question | Panels to check |
| --- | --- |
| Can Prometheus reach the gateway? | Gateway scrape availability |
| Are requests succeeding or being denied? | Chat requests by HTTP status; access denials, policy denials and server failures |
| Where is time spent? | Chat p95 latency; provider p95 latency; middleware p95 own-work duration |
| Did a provider call happen? | Completed provider calls; provider call outcomes |
| What usage was reported? | Reported token throughput; calls with unknown usage |
| Which middleware stopped processing? | Middleware outcomes |

The local Grafana instance allows anonymous Viewer access and has no initial administrator.
The dashboard and datasource come from `monitoring/grafana/dashboards/` and `monitoring/grafana/provisioning/`.
Edit those files to change the setup; restart Grafana after changing datasource settings.
The datasource UID is `gateway7-prometheus`, the dashboard UID is `gateway7-overview`, and the Prometheus job is `gateway7`.

## Useful queries

Open `http://127.0.0.1:9090` for Prometheus and paste one query at a time.
A missing series can mean that the event has not happened yet; it does not prove zero errors or zero cost.

Is the last gateway scrape healthy? Expect `1`:

```promql
up{job="gateway7"}
```

Chat requests per second, by HTTP status, across both APIs:

```promql
sum by (status) (rate(gateway7_http_requests_total{route=~"chat|openai_chat"}[1m]))
```

Chat p95 latency in seconds, below which about 95% of requests fall:

```promql
histogram_quantile(0.95,
  sum by (le) (rate(gateway7_http_request_duration_seconds_bucket{route=~"chat|openai_chat"}[5m])))
```

Middleware p95 work time, excluding waits for nested handlers and the provider:

```promql
histogram_quantile(0.95,
  sum by (middleware, phase, le) (rate(gateway7_middleware_duration_seconds_bucket[5m])))
```

Capacity rejections per second:

```promql
rate(gateway7_admission_rejections_total[5m])
```

Compare this with `gateway7_active_pipelines` and the configured per-process limit, which defaults to 64.
These two metrics are available in Prometheus; the shipped dashboard has no separate capacity panel.

Provider failures by safe category over five minutes:

```promql
sum by (provider, reason) (increase(gateway7_provider_errors_total[5m]))
```

Attempts with unknown token usage over five minutes:

```promql
sum by (provider) (increase(gateway7_provider_usage_unknown_total[5m]))
```

## Diagnose a failing request

1. Check `/ready`, then `up{job="gateway7"}` to separate gateway startup from a scrape problem.
2. Find the request's HTTP status in the table below.
3. Compare provider latency with middleware work time; these measure different parts of the request.
4. For a 502, inspect the provider `reason` counter and use the returned request ID to find the matching gateway log event.

```sh
docker compose logs --tail=100 gateway
```

For the live override, use `docker compose -f compose.yaml -f compose.live.yaml logs --tail=100 gateway`.
Gateway events include request IDs, component/outcome codes and timings.
Provider failure events also include a fixed `reason` value.
Request IDs stay in logs and response headers/bodies; they are not metric labels.

| HTTP status | What to check |
| --- | --- |
| `401` | Missing or invalid gateway client token |
| `403` | Client model access or a middleware policy denial |
| `500` | Middleware failure or an internal error |
| `502` | Provider failure; inspect the safe reason below |
| `503` | Gateway not ready, or all pipeline slots busy (`overloaded`) |
| `504` | Whole-request deadline reached |

Reproduce policy problems with synthetic fixtures instead of logging real message bodies.
A denied response may follow a completed provider call, so check both HTTP and provider metrics.

## Metric contract

`GET /metrics` exports Prometheus text, with a separate registry for each application instance.
Labels contain no prompts, answers, policy terms, credentials, URLs, request IDs, client names or model IDs.
Routes use the fixed names `chat`, `openai_chat`, `models`, `health`, `ready`, `metrics` and `other`.
Provider and middleware names come from validated server configuration.

| Metric | Labels | Meaning |
| --- | --- | --- |
| `gateway7_http_requests_total` | `route`, `status` | Completed HTTP requests, including failures |
| `gateway7_http_request_duration_seconds` | `route` | Histogram of HTTP duration |
| `gateway7_http_requests_in_flight` | None | Active HTTP requests, including health checks and the current scrape |
| `gateway7_active_pipelines` | None | Pipeline tasks still running, including cancellation cleanup |
| `gateway7_admission_rejections_total` | None | Requests refused because pipeline capacity is full |
| `gateway7_provider_calls_total` | `provider`, `outcome` | One observation per provider attempt |
| `gateway7_provider_duration_seconds` | `provider`, `outcome` | Histogram of provider attempt duration |
| `gateway7_provider_errors_total` | `provider`, `reason` | Failed attempts by safe reason; excludes cancellation |
| `gateway7_provider_tokens_total` | `provider`, `direction` | Known reported tokens; direction is `input` or `output` |
| `gateway7_provider_usage_unknown_total` | `provider` | Attempts without complete valid usage |
| `gateway7_middleware_steps_total` | `middleware`, `phase`, `outcome` | Middleware processing segments, including failures |
| `gateway7_middleware_duration_seconds` | `middleware`, `phase` | Histogram of middleware work, excluding downstream waits |

Histograms also expose `_bucket`, `_sum` and `_count` series.
Counters reset when the gateway process restarts.
The active-pipeline gauge drops only when a task finishes: a plugin that ignores cancellation still holds its capacity slot.
Health and scrape requests do not use pipeline slots.
The rejection counter separates a capacity-related 503 from a not-ready 503.

Middleware metrics count processing segments, not distinct requests.
One inner failure can give several outer middleware a `downstream_error` result.
Use HTTP 403 counts for combined policy/model denials instead of adding middleware failure counts.

A request denied before forwarding adds no provider attempt.
A response denied after forwarding still counts the call and any known token usage.
Complete valid usage from a decoded HTTP 200 response is counted even when answer validation then fails.
The client still gets a safe 502 without the rejected answer or its usage fields.
HTTP error bodies and incomplete or undecodable responses supply no usage.

Both token counts must be integers from 0 through 2^63−1.
Missing, incomplete, boolean, negative, fractional or overflowing counts stay unknown; reported `0/0` is known usage.
For Gemini, output usage includes reported thinking tokens even though hidden thoughts are not delivered.
A failed or canceled call can still cost tokens that the gateway never receives in a usage report.
Treat these metrics as operational observations, not a billing ledger.

### Provider failure reasons

All provider failures keep the public HTTP 502 / `provider_error` response.
The failure counter and log event use only these fixed reasons:

| Reason | Observed condition |
| --- | --- |
| `authentication` | Provider HTTP 401 or 403, including permission failures |
| `rate_limit` | Provider HTTP 429 |
| `timeout` | Provider connect, read, write or pool timeout |
| `unavailable` | Provider HTTP 500–599 |
| `transport` | Another connection or protocol failure |
| `invalid_response` | Malformed, oversized, incorrectly encoded or unsupported response |
| `rejected` | Another status instead of the expected HTTP 200, including redirects |
| `unknown` | Unexpected adapter failure or unrecognized reason |

These categories describe observations, not the provider's underlying cause.
Logs and metrics do not expose upstream error bodies, exception strings, headers or URLs.
No category triggers a retry or fallback.
A provider timeout returns 502; a whole-request deadline returns 504.
If a provider call is active when the gateway deadline or caller cancellation occurs, its outcome is `cancelled` and the failure counter is not incremented.

## Storage and verification

Prometheus keeps data in a named volume, bounded by seven days and 512 MB.
Grafana uses a separate named volume for its state.
The default stack sends no telemetry to a hosted monitoring service.
`docker compose down` keeps these volumes; `docker compose down --volumes` deletes them.

With the default synthetic stack running, use:

```sh
python scripts/smoke_compose.py
```

This checks client/model access, both chat APIs, masking and denial, provider-call counts, metrics, scraping and the Grafana datasource query path.
The Compose CI job builds the image and runs this check on Ubuntu.
The Python tests cover metric behavior without containers.

For changes to monitoring configuration, see the official [Prometheus reference](https://prometheus.io/docs/prometheus/latest/configuration/configuration/) and [Grafana provisioning guide](https://grafana.com/docs/grafana/latest/administration/provisioning/).
