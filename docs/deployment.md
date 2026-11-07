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
2. On the VM, in the staging checkout directory, fetch and check out that commit.
   Build from clean tracked sources, with private configuration supplied separately, then recreate the selected stack and verify the running image's revision:

   ```bash
   set -euo pipefail
   test -z "$(git status --porcelain)"
   DEPLOYED_COMMIT=$(git rev-parse HEAD)
   image=$(docker compose -p gateway7-staging config --format json |
     python3 -c 'import json, sys; print(json.load(sys.stdin)["services"]["gateway"]["image"])')
   docker build --pull --no-cache \
     --label "org.opencontainers.image.revision=$DEPLOYED_COMMIT" \
     --tag "$image" .
   docker compose -p gateway7-staging up --no-build --force-recreate --detach --wait
   container=$(docker compose -p gateway7-staging ps -q gateway)
   running_image=$(docker inspect --format '{{.Image}}' "$container")
   test "$running_image" = "$(docker image inspect --format '{{.Id}}' "$image")"
   test "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$running_image")" = "$DEPLOYED_COMMIT"
   printf 'Verified deployment: %s\nImage: %s\n' "$DEPLOYED_COMMIT" "$running_image"
   ```

   Keep `DEPLOYED_COMMIT` and the running image ID with the verification result; a checkout's `HEAD` alone does not identify an already running container.
