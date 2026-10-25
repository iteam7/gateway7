# Metrics and Grafana

The Compose stack provisions Prometheus and a Grafana overview dashboard automatically.
Start it with `docker compose up --build --detach --wait`, then open `http://127.0.0.1:3000/d/gateway7-overview`.
Send requests with `gateway7 chat` or the README curl example; charts need at least two scrapes before a rate appears.
The default scrape/refresh interval is 5 seconds and the dashboard initially shows the last 15 minutes.

## What the dashboard shows

- Scrape availability, in-flight HTTP requests and completed provider calls.
- Chat throughput by status, policy denials, server failures and p95 request latency.
- Provider outcomes, p95 latency and reported input/output token throughput.
- Attempts with unknown token usage, kept separate from known token counters.
- Each configured middleware's request/response outcomes and p95 own-work duration.

The files live in `monitoring/grafana/dashboards/` and `monitoring/grafana/provisioning/`.
Grafana is an anonymous Viewer on localhost; there is no initial administrator or password to share.
Provisioned configuration is read-only in the UI. Edit the repository files and restart Grafana when changing datasource settings.
The datasource UID is `gateway7-prometheus`, the dashboard UID is `gateway7-overview`, and the Prometheus job is `gateway7`.

## Metric contract

`GET /metrics` exposes Prometheus text with one registry per application instance.
No labels contain prompts, answers, policy terms, credentials, URLs, request IDs or arbitrary client data.
Routes are mapped to the fixed names `chat`, `health`, `ready`, `metrics` and `other`; provider names and middleware names come from validated server configuration.

| Metric | Labels | Meaning |
| --- | --- | --- |
| `gateway7_http_requests_total` | `route`, `status` | Completed HTTP requests, including failures |
| `gateway7_http_request_duration_seconds` | `route` | Histogram of HTTP duration |
| `gateway7_http_requests_in_flight` | None | Active HTTP requests, including health/scrape traffic |
| `gateway7_provider_calls_total` | `provider`, `outcome` | Exactly one observation per attempted provider call |
| `gateway7_provider_duration_seconds` | `provider`, `outcome` | Histogram of provider attempt duration |
| `gateway7_provider_tokens_total` | `provider`, `direction` | Known reported token amounts; direction is `input` or `output` |
| `gateway7_provider_usage_unknown_total` | `provider` | Attempts without complete valid usage, including failed/cancelled attempts |
| `gateway7_middleware_steps_total` | `middleware`, `phase`, `outcome` | Own-work segments, including terminal failures |
| `gateway7_middleware_duration_seconds` | `middleware`, `phase` | Histogram of own work, excluding downstream waiting |

A request rejected before forwarding does not increment provider metrics.
A response rejected after forwarding still increments the provider call and any known token amounts: rejecting an answer cannot undo upstream work.
Missing usage is not invented as zero. A provider failure/cancellation can still consume tokens that were never returned to the gateway.
For Gemini, the output count includes reported thinking tokens when present, even though hidden thought content is not delivered.
These are operational counters, not a billing ledger; they reset when the gateway process restarts.

Middleware metrics count processing segments, not distinct HTTP requests.
An inner failure can give several outer middleware a `downstream_error` outcome; use HTTP `status="403"` for denied request counts instead of summing middleware denials.
Prometheus adds histogram `_bucket`, `_sum` and `_count` series and counter creation timestamps.
Before a labeled event has occurred its series may be absent; a blank chart is not proof of zero errors or zero cost.
The in-flight gauge includes the scrape request currently collecting it.

## Useful queries

Chat throughput by outcome:

```promql
sum by (status) (rate(gateway7_http_requests_total{route="chat"}[1m]))
```

Chat p95 latency in seconds:

```promql
histogram_quantile(0.95,
  sum by (le) (rate(gateway7_http_request_duration_seconds_bucket{route="chat"}[5m])))
```

Slow middleware phases, excluding the provider and nested handlers:

```promql
histogram_quantile(0.95,
  sum by (middleware, phase, le) (rate(gateway7_middleware_duration_seconds_bucket[5m])))
```

Unknown-usage attempts over five minutes:

```promql
sum by (provider) (increase(gateway7_provider_usage_unknown_total[5m]))
```

## Diagnose a failing request

1. Check `/ready`, then Prometheus `up{job="gateway7"}`. Readiness confirms successful local startup, not provider credentials or model access.
2. Look at the chat status series: 403 is a policy denial, 500 a middleware/internal failure, 502 a provider failure and 504 an overall deadline.
3. Compare provider latency with middleware own-work latency to locate the slow stage. Middleware awaiting the provider does not spend its own timeout budget on that wait.
4. Use the returned request ID to find gateway logs with `docker compose logs gateway`. Events contain only safe component/outcome codes and durations; the ID is not a metric label.

The configured provider HTTP timeout may fail before the overall request deadline; this is a provider error (502), not an automatic retry.
A failed or denied response can follow a completed provider attempt, so inspect both HTTP and provider metrics.
Do not log request bodies to diagnose policies; reproduce with synthetic fixtures instead.

## Storage and verification

Prometheus uses a named volume with a seven-day/512 MB retention cap; Grafana uses a separate named volume.
The default local stack does not send telemetry to a hosted monitoring service.
`docker compose down` preserves these volumes. `docker compose down --volumes` intentionally discards them.

`python scripts/smoke_compose.py` checks more than service health: it sends masked/redacted/denied synthetic requests, verifies provider call counts, checks privacy-safe metrics, and queries the provisioned Prometheus datasource through Grafana.
The Compose CI job builds the installed image and runs that smoke check on Ubuntu.
The Python tests cover metrics isolation, failures and token accounting without containers.

The configuration follows the [Prometheus configuration reference](https://prometheus.io/docs/prometheus/latest/configuration/configuration/), [Grafana provisioning guide](https://grafana.com/docs/grafana/latest/administration/provisioning/) and [Grafana configuration reference](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/).
