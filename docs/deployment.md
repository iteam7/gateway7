# Deploy to the university VM

This page covers the shared deployment environments and the manual process for promoting a commit to them.
Use [setup](setup.md) for installing and configuring Gateway7 itself; this page only adds what changes for a shared, campus-network deployment.

## Environments

| Environment | Where it runs | Who reaches it | Purpose |
| --- | --- | --- | --- |
| Development | A contributor's own machine | The contributor | Local checkout, `gateway7 demo`, tests |
| Integration | GitHub Actions | CI only | The checks in [AGENTS.md](https://github.com/iteam7/gateway7/blob/main/AGENTS.md#checks) on every pull request and push to `main` |
| Staging | University VM, a dedicated directory and Compose project | Team members on the campus network | First deployment target for a candidate commit; where an implemented quality requirement test (QRT) is exercised before release |
| Production | Same university VM, a separate directory and Compose project | Team members on the campus network | Deployment target after staging passes verification |

Staging and production are two independent Compose deployments on the same VM, each in its own checkout directory and its own `docker compose` project name, so their containers, networks and named volumes never overlap.
On 31 October, azamatbayramov clarified that HTTP access from the university network is available.
This is a team-reported operational fact; no independent network probe is claimed here.
The tracked Compose defaults bind services to loopback, which can be reached through SSH forwarding; those defaults alone do not establish direct campus access to a deployed environment.
The operator verifies the deployed network configuration and records the actual campus endpoints in the private submission.
Staging and production use different host ports for the same three services (gateway, Prometheus, Grafana), so both can run at once without a collision.

## Configuration and secrets

Each environment has its own checkout, so it has its own copy of `compose.yaml`.
A real-provider deployment also needs its own `GATEWAY_CONFIG_FILE`, `GATEWAY_KEY_ENV` value and provider key, supplied the same way as in [setup.md#supply-server-credentials](setup.md#supply-server-credentials) — read into the shell on the VM, never committed, never echoed into a log.
Staging and production must not share a client token or a provider key.

`.env.example` and this page describe only the shape of that configuration (file names, variable names, port numbers).
The actual VM hostname/address, its login credentials, and any deployed provider key are kept off this page, out of commit messages and out of `.agents-log.md`; evidence for a deployment cites the commit that was deployed, not where it was deployed.

## Manual deployment

Deployment is a manual operator action, run from a terminal with access to the VM; it is intentionally outside the product CI (`.github/workflows/`), per the course deployment rules.

1. Identify the candidate commit (normally the tip of `main` after its checks pass).
2. On the VM, in the staging checkout directory, fetch and check out that commit, then run:

   ```sh
   docker compose -p gateway7-staging up --build --detach --wait
   ```

3. Run the core-task check against staging from a campus machine using its deployed HTTP endpoint (a chat request plus `/health`); record the result.
4. Run the deployed quality requirement tests [QR-03 QRT-02](quality-requirements/qr/QR-03.md#qrt-02) and [QR-05 QRT-01](quality-requirements/qr/QR-05.md#qrt-01) against staging.
5. Only once staging passes, check out the same commit in the production checkout directory and repeat the `docker compose up --build --detach --wait` for the `gateway7-production` project.
6. Run the same core-task check against production over the campus network.
7. If any rework lands the same week, redeploy the updated commit to staging, reverify, then repeat the promotion to production before release.

## Verification

A deployment counts as verified once, for that environment:

- `docker compose ps` shows the `gateway`, `prometheus` and `grafana` containers `healthy`.
- `GET /health` on the gateway's published port returns `{"status":"ok"}`.
- A chat request against the gateway's published port, with a valid client token, returns a successful completion.
- For staging, [QR-03 QRT-02](quality-requirements/qr/QR-03.md#qrt-02) and [QR-05 QRT-01](quality-requirements/qr/QR-05.md#qrt-01) pass.

## Rollback

Staging and production keep their named Compose volumes (`prometheus-data`, `grafana-data`) independent of which commit is checked out, so a rollback does not lose monitoring history.
If production verification fails after a promotion:

1. In the production checkout directory, check out the last known-good commit (the one most recently verified in production).
2. Re-run `docker compose -p gateway7-production up --build --detach --wait` to rebuild and restart the containers on that commit.
3. Repeat the verification steps above against production.
4. Record the failed commit, the rollback target commit and the reason in the deployment evidence; do not retry the failed commit in production until the underlying issue is fixed and it has passed staging again.

Staging is never the rollback target for production; it always moves independently to the next candidate commit.

## Telemetry pipelines

The gateway pushes the observability signals described in the [observability plan](observability.md) when collection is enabled; collection stays off on a developer's machine and in CI.

### Observability pipeline

The OpenObserve instance on the VM needs one organization per environment, `staging` and `production`, an ingestion credential for each organization, and a retention of at least seven days.
Each environment's gateway then receives its own values for these variables through the live Compose file, in the same way as its provider key:

| Variable | Staging value | Production value |
| --- | --- | --- |
| `TELEMETRY_ENABLED` | `true` | `true` |
| `GATEWAY7_ENVIRONMENT` | `staging` | `production` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | The OpenObserve address followed by `/api/staging` | The OpenObserve address followed by `/api/production` |
| `OTEL_EXPORTER_OTLP_HEADERS` | `Authorization=Basic%20<base64 of user:token>,stream-name=gateway7_requests` with the staging credential | The same shape with the production credential |

The OpenTelemetry exporter appends `/v1/logs` and `/v1/metrics` to the endpoint, and `%20` is the encoded space after `Basic`.
`stream-name` places the per-request log records in the `gateway7_requests` log stream; the histogram streams are named after the metric.
The log processor batches every 1,000 ms and the metric reader exports every 10,000 ms; `OTEL_BLRP_SCHEDULE_DELAY` and `OTEL_METRIC_EXPORT_INTERVAL` change them, in milliseconds.
With `TELEMETRY_ENABLED=true`, the gateway refuses to start until `GATEWAY7_ENVIRONMENT` is `staging` or `production` and the endpoint is set, so a deployment cannot silently send nothing or report under the wrong environment.

The query API used by the diagnosability check is the same organization's OpenObserve address: `_search` for the log query and `prometheus/api/v1/query` for the SLI query.
The OpenObserve address, the ingestion and query credentials and the dashboard addresses are private-only: they are installed on the VM and recorded in the private submission, never in this repository.
When the backend is unreachable, requests are served unchanged and the exporter writes a retry warning naming the backend host and signal path to the gateway's own log; it never writes the credential header.
