# Product analytics

Gateway7 records whether a chat task starts and whether its checked answer reaches the client, without collecting the conversation.
This page defines the metrics; [deployment](deployment.md#telemetry-pipelines) explains how to connect an environment's backend and build its charts.

## The Value And The Metrics

The focus metric is successful gateway tasks per week.
It expresses [VP-01](research/value-proposition.md#vp-01-predictable-local-preflight-for-small-teams): completing a conversation through the configured local policy pipeline.
A successful HTTP task is an observable proxy for that value; it does not prove detector accuracy, answer usefulness or absence of sensitive data.

### The Metric Tree

The bold label is the metric's level; the counter-metric guards the focus rather than feeding it.

- **Focus:** [Successful gateway tasks per week](#successful-gateway-tasks-per-week)
  - **L1 (counter-metric):** [Rejected and failed task share](#rejected-and-failed-task-share)
  - **L1:** [Task completion rate](#task-completion-rate)
    - **L2:** [Task starts per week](#task-starts-per-week)

### Why This Focus Metric

- **It expresses value:** a task counts when the gateway finishes its configured request and response checks and sends the full answer.
- **It represents the vision and strategy:** it counts use of the plugin host's core task rather than a provider call that may later be blocked.
- **It is a leading indicator:** sustained successful task use is available before longer-term retention or adoption evidence.
- **It is actionable:** configuration, middleware failures, model access and provider reliability can change completion.
- **It is understandable:** it counts completed chat tasks over the last seven days.
- **It is measurable:** the gateway emits one completion event, labelled with its result, for each chat request.
- **It is not a vanity metric:** requests that only reach a health endpoint, fail access checks or stop before answer delivery do not increase it.

Rejected as a vanity metric: repository stars, because attention to the source does not show anyone completing a task through Gateway7.

The focus depends on its inputs and on real traffic: it has no reported production value until the production pipeline is deployed and queried.
Synthetic fixtures validate the instrumentation and never establish adoption or a production metric value.

### Successful gateway tasks per week

- **Definition:** The number of `chat_completed` events with `outcome=ok` in the rolling seven-day window; unit: completed tasks per week.
- **Source:** [`chat_completed`](#the-events).
- **Query:** In the environment's OpenPanel project, use event `chat_completed`, aggregation `count`, property filter `outcome is ok`, property filter `source is not smoke`, property filter `source is not usability-test`, and date range `Last 7 days`.

Use event count, not unique profiles: `profileId` identifies a task, never a user.
A retry is a new task and may count again.

### Rejected and failed task share

- **Definition:** Completed task attempts whose outcome is not `ok`, divided by all completed task attempts in the same rolling seven days; unit: fraction, undefined when the denominator is zero.
- **Source:** [`chat_completed`](#the-events).
- **Query:** In OpenPanel, series `A` is `count(chat_completed)` with `outcome is not ok`; series `B` is `count(chat_completed)`; apply `source is not smoke` and `source is not usability-test` to both, set the date range to `Last 7 days`, and use formula `A/B`.

This includes policy denials, access failures, malformed requests, cancellations and server errors.
Read it by outcome before treating an increase as harm: a correct policy denial may be the intended result.

### Task completion rate

- **Definition:** Successful task completions divided by task starts in the same rolling seven days; unit: fraction, undefined when there are no starts.
- **Source:** [`chat_started` and `chat_completed`](#the-events).
- **Query:** In OpenPanel, series `A` is `count(chat_completed)` with `outcome is ok`; series `B` is `count(chat_started)`; apply `source is not smoke` and `source is not usability-test` to both, set the date range to `Last 7 days`, and use formula `A/B`.

The deployment guide records this exact chart recipe for both projects.
Backend computation has not been demonstrated in this change: a member must execute the chart against the deployed project and retain the result before reporting a measured value.
Starts and completions can straddle the window boundary, and process termination or best-effort export loss can leave an unmatched start; this is an event ratio rather than a cohort conversion rate.

### Task starts per week

- **Definition:** The number of `chat_started` events in the rolling seven-day window; unit: task attempts per week.
- **Source:** [`chat_started`](#the-events).
- **Query:** In the environment's OpenPanel project, use event `chat_started`, aggregation `count`, property filter `source is not smoke`, property filter `source is not usability-test`, and date range `Last 7 days`.

All four queries exclude `smoke` and `usability-test` traffic, so only `web` traffic contributes.
The deployment owns `source`; no request header or request body can change it.
`web` means ordinary API traffic, including SDK clients; it does not enable browser tracking.

## The Events

Names follow `object_action` in snake case.
The event registry below is the complete property allowlist.

| Event | Fires when | Fields | Collected at |
| --- | --- | --- | --- |
| `chat_started` | The gateway receives a request on `/chat`, `/v1/chat/completions` or `/v1/responses`, before authentication or validation. | `request_id` (random UUID hex, required), `route` (`chat`, `openai_chat` or `openai_responses`, required), `environment` (`staging` or `production`, required), `source` (`web`, `usability-test` or `smoke`, required), `participant_code` (optional canonical `P-01` through `P-999999`, staging usability traffic only), `occurred_at` (UTC ISO 8601, required), `__timestamp` (same timestamp, required by the queued transport) | `gateway`, staging and production |
| `chat_completed` | That request finishes, fails or is cancelled, after the final response body has been sent or the failure has been observed. | All `chat_started` fields; `status` (HTTP status integer, required), `outcome` (`ok`, `client_error`, `cancelled` or `server_error`, required), `duration_ms` (nonnegative finite number, required) | `gateway`, staging and production |

The shared `request_id` links the start and completion and is the same opaque identifier as the `X-Request-ID` response header.
OpenPanel receives it as `profileId` too, to group only this task's two events; the gateway creates no persistent user or client identity.
`__timestamp` preserves occurrence time while the event waits in the queue; it is OpenPanel's transport timestamp, not another user field.
Health probes, metrics scrapes, model listings and unrelated routes emit neither event.
An answer whose send times out or is interrupted is a failed or cancelled completion even if HTTP 200 headers were already sent.
If the process stops abruptly, a completion event may never be delivered.

## The Pipeline

The `gateway` container sends the typed events to self-hosted OpenPanel's HTTP `POST /track` API using the existing HTTP client.
The deployment target is one backend with separate `staging` and `production` projects, each with its own write client ID and secret; neither the backend's deployment nor its chart results are certified by the local protocol tests.
Configure retention to at least seven days, matching the longest metric window.
The backend's deployment steps, project creation and chart recipe are in [telemetry pipelines](deployment.md#telemetry-pipelines).

Collection is off by default and is disabled with `ANALYTICS_ENABLED=false`.
When enabled, startup requires the environment, API base, client ID and secret; invalid or incomplete settings stop startup without echoing their values.
`ANALYTICS_SOURCE` is server configuration, defaults to `web` and changes on restart.
Only staging accepts `smoke` or `usability-test`; production refuses to start with either source, so pipeline checks must target staging.
The optional server setting `ANALYTICS_PARTICIPANT_CODE` is accepted only with staging and `source=usability-test`.
Its canonical format is `P-` followed by a positive number padded to at least two digits and at most six digits, without redundant leading zeros (`P-01`, `P-10`, `P-100`; not `P-00` or `P-001`).
When unset, neither event contains `participant_code`; an empty or invalid configured value stops enabled analytics startup without echoing the value.
Clients cannot supply or override it through headers or request bodies.
The configured credentials still determine the destination project: a member must verify project isolation before sending the first smoke request.

Delivery uses a 256-event in-memory queue and one background worker, with a one-second HTTP timeout and no retries or redirects.
A full queue or failed export drops that event and writes a fixed diagnostic without backend text or credentials.
Requests never wait for delivery; shutdown drains for at most two seconds and then discards the remainder, with a separate one-second bound on closing the HTTP client.
A prolonged backend outage can undercount events, so these metrics are not an audit or billing ledger.

## The Dashboard

The intended dashboards are `Gateway7 tasks (staging)` and `Gateway7 tasks (production)`, in their corresponding projects.
Each uses the [Task completion rate](#task-completion-rate) formula and its exact seven-day filters that exclude `smoke` and `usability-test` traffic.
The staging project's raw event list must show the smoke events while its metric chart excludes them; the production chart uses the same recipe and receives no pipeline-check traffic.
Both backend and dashboard addresses and credentials belong in the private submission.
The Week 6 report needs sanitized screenshots after a member actually provisions and checks these dashboards.

## The Usability Funnel

A usability session's events carry `source=usability-test` and are read in the staging project through that filter alone.
The server-configured `participant_code`, session time window and `X-Request-ID` values the observer records link the task events to the coded observation record.
The code is not an identity, and the code-to-person mapping remains only in private usability storage.
It is never a Prometheus label, log field or OpenPanel `profileId`; that identifier remains the per-task random request identifier.
The funnel's counts are test records, not product values, and never appear in the focus metric or its three companion metrics.

The setup isolates the participant's staging run, sets `ANALYTICS_SOURCE=usability-test` and `ANALYTICS_PARTICIPANT_CODE` to the assigned code, and recreates the gateway before the session.
Reset the synthetic seed before each participant, capture only that code's session window from the staging OpenPanel project, then unset the code and restore `source=web` by recreating the gateway before ordinary traffic resumes.
Changing the operator's shell variables alone does not change a running gateway.
The raw export stays in the private usability-data repository, and the funnel covers only the flows the gateway's own events record; the observer records the rest.
Local synthetic tests verify the event contract and exporter, not the deployed project's code filters, retention, access or session outcomes.

## Collected Data

Events carry only the task identifier, fixed route, environment and source, optional staging-usability participant code, event time, completion status, fixed outcome and duration from [the registry](#the-events).
They never carry prompts, answers, tool content, policy terms, client names, model names, credentials, IP addresses, client user agents, URLs or free-text errors.
The exporter sends a fixed SDK user agent and never forwards the caller's IP or headers.
Data is stored by OpenPanel outside the repository; disable export with `ANALYTICS_ENABLED=false` and use the backend's retention controls to remove old data.

The wire format follows the [OpenPanel track API](https://openpanel.dev/docs/api/track) and its [public 2.x schema](https://github.com/Openpanel-dev/openpanel/blob/cd24bb838301df1a9087e2e132b344e5b8a99963/packages/validation/src/track.validation.ts).