3. Run the core-task check against staging from a campus machine using its deployed HTTP endpoint (a chat request plus `/health`); record the result.
4. Run the deployed quality requirement tests [QR-03 QRT-02](quality-requirements/qr/QR-03.md#qrt-02) and [QR-05 QRT-01](quality-requirements/qr/QR-05.md#qrt-01) against staging.
5. Only once staging passes, check out the same commit in the production checkout directory and repeat the build, recreation and image-revision verification above with the `gateway7-production` project; keep production's analytics source `web`.
6. Check production readiness and its selected configuration over the campus network, then verify the core task from real traffic.
   With analytics enabled, keep synthetic requests and smoke tools on staging so production receives no test events.
7. If any rework lands the same week, redeploy the updated commit to staging, reverify, then repeat the promotion to production before release.

## Verification

A deployment counts as verified once, for that environment:

- `docker compose ps` shows the `gateway`, `prometheus` and `grafana` containers `healthy`.
- `GET /health` on the gateway's published port returns `{"status":"ok"}`.
- A chat request against the gateway's published port, with a valid client token, returns a successful completion; use a synthetic task on staging and real traffic in production when analytics is enabled.
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

The [analytics plan](analytics.md) owns product events and metric queries; the [observability plan](observability.md) owns operational signals and SLI queries.
Both exporters are optional and off by default.
The following is a deployment runbook, not evidence that the telemetry backends or dashboards have been deployed.
A completed deployment records its commit, verification output and sanitized dashboard screenshots in the current week's report.

### Prepare the backends

Run one backend instance of each kind, with separate `staging` and `production` scopes and credentials.
The backends stay outside the product boundary: Gateway7 must keep serving when either is unavailable.
Keep their listeners and query access on the university network; use a campus reverse proxy or SSH forwarding for the loopback defaults.

**OpenPanel:** use the public 2.x [upstream setup](https://openpanel.dev/docs/self-hosting/v2/get-started), in a separate directory outside the Gateway7 repository:

```sh
git clone --branch self-hosting https://github.com/Openpanel-dev/openpanel.git gateway7-openpanel
cd gateway7-openpanel
git checkout cd24bb838301df1a9087e2e132b344e5b8a99963
cd self-hosting
umask 077
./setup
docker compose -p gateway7-openpanel config --quiet
docker compose -p gateway7-openpanel up --detach --wait
```

Use an installed Docker/Node toolchain, the campus-only backend address, and one worker in the setup prompts.
Restrict the generated proxy listener to campus access before starting it.
The pinned setup includes its database migrations and storage services; keep its generated `.env` and credentials outside the product checkout.
The upstream application's `:2` image tags can move: before deployment, record the pulled image digests privately and pin those digests in the generated Compose file for repeatable restarts.
Create two projects named `staging` and `production`, with a different write client and read client in each.
Retain events for at least seven days and use UTC for both projects.

On 7 November, one OpenPanel 2.x stack was started in the VM's private operator directory with the above pinned upstream configuration, one worker and locally pinned image digests.
Its database, Redis, ClickHouse, API, dashboard and worker reported healthy; the backend proxy binds to loopback.
An additional TLS proxy exposes both telemetry backends on the university-network interface; its private operator directory contains an internal CA certificate for clients to trust and its private key stays on the VM.
The operator and a team member on Windows verified both health endpoints with certificate verification enabled; Customer access is not yet verified.
The stack has separate `staging` and `production` projects with different write clients, registration disabled after creating the operator, and its bootstrap and project credentials stored in a root-only file outside the repository.
The operator generated the Compose file from the pinned templates without installing Node on the VM, set a unique database password and cookie secret, and restricted the backend containers' memory.
The deployed OpenPanel retention policy has not yet been verified against the seven-day metric window.
The dashboard's server-side API address points to the API container, while its public API address uses the campus TLS proxy.
The deployed dashboard image logged its process environment during server-side rendering, so the operator rotated the database and cookie secrets and disabled Docker log persistence for that dashboard container.
The private Compose file and named volumes are the running configuration; do not replace or delete them while promoting a gateway.

An isolated staging preview built from commit `22ecc152f57ad096cd942050cd46d6d3457fb93d` used the staging write client with `ANALYTICS_SOURCE=smoke`.
Its unauthenticated synthetic request returned HTTP 401, and its `chat_started` and `chat_completed` events appeared in the staging event store; neither appeared in the production project.
An additional isolated preview used the existing staging configuration and the same commit; its deliberately forbidden-model request generated staging smoke events and passed the SLI preview check.
The current staging and production gateways have not yet been promoted to this commit or connected to these projects.
This preview is not a production deployment, a production metric or a completed quality requirement test.

### TLS access to the telemetry backends

The sanitized `monitoring/telemetry-proxy/compose.yaml` configuration uses the OpenPanel and OpenObserve Compose networks described above.
Its default OpenObserve network is the existing VM project's `gateway7-observability_default`; set `OBSERVABILITY_BACKEND_NETWORK` to the actual network name when deploying a different Compose project.
Set `TELEMETRY_BIND_ADDRESS` to the VM's private campus interface and `TELEMETRY_TLS_DIR` to a root-only directory outside the checkout.
On a new installation, create an internal CA and a server certificate with the VM address as its IP subject alternative name; do not replace an existing CA or its private key.
The private directory must contain `server.crt`, `server.key` and the public `ca.crt`; keep `ca.key` on the VM.
Configure the OpenPanel dashboard and API public URLs to use the analytics TLS endpoint and its server-side API URL to the internal API service.
Once both backend networks exist, run:

```sh
docker compose -f monitoring/telemetry-proxy/compose.yaml config --quiet
docker compose -f monitoring/telemetry-proxy/compose.yaml up --detach
curl --fail --cacert "$TELEMETRY_TLS_DIR/ca.crt" \
  "https://$TELEMETRY_BIND_ADDRESS:18443/api/healthcheck"
curl --fail --cacert "$TELEMETRY_TLS_DIR/ca.crt" \
  "https://$TELEMETRY_BIND_ADDRESS:18444/healthz"
```

Deliver the CA certificate and its fingerprint through the team's private channel so a client can verify the endpoint; never share the CA or server private key.
The certificate and endpoint contain private deployment details and do not belong in this repository.

**OpenObserve:** supply `OPENOBSERVE_ROOT_USER_EMAIL` and `OPENOBSERVE_ROOT_USER_PASSWORD` through the operator's private environment, then run from the Gateway7 checkout:

```sh
docker compose -p gateway7-telemetry -f compose.telemetry.yaml config --quiet
docker compose -p gateway7-telemetry -f compose.telemetry.yaml up --detach --wait
```

The standalone [backend definition](https://github.com/iteam7/gateway7/blob/177-analytics-core-events/compose.telemetry.yaml) pins OpenObserve `v1.1.2`, stores its data in a named volume and retains it for seven days.
Verify `/healthz` before configuring ingestion; Compose's running state alone is not readiness.
In the OpenObserve UI, create the `staging` and `production` organizations with separate ingestion and query identities.
Use bootstrap administrator credentials only to configure the service, not in either gateway.
Record the deployed image digest, backend access and both scopes' credentials privately.
Do not run `down --volumes` on either backend when changing a gateway version.

On 7 November, an existing OpenObserve `v1.1.2` instance on the VM was configured with seven-day retention and separate staging and production ingestion and query identities.
An authenticated stream-list request from each query identity succeeded in its own organization and returned HTTP 401 for the other organization.
The installed open-source edition grants these accounts the organization administrator role; separate read-only permissions have not been established, so these credentials are not suitable as least-privilege Customer accounts.
Keep the bootstrap and organization credentials in the private operator directory, not in the repository or gateway logs.

The regular gateway deployments have per-environment Prometheus collectors scraping at five-second intervals and Vector log collectors configured to flush at one second to their corresponding organization.
The expected legacy log stream was not found in either organization during the operator check, so log delivery from the regular deployments remains unverified.
Vector has access to the Docker socket, which is effectively privileged even when mounted read-only; remove that access only after both regular gateways have been migrated to native OTLP exporters and verified.
The current regular staging and production gateways have not yet been promoted to the native OTLP instrumentation.
An isolated staging candidate using the existing staging configuration passed QR-05 QRT-01, but its separate core-task verification returned HTTP 502.
A direct provider check from the VM returned a country or territory restriction; it did not establish whether the key itself was valid.

The backend listens on VM loopback and is also available through an internal TLS proxy on the university-network interface.
The operator verified the proxy's certificate and health endpoint from the deployment machine using the private internal CA certificate; a team member also reported a successful Windows health check.
Customer access has not been verified; deliver the certificate and access details privately.
The TLS proxy and its key material are in a separate operator directory outside the checkout.

### Analytics pipeline

Each gateway receives its own OpenPanel write client through the live Compose file:

| Variable | Staging | Production |
| --- | --- | --- |
| `ANALYTICS_ENABLED` | `true` | `true` |
| `GATEWAY7_ENVIRONMENT` | `staging` | `production` |
| `ANALYTICS_SOURCE` | `web`; temporarily `smoke` for the pipeline check | `web` |
| `OPENPANEL_API_URL` | Self-hosted API base, including `/api` when behind the upstream proxy | Same backend API base |
| `OPENPANEL_CLIENT_ID` and `OPENPANEL_CLIENT_SECRET` | Staging project's write client | Production project's different write client |

The exporter appends `/track` to the API base and sends only the plan's typed event properties.
It forwards no client IP address or user agent.
Set `ANALYTICS_ENABLED=false` and restart the gateway to stop collection.
The source belongs to server configuration; callers cannot turn their requests into smoke traffic with a header.
Production refuses any source other than `web`.

After supplying the private staging credentials above, run the pipeline check only against the staging endpoint in `STAGING_URL`:

```sh
GATEWAY7_ENVIRONMENT=staging ANALYTICS_ENABLED=true ANALYTICS_SOURCE=smoke \
  docker compose -p gateway7-staging up --build --detach --wait
curl --include --silent --show-error --request POST "$STAGING_URL/chat" \
  --header 'Content-Type: application/json' --data '{}'
GATEWAY7_ENVIRONMENT=staging ANALYTICS_ENABLED=true ANALYTICS_SOURCE=web \
  docker compose -p gateway7-staging up --detach --wait
```

The unauthenticated synthetic request must return `401`; it makes no provider call.
Find its response request identifier in the raw-events view: both `chat_started` and `chat_completed` must carry `source=smoke` and stay out of the default metric chart.
Restore staging's source before accepting ordinary traffic; never send synthetic traffic to production to fill an empty chart.

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

### Connect containers and create the four dashboards

If the gateway runs in Compose, append `compose.telemetry-client.yaml` to its private `COMPOSE_FILE` value, after `compose.live.yaml`.
This preserves each gateway project's normal network and adds the backend network `gateway7-telemetry_default`.
Its OTLP endpoint can then use `http://openobserve:5080/api/staging` or `/api/production` respectively; container-local `127.0.0.1` would point at the gateway itself.
Configure the OpenPanel API base to an address reachable from the gateway container too.
Apply changes with `docker compose -p gateway7-staging up --build --detach --wait`, and later the corresponding production command after staging verification.

| Backend and scope | Dashboard | Chart configuration |
| --- | --- | --- |
| OpenPanel `staging` | `Gateway7 tasks (staging)` | `Task completion rate`: count `chat_completed` with `outcome=ok` as A, count `chat_started` as B, formula `A/B`, aggregate over the last seven days; exclude `source=smoke` on **both** event series |
| OpenPanel `production` | `Gateway7 tasks (production)` | The same saved report and filters, using only the production project |
| OpenObserve `staging` | `Gateway7 SLI (staging)` | Import the SLI-01 template into this organization |
| OpenObserve `production` | `Gateway7 SLI (production)` | Import the identical template into this organization, without injecting test traffic |

In each OpenPanel project's dashboard editor, create a metric report with the two event-count series and the formula above, UTC and `Last 7 days`.
The OpenPanel API names the property filters `properties.outcome` and `properties.source`; bare names do not filter those custom event properties.
Display the ratio of the whole period's totals as a fraction, not an average of daily ratios or a percentage.
Keep a zero denominator as no data, and do not relabel an empty chart as a measured zero.
The exact metric definitions and source filters remain in the [analytics plan](analytics.md#the-value-and-the-metrics).
Keep the staging project's raw-events view visible next to its chart when demonstrating the smoke exclusion.

In each OpenObserve organization, use **Dashboards → Import** with the address-free [SLI-01 template](https://github.com/iteam7/gateway7/blob/177-analytics-core-events/monitoring/openobserve/gateway7-sli-dashboard.json), then name the dashboard as above.
The template uses the OpenObserve v5 dashboard schema and the exact [SLI-01 query](observability.md#sli-01); the organization, not a chart label, selects the environment's data.
Importing needs dashboard-edit permission; the read-only QRT query credential is not an import credential.
When the query changes, import the updated definition into both scopes and remove the older dashboard copies after verifying the replacements.
For [QR-05 QRT-01](quality-requirements/qr/QR-05.md#qrt-01), confirm that both target endpoints belong to staging and retain the verified `DEPLOYED_COMMIT` from the manual deployment above.
The checker reads its process environment; Compose reading `.env`, or variables assigned only before a Compose command, do not export values to it.
In Bash, the following keeps existing private shell values, prompts without echoing for any missing values, and restores normal staging event collection even if the check fails:

```bash
(
  set -euo pipefail
  : "${DEPLOYED_COMMIT:?Verify the staging deployment revision first}"
  export GATEWAY7_ENVIRONMENT=staging
  for variable in STAGING_URL GATEWAY7_CLIENT_TOKEN OPENOBSERVE_URL OPENOBSERVE_USER OPENOBSERVE_TOKEN; do
    if [[ -z ${!variable-} ]]; then
      read -r -s -p "$variable: " "$variable"
      printf '\n'
    fi
    export "$variable"
  done
  restore_staging_source() {
    ANALYTICS_SOURCE=web docker compose -p gateway7-staging up --no-build --detach --wait gateway
  }
  trap 'restore_staging_source || exit 1' EXIT
  ANALYTICS_SOURCE=smoke docker compose -p gateway7-staging up --no-build --detach --wait gateway
  uv run --locked python scripts/check_sli.py --org staging --confirm-staging --commit "$DEPLOYED_COMMIT" |
    tee /tmp/gateway7-qr05-staging-result.txt
)
```

This preserves the environment's analytics-enabled setting; when collection is enabled, smoke events stay out of the normal metrics.
Check that the restore command succeeds before accepting ordinary staging traffic.
Keep the plain-text result with the verified commit and image ID; the checker prints a JSON result line followed by a verdict, not a standalone JSON file.
The check deliberately requests a forbidden model and must return `403 model_forbidden` without calling a provider.
Inspect its returned failure series in the staging chart.
Save four sanitized screenshots from the actual dashboards, with their metric or SLI names and environment scopes; keep addresses, access credentials and query credentials in the private submission.
A successful local protocol test or a checked-in template does not establish a deployed QRT pass or a working dashboard.
