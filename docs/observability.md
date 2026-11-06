# Observability

The signals Gateway7 reports about its own operation, the service level indicators (SLIs) they define, and the pipelines that store them.
An operator reads the per-request log point and the SLI's aggregate in the observability backend of a deployed environment, and reads the local Prometheus and Grafana stack while developing.

## The Signals

Gateway7 emits two of the three [signal](glossary.md#signal) types: the metric and the log.
It emits no trace span.
No alert is defined; an alert would be a rule over one of these signals, not a signal of its own.

| Signal | What it carries | Emitted by | Where it goes |
| --- | --- | --- | --- |
| Metric `gateway7_request_duration_ms` | An OpenTelemetry histogram of each API request's duration in milliseconds, labelled `route` and `outcome` | `gateway` | The environment's OpenObserve organization over OTLP/HTTP, when [collection is on](#collected-data) |
| Log `gateway request` | One structured record per API request with `request_id`, `route`, `outcome`, `status`, `error_code` and `duration_ms` | `gateway` | The environment's OpenObserve organization over OTLP/HTTP, in the `gateway7_requests` log stream |
| Metrics `gateway7_*` | The Prometheus counters and histograms in the [metric contract](#metric-contract) | `gateway` | Scraped by the local `prometheus` container from `GET /metrics` |
| Log lines on standard output | Request, middleware and provider events with request IDs, component and outcome codes, and timings | `gateway` | `docker compose logs gateway` |

API requests are those on the `chat`, `openai_chat`, `models` and `other` routes; health checks and metric scrapes are not recorded as exported points.
One monotonic-clock measurement, from the gateway receiving the request to its response completing, feeds the exported log point, the exported histogram, the local log line and the Prometheus histogram, so the per-request point and the aggregate cannot disagree.

The `outcome` label takes one of four values: `ok` for HTTP 1xx–3xx, `client_error` for HTTP 4xx other than 499, `cancelled` for 499 (the caller disconnected), and `server_error` for HTTP 5xx.
The log record also carries the HTTP `status` and the gateway's fixed `error_code` from the [API error table](api.md#errors-and-operational-endpoints), or `none` for a successful request.

## The SLIs

An SLI is a quality signal the gateway emits and the observability pipeline records.
Its target is the `Response Measure` of the quality requirement whose test reads it; the SLI only records the measured signal.
SLI-01 is the one this sprint demonstrates, and [QR-05 QRT-01](quality-requirements/qr/QR-05.md#qrt-01) reads it against the staging organization.

### SLI-01

API request duration by route and outcome.

- **Status:** Active
- **Definition:** The five-minute P95 of the `gateway`'s API request duration, computed from the `gateway7_request_duration_ms` histogram labelled `route` (`chat`, `openai_chat`, `models` or `other`) and `outcome` (`ok`, `client_error`, `cancelled` or `server_error`); a failure appears as its own `client_error`, `cancelled` or `server_error` series.
  The per-request point is the `gateway request` log record, which identifies the request by `request_id`, the route by `route`, and the failure by `outcome`, `status` and `error_code`, and carries the same `duration_ms` the histogram records.
- **Unit:** Milliseconds.
- **Window:** Five minutes, evaluated at the query's time; the per-request log point is queryable in the environment's organization within five seconds of the response, and the histogram point follows within one minute.
- **Source:** The `gateway` records both from one measurement in its HTTP boundary middleware (`gateway7/telemetry.py`) and exports them with the OpenTelemetry SDK over OTLP/HTTP to OpenObserve: logs in batches every second and the histogram every ten seconds with delta temporality.
- **Query:** `histogram_quantile(0.95, sum by (le, route, outcome) (sum_over_time(gateway7_request_duration_ms_bucket{route=~"chat|openai_chat"}[5m])))`

The query selects the two chat routes, which carry the core task.
Each exported histogram point holds only the observations made since the previous export, so the query sums the points in the five-minute window instead of taking a `rate`; a series created by its first request therefore has a P95 at once.

The per-request log query, which [QR-05 QRT-01](quality-requirements/qr/QR-05.md#qrt-01) runs against the staging organization, selects the record by its identifier:

```sql
SELECT request_id, route, outcome, status, error_code, duration_ms
FROM "gateway7_requests"
WHERE request_id = '<request_id>'
```

The request identifier is the `X-Request-ID` response header, and the error body of a failed request carries the same value.

## The Pipeline

The `gateway` container exports both signals itself with the OpenTelemetry SDK over OTLP/HTTP; no collector or other container is added.
The log processor batches every 1 second and the metric reader exports every 10 seconds, which keeps the log point within the five-second and the histogram point within the one-minute bound of [SLI-01](#sli-01).
Both intervals can be changed with `OTEL_BLRP_SCHEDULE_DELAY` and `OTEL_METRIC_EXPORT_INTERVAL`, in milliseconds.

One OpenObserve instance on the university VM carries two organizations, `staging` and `production`, and each environment's gateway points at its own organization through its OTLP endpoint and its own credential.
The staging organization receives the test traffic; the production organization's dashboard runs the same query and is not exercised with test traffic.
Each exported point also carries the resource attribute `deployment.environment.name`, which the gateway sets from `GATEWAY7_ENVIRONMENT`.
The backend's retention must cover at least seven days, which covers the five-minute window and the per-request log point the test reads.
The backend, its dashboards and its query API are reachable from the university network only, and their addresses and credentials are in the private submission.

The gateway's configuration for the pipeline is in [the deployment guide](deployment.md#telemetry-pipelines); `.env.example` carries its shape, and the credentials are installed on the VM.

## The Dashboard

Each organization has its own dashboard with one chart, `SLI-01 API request P95 by outcome`, which runs the [SLI-01](#sli-01) query.
The page names the dashboards rather than linking them, because their addresses are private.

| Dashboard | Organization | What it runs |
| --- | --- | --- |
| `Gateway7 SLI (staging)` | `staging` | The SLI-01 query over the staging test traffic |
| `Gateway7 SLI (production)` | `production` | The same query over production traffic only |

## Collected Data

The exported log point collects the random request identifier, the fixed route name, the outcome, the HTTP status, the gateway's fixed error code and the duration.
The exported histogram collects the route, the outcome and the duration.
Both also carry the resource attributes `service.name`, `deployment.environment.name`, the SDK's name and version, and a random service instance identifier.

They never collect prompts, answers, message or tool content, policy terms, client names, client tokens, provider keys, model names, client IP addresses, user agents, URLs or upstream error text.
The request identifier is a random UUID generated by the gateway for each request; it is not derived from the client or the content and cannot be traced back to a person.

Collection is off unless `TELEMETRY_ENABLED=true`; with it unset or `false`, the gateway starts no exporter and sends nothing.
The exported data lives in the OpenObserve instance's storage on the university VM, outside the repository.

## Local metrics and Grafana

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

### What the dashboard shows

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

### Useful queries

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

### Diagnose a failing request

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

### Metric contract

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

#### Provider failure reasons

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

### Storage and verification

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
