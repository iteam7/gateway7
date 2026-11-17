# Client authentication and model permissions

Give each application its own gateway token and optionally restrict the models it may use.
Gateway7 checks authentication and the effective provider/client permissions before it runs middleware or generates an answer.

| Credential | Who holds it | What it authorizes |
| --- | --- | --- |
| Gateway client token | The calling application and gateway server | Calls to `/chat`, `/v1/chat/completions`, `/v1/responses` and `/v1/models` |
| Provider API key | The gateway server | Outbound calls to the selected LLM provider |

The application sends its gateway token in `Authorization: Bearer ...`.

## Synthetic demo

Start the packaged demo with the [setup guide](setup.md#install-from-a-checkout), then set these public test values in the client terminal:

```sh
export GATEWAY7_URL=http://127.0.0.1:8000
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
```

### Check allowed and denied requests

Send an allowed request:

```sh
curl --silent --show-error --write-out '\nHTTP %{http_code}\n' \
  "$GATEWAY7_URL/v1/chat/completions" \
  -H "Authorization: Bearer $GATEWAY7_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"fake","messages":[{"role":"user","content":"Hello"}]}'
```

Expect HTTP 200 and `pong — Hello` in `choices[0].message.content`.
Now use a model that this client is not allowed to call:

```sh
curl --silent --show-error --write-out '\nHTTP %{http_code}\n' \
  "$GATEWAY7_URL/v1/chat/completions" \
  -H "Authorization: Bearer $GATEWAY7_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"not-allowed","messages":[{"role":"user","content":"Hello"}]}'
```

Expect HTTP 403 with `error.code` equal to `model_forbidden`.
No middleware or provider call runs for that request.
Authenticated `GET /v1/models` lists the allowed IDs; this demo allows only `fake`.

Check missing and wrong credentials:

```sh
curl --silent --show-error --write-out '\nHTTP %{http_code}\n' \
  "$GATEWAY7_URL/v1/models"

curl --silent --show-error --write-out '\nHTTP %{http_code}\n' \
  "$GATEWAY7_URL/v1/models" \
  -H 'Authorization: Bearer gateway7-synthetic-wrong-token'
```

Both return HTTP 401 with `error.code` equal to `unauthorized`.
The same token and model checks protect native `/chat`.
Malformed, duplicated or unknown bearer credentials also fail with 401.
See [API examples](api.md) for complete native, curl and Python SDK requests.

Add `--fail-with-body` when scripts should stop on HTTP errors.

## Configure clients

For day-to-day administration in the browser, enable [managed users](#manage-users-in-the-operator-console).
The YAML examples in this section describe legacy configuration and optional first-start imports.

Keep the provider and middleware settings from an [OpenAI provider configuration](setup.md#real-providers).
Replace its `auth` section, for example with these two applications:

```yaml
auth:
  enabled: true
  clients:
    chat_app:
      token_env: GATEWAY7_APP_TOKEN
      models: [gpt-4.1-mini]
    worker:
      token_env: GATEWAY7_WORKER_TOKEN
      models: [gpt-4.1-mini, gpt-4.1]
```

`provider.allowed_models` is an optional provider-wide restriction, and each client's `models` is an optional additional restriction; effective permissions are their intersection.
The same rules apply independently at both levels:

| Setting | Meaning |
| --- | --- |
| Omitted | No restriction at that level |
| Explicit nonempty list | Permit only its distinct entries, at most 64 IDs |
| `[]` | Deny every model |
| Explicit `null`, wrong types or duplicate IDs | Configuration error, not unrestricted access |

`provider.model` is the default, not a whitelist; a forbidden default is denied rather than replaced with another model.
Use model IDs your provider account can access; permission at the gateway does not prove that the provider will accept a request.
OpenAI IDs are opaque literal strings of at most 1024 UTF-8 bytes: colon and slash are supported, while whitespace, control, format and surrogate characters are rejected.
Non-OpenAI providers retain their existing URL-safe ID validation.
Permitted IDs are forwarded unchanged through the supported text Chat/Responses contracts; no endpoint, modality or parameter adaptation is inferred from the ID.
The [authenticated catalog](api.md#model-catalog-and-permission-filtering) is permission-filtered, but missing catalog membership is not an authorization denial and discovery failure never broadens permissions.

Supply both client tokens and the provider key through the server environment, secret manager or [explicit private startup file](setup.md#supply-server-credentials); YAML holds variable names only.
Clients can store their own token as `GATEWAY7_TOKEN`.

Client tokens must be distinct, 16–512 visible ASCII characters without spaces, and different from the provider key.
Generate random tokens for real applications.
Missing/invalid values, duplicates and provider-key reuse prevent startup for enabled clients.

The names under `auth.clients`, such as `chat_app` and `worker`, identify the accounts.
Keep a client's name when rotating its token so its identity stays the same.
The gateway does not add these names to prompts, ordinary chat responses, logs or metric labels.

In configuration-only mode, suspend an account by setting `enabled: false` on that client and restarting:

```yaml
worker:
  token_env: GATEWAY7_WORKER_TOKEN
  enabled: false
  models: [gpt-4.1-mini, gpt-4.1]
```

Place this entry under `auth.clients` in the example above.
`enabled` defaults to `true`.
A suspended account cannot authenticate on any protected API route, and its token environment variable need not be present.
Set `enabled: true`, supply a valid token and restart to restore access.

Validate the edited file and restart as shown in [setup](setup.md#real-providers).
Validation needs no credentials and makes no provider call; startup checks credential values.
Both commands load trusted middleware code, as described in [setup](setup.md#select-and-validate-a-config).

Authentication may be disabled only for the fake provider, as in legacy `config/demo.yaml` and `config/reference.yaml` fixtures.
Only the configured default may be used anonymously, and it must also pass `provider.allowed_models`; omitted restrictions do not enable anonymous real-provider access.
The packaged demo and default Compose stack enable it.

## Apply additional client policies

Use `additional_middleware` to append configured middleware instances after the complete global chain for one account.
The field defaults to an empty list and accepts at most 64 distinct enabled instances.
The server chooses the account from its authenticated token; a request cannot select a different chain.

For example, merge these sections into a provider configuration and supply the two token variables through its server environment:

```yaml
plugins:
  global_guard:
    module: gateway7.plugins.content_policy
    required: true
    settings:
      terms: [SYNTHETIC-GLOBAL-BLOCK]
      phase: request
      action: block
  worker_guard:
    module: gateway7.plugins.content_policy
    settings:
      terms: [SYNTHETIC-WORKER-BLOCK]
      phase: request
      action: block
middleware: [global_guard]
auth:
  enabled: true
  clients:
    chat_app:
      token_env: GATEWAY7_APP_TOKEN
      models: [gpt-4.1-mini]
    worker:
      token_env: GATEWAY7_WORKER_TOKEN
      models: [gpt-4.1-mini]
      additional_middleware: [worker_guard]
```

Both clients are denied for `SYNTHETIC-GLOBAL-BLOCK`; only `worker` is denied for `SYNTHETIC-WORKER-BLOCK`.
Global middleware always runs first, and buffered response checks unwind the effective chain in reverse order.
An additional entry cannot name an unknown, disabled, repeated or already-global instance; these checks also apply to suspended client entries and run before plugin factories.
Configured instances are shared and started/stopped once, while each request has fresh private hook state.

The effective chain covers native chat, Chat Completions and Responses, including checked SSE and explicit early delivery.
Missing native/early hooks or response-dependent early policies reject before provider work instead of skipping an additional policy.
Keep response inspection in buffered delivery unless every selected middleware explicitly supports request-only early processing.
See [FR-018](functional-requirements/fr/FR-018.md) for the behavior and technical acceptance criteria.
In configuration-only mode, policy changes take effect after validation and restart.
In managed mode, select already-loaded additional middleware in the console and save to apply it to subsequent requests.
Installing middleware or changing its code/settings still requires validation and restart.
Selection adds no raw-prompt retention or client-identity fields to ordinary telemetry.

## Operator usage snapshot

This section describes the original configuration-only snapshot; [managed mode](#manage-users-in-the-operator-console) adds persistent daily reports.

To enable operator access, add `operator_token_env` to the authenticated server configuration:

```yaml
auth:
  enabled: true
  operator_token_env: GATEWAY7_OPERATOR_TOKEN
  clients:
    chat_app:
      token_env: GATEWAY7_APP_TOKEN
      models: [gpt-4.1-mini]
```

Supply the named operator variable through the server's environment or secret manager, with a distinct random token of 16–512 visible ASCII characters without spaces.
It must differ from the provider key and all enabled client tokens.
Configuration requires client authentication to be enabled; malformed, missing or conflicting configured values prevent startup without printing them.
The supplied live Compose sample does not automatically forward this variable; the [managed Compose override](#persist-managed-state-with-compose) adds it, or explicitly provide it to the server.

An operator request sends only that separate Bearer credential.
Client credentials cannot read usage, and an operator credential cannot call chat or list models.
The endpoint returns HTTP 404 by default and HTTP 401 for missing, invalid or duplicated credentials when enabled, before reading the request body.
Successful responses have `Cache-Control: no-store`.
For example, a client process that already receives the operator variable can read the snapshot without putting its value in command-line arguments:

```python
import json
import os
from urllib.request import Request, urlopen

request = Request(
    "http://127.0.0.1:8000/operator/usage",
    headers={"Authorization": "Bearer " + os.environ["GATEWAY7_OPERATOR_TOKEN"]},
)
with urlopen(request, timeout=10) as response:
    print(json.load(response))
```

Use HTTPS when reaching a shared deployment.
Without a configured management database, the result includes `scope: process_lifetime`, its UTC `started_at`, `reset_on_restart: true` and a `clients` object keyed by configured client identity.
Each client row contains:

| Field | Meaning |
| --- | --- |
| `provider_attempts` | Provider calls observed once, including failures and cancellation |
| `outcomes` | Provider outcomes `complete`, `provider_error` and `cancelled`; these are not HTTP delivery outcomes |
| `known_input_tokens`, `known_output_tokens` | Independent sums of valid source-reported counts |
| `input_usage_unknown_attempts`, `output_usage_unknown_attempts` | Attempts lacking valid usage for that direction |

A zero known total accompanied by unknown attempts does not mean that those attempts consumed zero tokens.
An in-flight attempt enters this snapshot when its terminal provider observation is recorded; active admission is a separate signal.
Requests rejected before the provider runs add no usage; an answer blocked after a provider call keeps its observed provider usage.
The snapshot retains aggregate numbers only, without prompts, answers, tools, credentials or per-request history, and adds no client-identity labels to logs or metrics.
Rows are limited to configured client IDs, including zero-usage disabled clients; a configuration reload still requires a restart.

Restarting the application resets its ledger, and separate workers have separate ledgers.
This bounded view is not durable accounting, an arbitrary-period or per-model usage report, a distributed budget, a hard token or currency cap, or a monetary cost estimate.
[FR-019](functional-requirements/fr/FR-019.md) specifies this increment; [FR-012](functional-requirements/fr/FR-012.md) and its broader US-13 history requirement remain separate.

## Open the read-only operator console

This section describes the console when neither `auth.management_database_url_env` nor `auth.management_db` is configured.
Enable [managed users](#manage-users-in-the-operator-console) to administer accounts in the same workspace.

After configuring the separate operator credential above, open `/operator/console` on your gateway and enter that token.
The shell and its packaged stylesheet/script contain no configured client, policy or usage data.
The dashboard loads a protected `GET /operator/state` snapshot only after connecting, using an authorization header to the same gateway.
The token stays in page memory; the console does not place it in URLs, cookies or browser storage.
Disconnect clears the token and displayed data, and leaving the page ends that browser session.
Shell, asset and operator state responses prohibit caching, including authentication errors.
Without configured operator access, the shell, assets and state endpoint return HTTP 404.

The workspace shows enabled and suspended clients, their configured model permissions and request limits, process-lifetime provider usage, and global and additional middleware order.
Known input/output tokens and attempts with unknown usage remain separate.
Counts reflect terminal provider observations; in-flight calls have not yet been included.
A provider completion is not a guarantee that a response passed all policies or reached its caller, and the counters are not a monetary ledger.
Refresh reads another snapshot from the current process; counters reset on restart and separate workers keep separate ledgers.

Middleware metadata identifies configuration validated at startup, required/enabled instances and registered hook presence.
A hook can reject a particular request or configuration, so its presence is not a live health or universal compatibility claim.
Disabled middleware has validated configuration but no instantiated hooks.
Policy terms/settings, provider origins, credential references and conversations are excluded from the snapshot.

Without a configured management database, the console changes no account, permission, limit or middleware setting.
Update the server configuration, run the existing [configuration validation](cli.md#validate-configuration) and appropriate [isolated middleware fixtures](cli.md#generate-and-test-middleware), then restart to apply a change.
Malformed configuration prevents startup, while runtime policy/plugin failures retain their existing fail-closed behavior.
[FR-020](functional-requirements/fr/FR-020.md) specifies the console boundary.

## Manage users in the operator console

Enable PostgreSQL-backed administration once in the server YAML:

```yaml
auth:
  enabled: true
  operator_token_env: GATEWAY7_OPERATOR_TOKEN
  management_database_url_env: GATEWAY7_DATABASE_URL
  clients: {}
```

Keep the rest of the provider, middleware and request-limit configuration.
Supply the operator token, provider key and PostgreSQL connection settings privately, validate the configuration, and restart once.
The named database URL variable is resolved only at runtime; YAML contains its environment name, never a DSN or password.
For a local Python process, set `GATEWAY7_DATABASE_URL` to your PostgreSQL DSN and supply its password through `PGPASSWORD` or your existing libpq credential mechanism.
Managed administration requires client authentication and a separate operator credential; an empty client set is allowed so the operator can create the first user in the console.
PostgreSQL is the primary managed deployment; the explicit [SQLite alternative](#optional-local-sqlite-storage) remains available for local use.
Configure exactly one backend: `management_database_url_env` and `management_db` are mutually exclusive.

Open `/operator/console` and connect with the operator token.
The [admin controls guide](admin-controls.md) follows the available panels; use the user controls to:

1. Create a user with a stable client ID, owner label, tags, enabled state, model permissions, default model, request limits and ordered additional middleware.
2. Copy the generated client token when it is shown and deliver it to the application through your normal secret channel.
3. Edit access, enable or suspend the user, create separately named application keys, rotate or revoke one key, revoke all keys, or delete the user.
4. Filter usage by user, model and precise UTC interval, inspect request diagnostics and budgets, and export the selected report as CSV.

Tokens are shown only after creation or replacement; later state and usage reads cannot recover them.
The database stores token digests, and the browser keeps the operator token only in page memory.
Replacing a token invalidates its predecessor; revoking it leaves the account without a credential until a fresh token is issued.
Enabling an account whose token was revoked does not recreate that token.
Keep user IDs pseudonymous because they are part of the protected usage report.

Model permissions retain the same three choices: unrestricted at the client level (`null`), an explicit allowlist, or deny every model (`[]`).
The independent provider-wide restriction still applies.
The console can assign only enabled middleware already installed and loaded at startup; global policies always remain first and cannot be removed by a user edit.
Save applies new permissions, state, limits and middleware selections to subsequent requests without restarting.
Already-admitted requests finish under their existing policy chain; suspending or deleting an account does not retract a response already in progress.
Editing a limit retains current admission occupancy and does not grant a fresh rate bucket through unrelated account edits.

An existing `auth.clients` section can seed the database on its first initialization.
Only that first initialization resolves and imports its client tokens; subsequent starts use stored profiles and digests, so bootstrap client environment variables are no longer required.
Editing seed YAML or restoring an old bootstrap token does not overwrite managed changes or reactivate deleted users.
The operator token and provider key remain server-managed credentials.
Deleting a user retains its usage and reserves its ID so a new account cannot inherit old history.

### Named keys and operators

The [operator identity guide](operator-identities.md) details credential lifecycle, role boundaries and recovery.

Each user can hold several named application keys, with separate expiry, last-used time, rotation and revocation.
New credentials expire after 90 days by default; an explicit expiry must be in the future and within 366 days.
Revoking one key preserves the other applications belonging to that user, and all of the user's keys share its access rules and budgets.
The original user-level token rotation endpoint replaces all of that user's active keys; use the individual key controls when replacing only one application credential.
Imported legacy keys retain their existing expiry behavior.

Named operators have an `admin` or `viewer` role and an expiring credential.
Viewers can inspect users, reports, audit records and diagnostics, and download reports.
Admins can change managed settings and issue or revoke credentials.
The separately configured environment operator token remains the recovery administrator; the console cannot delete or demote that recovery capability.
The browser holds the selected operator token in page memory and uses authorization headers, without cookies or browser storage.

Every managed write requires `If-Match` with the current global revision returned by the state snapshot, plus `X-Gateway7-Operator: true`.
A stale revision returns HTTP 409 without overwriting another operator's change; refresh, review the new state and submit again.
The gateway rechecks the operator's current role and credential before committing a change.
Changes record the operator identity, action, target, time, request ID and a sanitized difference in the protected audit view; raw credentials never appear there.
The user list supports search, enabled status, owner, tag and bounded pages.

### Defaults, aliases and provider settings

A user's default model is an optional canonical model ID; otherwise requests without a model use the gateway default.
Aliases map directly to canonical IDs, without alias chains, and authorization applies after resolving an alias.
Client and provider allowlists continue to intersect; choosing a default or alias does not broaden access.
A forbidden default is reported as denied instead of being silently replaced.

The provider panel controls the instance's one provider, endpoint, default and allowed models, aliases, provider timeout and global concurrency limit.
Model discovery and explicit refresh show the provider catalog when supported, with a visible fallback to configured models when discovery is unavailable.
Catalog membership is separate from permission and endpoint compatibility.
A candidate provider configuration is checked before publication; running requests retain their captured adapter until they finish and cleanup completes.

A provider credential entered through the console is write-only and encrypted in managed storage.
Set a private Fernet key in `GATEWAY7_CONTROL_KEY` before saving such a credential, and retain that key separately from database backups.
Generate and store it with your secret manager; changing or losing it makes stored provider credentials unreadable.
The initial environment provider key remains usable until a managed credential is saved.
The connection test uses model discovery for OpenAI; other adapters can send one synthetic request with an output limit of one token, which can incur provider charges.
Provider configuration changes and connection tests require an administrator.
Installing middleware code or changing its settings still requires server deployment and restart.

### Usage, budgets and diagnostics

Managed usage reports use `scope: persistent` and `reset_on_restart: false`.
New provider attempts are selected by their actual UTC provider-start time, with inclusive `start` and exclusive `end` timestamps.
The default interval is the last 30 days; hourly or daily series, user/model filters, bounded table pages and streamed CSV exports support inspection.
Known token directions, unknown usage, captured pricing revisions and known costs remain separate.
The [accounting guide](accounting.md) explains exact intervals, older daily precision, prices, token/cost budgets, unknown reservations and retention.

The diagnostics view additionally includes authenticated requests denied before forwarding, terminal stream outcomes, latency, last-seen and key activity, active requests and remaining request-rate allowance.
No prompt, answer, tool argument, bearer token or provider credential is included.
User and key identities stay in protected operator reports rather than public Prometheus labels.

### Persist managed state with Compose

Use `compose.yaml` with `compose.admin.yaml` to run the gateway, PostgreSQL and monitoring services.
The default managed configuration is `config/admin-postgres.yaml`; unlike the legacy single-client example, it needs no bootstrap client token.
Set a private provider key, a distinct random operator token and a database password in your environment or local uncommitted Compose `.env` file:

```sh
export GATEWAY_KEY_ENV=OPENAI_API_KEY
export GATEWAY_CONFIG_FILE=./config/admin-postgres.yaml
read -r -s -p 'OpenAI API key: ' OPENAI_API_KEY
printf '\n'
read -r -s -p 'Operator token: ' GATEWAY7_OPERATOR_TOKEN
printf '\n'
read -r -s -p 'PostgreSQL password: ' GATEWAY7_POSTGRES_PASSWORD
printf '\n'
export OPENAI_API_KEY GATEWAY7_OPERATOR_TOKEN GATEWAY7_POSTGRES_PASSWORD
docker compose -f compose.yaml -f compose.admin.yaml \
  up --build --detach --wait
```

Alternatively set `COMPOSE_FILE=compose.yaml:compose.admin.yaml` and `GATEWAY_CONFIG_FILE=./config/admin-postgres.yaml` in the local Compose `.env`, fill the same private variables, and run `docker compose up --build --detach --wait`.
For another provider, select equivalent provider settings and `GATEWAY_KEY_ENV`; managed accounts and the database are independent of the provider.
Both managed overrides forward the optional telemetry and product-analytics settings.
Adding `compose.admin.yaml` after `compose.live.yaml` remains supported for its explicit proxy environment forwarding.

The managed override provides a pinned PostgreSQL 17 image, a persistent `postgres-data` named volume, a database health check and a gateway startup dependency on that health check.
It publishes no PostgreSQL host port.
The default DSN is `postgresql://gateway7@postgres:5432/gateway7`; Compose passes the password separately as `PGPASSWORD` to the gateway and `POSTGRES_PASSWORD` to PostgreSQL, so special characters in passwords need no URI encoding.
An explicit `GATEWAY7_DATABASE_URL` overrides the gateway connection string; it does not provision a different server or change an existing database user's password.
Do not print expanded live Compose configuration, since it contains injected credentials.

First startup initializes the `gateway7_admin` schema and version metadata, then imports optional seed clients once.
Subsequent starts validate the schema version and stored state instead of overwriting them from YAML.
An unavailable database, incompatible schema, invalid stored state or another gateway holding the database ownership lock prevents readiness; the gateway does not silently switch to SQLite or create an empty replacement registry.
If the active PostgreSQL connection is lost, client requests fail closed until the gateway has been restarted with a healthy database.

Run one gateway process per management database: PostgreSQL session ownership prevents several processes from serving divergent access rules or independent client limits.
Concurrent/rate counters remain process-local and restart-reset, while stored limit settings and usage survive.
Container restart, recreation or ordinary `docker compose down` preserves the named volume.
`docker compose down --volumes` removes it and its managed accounts and usage; use that only for intentionally disposable data.
Use the installed [backup and restore commands](cli.md#back-up-and-restore-managed-state), keep the backup and `GATEWAY7_CONTROL_KEY` separately private, and verify restoration in an isolated empty database.
The image initializes its password only for a new volume; changing an existing user's password requires an explicit database administration step and matching gateway credential update.

### Optional local SQLite storage

For an explicit local alternative, set `auth.management_db` to a private SQLite file and omit `management_database_url_env`.
The `config/admin-sqlite.yaml` example uses `/var/lib/gateway7/admin.sqlite3` with no seeded users.
For a Docker host using the supplied image's service UID/GID `10001:10001`, prepare a private directory outside the checkout:

```sh
sudo install -d -o 10001 -g 10001 -m 0700 /srv/gateway7/admin-state
export GATEWAY7_ADMIN_STATE_DIR=/srv/gateway7/admin-state
export GATEWAY_CONFIG_FILE=./config/admin-sqlite.yaml
docker compose -f compose.yaml -f compose.admin-sqlite.yaml \
  up --build --detach --wait
```

Supply the same provider key and operator token as above; this alternative needs no PostgreSQL password.
Use the SQLite override instead of the PostgreSQL override.
Its private directory is writable while the root filesystem remains read-only; the directory must already exist with service ownership.
For a local Python process, choose a persistent directory writable only by its service account, outside the checkout.
Stop the gateway before copying the complete SQLite database for a consistent backup, and restore it with the same service ownership.
A second gateway process opening the file fails startup.
Deleting or losing the file loses managed users and usage; a newly initialized store runs first-start bootstrap again.

### Operator API

The console uses these same protected endpoints:

| Method and path | Operation |
| --- | --- |
| `GET /operator/state` | Safe workspace snapshot, current revision and operator identity |
| `GET /operator/clients` | Search and page users by query, status, owner and tag |
| `POST /operator/clients` | Create a client and return its initial one-time key |
| `PUT /operator/clients/{id}` | Replace the client's editable settings |
| `DELETE /operator/clients/{id}` | Delete the account, retaining history and its reserved ID |
| `GET, POST /operator/clients/{id}/keys` | List safe key metadata or issue a separately named key |
| `POST /operator/clients/{id}/keys/{key_id}/rotate` | Replace one application key |
| `DELETE /operator/clients/{id}/keys/{key_id}` | Revoke one application key |
| `POST, DELETE /operator/clients/{id}/token` | Replace or revoke all keys for the user |
| `GET, POST /operator/operators` | Inspect named operators or create an expiring credential |
| `PUT, DELETE /operator/operators/{id}` | Edit a named operator or revoke its credential |
| `POST /operator/operators/{id}/token` | Reissue a named operator credential |
| `GET /operator/audit` | Filter and page attributable changes |
| `GET, PUT /operator/provider` | Read or change live provider settings |
| `POST /operator/provider/test` | Check current or candidate provider connectivity |
| `GET /operator/models` | Inspect or refresh the model registry |
| `GET /operator/accounting` | Read pricing, budgets and retention policy |
| `PUT /operator/pricing` | Save model prices for subsequent attempts |
| `PUT /operator/budgets` | Save daily/monthly user/model limits |
| `GET /operator/budgets/status` | Read usage, reservations and warning/exhaustion status |
| `GET /operator/usage` | Precise UTC interval report with client/model/bucket/page filters |
| `GET /operator/usage/export` | Stream the selected provider history as CSV |
| `GET /operator/diagnostics` | Inspect protected request outcomes and activity |
| `PUT /operator/retention` | Set the bounded history retention period |

Every endpoint requires the separate operator bearer credential.
Mutations require an administrator, the current `If-Match` revision and `X-Gateway7-Operator: true`; cross-origin requests, cookies and query parameters cannot authorize them.
Client settings include `enabled`, `models`, `limits`, `additional_middleware`, `owner`, `tags` and `default_model`; creation also requires `id`.
Invalid or stale edits leave the published profile and stored state unchanged.
The [functional requirements index](functional-requirements/README.md) links the independent account, operator, provider, audit, budget and recovery contracts.

## Use the CLI

From the checkout, using the demo variables above:

```sh
uv run --locked gateway7 chat \
  --url "$GATEWAY7_URL" \
  --model fake \
  --message 'Hello'
```

Expect `pong — Hello` in `text`.
The CLI reads `GATEWAY7_TOKEN`; use `--token-env ANOTHER_VARIABLE` to select a different variable.
See the [CLI reference](cli.md) for other options.

## Limit concurrent client requests

Set `limits.max_concurrent_requests` on an individual client to limit how many of its admitted requests remain active:

```yaml
chat_app:
  token_env: GATEWAY7_APP_TOKEN
  models: [gpt-4.1-mini]
  limits:
    max_concurrent_requests: 2
```

The value must be an integer from 1 to 10,000.
Omitting the setting or using `null` leaves that client subject only to the independent global pipeline limit.
The client's limit is shared across native `/chat`, Chat Completions and Responses, including checked and early streaming.
When its slots are occupied, a valid new request receives HTTP 429 with `error.code: client_overloaded` and `Retry-After: 1` before middleware or a provider call.
Other clients retain their own capacity; the global pipeline limit still returns HTTP 503 with `overloaded` when all pipeline slots are busy.

A client slot stays occupied through response delivery and owned cancellation cleanup.
The global `active_pipelines` gauge continues to count pipeline tasks only, so it can be zero while a client's completed response is still being delivered.
Health, readiness, metrics and model-list requests do not use client slots.
Client names are not added to logs or public metric labels.
Limits apply to one gateway process and reset on restart; separate workers or replicas do not share counters.
Change the limit in the managed console to apply it to subsequent requests, or edit YAML and restart in configuration-only mode.

## Limit a client's request rate

Set `limits.requests_per_minute` on a client to add a request-rate quota:

```yaml
chat_app:
  token_env: GATEWAY7_APP_TOKEN
  models: [gpt-4.1-mini]
  limits:
    max_concurrent_requests: 2
    requests_per_minute: 30
```

The rate must be an integer from 1 to 1,000,000; absent or `null` leaves it unlimited.
Each enabled client has its own token bucket, initially full with that many request tokens.
It refills continuously at the configured rate using monotonic time, up to that capacity; this permits an initial burst rather than imposing a fixed calendar-minute window.
Native `/chat`, Chat Completions and Responses share that client's bucket, including buffered and early delivery.
A depleted bucket returns HTTP 429 with `error.code: rate_limited` before middleware or a provider call, and `Retry-After` gives the rounded-up wait for one request token, from 1 to 60 seconds.

Authentication, payload/model validation and global/client concurrency checks run before the rate debit.
Requests those checks reject and operation/task-creation failures that roll back admission consume no request token.
Once a request is admitted, later policy denial, unsupported pipeline capability or provider failure still consumes its token.
Health, readiness, metrics and model-list requests consume none.

Buckets belong to one gateway process and reset on restart; multiple workers or replicas each have their own quota.
This controls admitted request rate, without establishing a hard model-token, monetary or distributed budget.
The public `gateway7_rate_limit_rejections_total` counter has no client identity label.

## Deployment boundary

With a management database configured, use the console for users, credentials, permissions, limits and policy assignments.
Without it, change clients through server configuration/environment and restart.
The provider panel manages the single instance's provider settings and write-only credential.
The recovery operator credential, encryption key and middleware code/settings remain server administration.
Configured cost estimates and admission budgets are not provider invoice reconciliation.

The supplied live Compose override forwards the provider key and `GATEWAY7_CLIENT_TOKEN` for the single-client samples.
Using the two-client section above with Compose also requires forwarding `GATEWAY7_APP_TOKEN` and `GATEWAY7_WORKER_TOKEN`; see [setup](setup.md#real-providers).

A shared deployment needs HTTPS and restricted access to anonymous `/health`, `/ready` and `/metrics` endpoints, Prometheus and Grafana.
Installed Python middleware is trusted code with access to server credentials.
