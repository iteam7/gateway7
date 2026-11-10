# Client authentication and model permissions

Give each application its own gateway token and a list of models it may use.
Gateway7 checks both before it runs middleware or calls the provider.

| Credential | Who holds it | What it authorizes |
| --- | --- | --- |
| Gateway client token | The calling application and gateway server | Calls to `/chat`, `/v1/chat/completions` and `/v1/models` |
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

For any provider, use model IDs your account can access in `provider.model` and the client lists.
`GET /v1/models` reports configured permissions without testing provider access.

Supply both client tokens and the provider key through the server environment or secret manager; YAML holds variable names only.
Clients can store their own token as `GATEWAY7_TOKEN`.

Client tokens must be distinct, 16–512 visible ASCII characters without spaces, and different from the provider key.
Generate random tokens for real applications.
Missing/invalid values, duplicates and provider-key reuse prevent startup for enabled clients.

The names under `auth.clients`, such as `chat_app` and `worker`, identify the accounts.
Keep a client's name when rotating its token so its identity stays the same.
The gateway does not add these names to prompts, ordinary chat responses, logs or metric labels.

To suspend an account, set `enabled: false` on that client and restart:

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
Policy changes take effect after validation and restart; selection adds no raw-prompt retention or client-identity fields to ordinary telemetry.

## Operator usage snapshot

To enable a read-only usage view, add `operator_token_env` to the authenticated server configuration:

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
The supplied single-client Compose samples do not automatically forward this new variable; explicitly provide it to the server when enabling this optional capability.

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
The result includes `scope: process_lifetime`, its UTC `started_at`, `reset_on_restart: true` and a `clients` object keyed by configured client identity.
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
Changing client limits requires a configuration change and restart.

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

Change clients, permissions or tokens through server configuration/environment and restart.
There is no token-management API, user database or billing.

The supplied live Compose override forwards the provider key and `GATEWAY7_CLIENT_TOKEN` for the single-client samples.
Using the two-client section above with Compose also requires forwarding `GATEWAY7_APP_TOKEN` and `GATEWAY7_WORKER_TOKEN`; see [setup](setup.md#real-providers).

A shared deployment needs HTTPS and restricted access to anonymous `/health`, `/ready` and `/metrics` endpoints, Prometheus and Grafana.
Installed Python middleware is trusted code with access to server credentials.
