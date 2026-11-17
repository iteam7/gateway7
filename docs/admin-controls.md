# Operate the administration console

Open `/operator/console` on the gateway and connect with an operator credential.
The [PostgreSQL administration setup](authentication.md#manage-users-in-the-operator-console) remains the normal deployment path; SQLite is available for a local installation.
An administrator can change accounts, provider settings, pricing and budgets without restarting the gateway.
A viewer can inspect the workspace and download reports, but cannot change configuration, issue credentials or run a provider connection test.

## Users and named keys

Search users by ID or owner, filter by state, owner or tag, and use the page controls for larger directories.
A user has an owner, tags, enabled state, canonical model permissions, an optional default model, request-rate and concurrency limits, and ordered additional middleware.
The table distinguishes configured model permissions from their effective intersection with the gateway-wide policy.
A warning identifies a default model that the user cannot call.
An explicit user default must belong to that user's effective permissions.

Use **Keys** on a user row to inspect its named credentials.
Issuing another named key preserves existing keys, so separate applications can rotate or revoke their credentials independently.
New named credentials expire after 90 days by default and may expire at most one year after issuance.
Expiration inputs are UTC even when the browser uses another time zone.
Only imported legacy client keys can lack an expiration.

Creation and rotation show the raw credential once in the temporary credential panel.
Save it securely before dismissing the panel.
Disconnecting, navigating away or losing authentication clears the displayed credential; browser storage is not used.
Revoking a key denies subsequent requests using that key while leaving the user's other active keys available.
Suspending or deleting the user denies all its credentials on subsequent requests.
Already admitted work retains its original policy snapshot and can finish.

## Individual operators and audit

Create an individual operator with the administrator or viewer role rather than sharing the server's recovery credential.
The recovery operator is shown as `bootstrap` and cannot be edited in the console.
Named operator credentials expire and can be rotated, reissued or revoked independently.
An operator's role and expiration are enforced by the server, including requests that wait before a configuration commit.

The audit panel filters changes by actor, action, target and UTC interval.
Records contain the attributed operator, changed configuration fields, timestamp and request identifier.
Raw credentials, encrypted credential values and conversation content do not appear in audit output.

Configuration edits carry the revision of the state that was edited.
If another administrator changes that state first, the server returns HTTP 409 rather than overwriting the newer state.
Refresh the workspace, review the current values and apply the intended change again.

## Provider and model controls

The provider panel manages one active provider: OpenAI, Anthropic Claude, Google Gemini or the synthetic fixture.
It edits the default canonical model, gateway-wide model permissions, approved provider origin, timeout, concurrency cap and aliases.
Custom provider origins and multiple simultaneous upstreams remain outside this interface.

Aliases map a client-facing name directly to one canonical model ID.
Alias chains and cycles are rejected.
Permissions and user defaults use canonical IDs; an incoming alias is resolved before model authorization and is pinned outside middleware.

The model registry identifies configured models, aliases, global permissions and the current default.
OpenAI's account catalog can be refreshed explicitly.
Other adapters show the configured registry with availability marked as unverified.
Catalog membership does not establish that every generation request will succeed, and catalog failure never broadens authorization.

Saving provider settings validates a candidate connection before committing the change.
Existing admitted requests keep their previous provider instance until their work and delivery drain.
The displayed connection status records an explicit check and its timestamp; it is not a continuous provider health guarantee.
OpenAI checks its account catalog, while the other supported adapters send a small synthetic generation request.
Those checks can incur provider charges and do not represent a user's ordinary gateway usage.

### Store a new provider credential

Provider credentials supplied in the console are write-only and encrypted at rest with Fernet.
Configure `GATEWAY7_CONTROL_KEY` privately on the server before saving a new credential:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Store the generated key in the deployment's secret manager or private environment configuration, including the administration Compose deployment.
Keep the same key available after a restart or a backup restore.
A missing, incorrect or corrupted key prevents loading an encrypted provider credential rather than silently falling back to an environment credential.
Changing the encryption key requires separately re-encrypting the stored provider credential; replacing the environment value alone is not a rotation procedure.

Leaving the provider credential field empty retains the current credential.
Changing provider kind requires supplying its new credential explicitly.
Credentials must differ from client and operator credentials.
The console reports whether a credential is configured and never returns its value.

## Pricing and budgets

Enter input and output prices in USD per million tokens for each canonical model.
Amounts accept up to six decimal places and are converted to exact integer microdollars.
Changing a price affects new attempts; existing attempts retain their recorded pricing revision.
Known estimated cost and attempts with unknown cost are reported separately.
These estimates do not replace the provider's invoice.

A budget rule can cover every user and model, one user, one model, or their intersection.
Rules use UTC calendar days or months and can limit combined input/output tokens, estimated USD cost, or both.
**Warn** rules report the limit condition without blocking work.
**Hard** rules reserve allowance before contacting the provider and reject requests that cannot fit the remaining allowance.
Concurrent attempts therefore cannot each spend the same remaining allowance.

Hard cost budgets require model pricing and sufficiently known usage.
Unknown accounting is not treated as free usage.
Provider-reported usage settles reservations; unknown usage remains explicit and retains conservative accounting where possible.
The status table shows used allowance, pending reservations, warnings and exhaustion.

## Reports, diagnostics and retention

Filter usage by user, model and UTC dates, and select hourly or daily time buckets.
Date controls include both selected calendar days; the API uses an explicit UTC interval with an exclusive end.
The report includes known input/output tokens, provider outcomes, unknown usage, estimated costs, pending attempts and a time series.
Historical daily aggregates remain visible with their lower precision identified rather than being fabricated into hourly events.
Export CSV to download the selected interval and filters.

Request diagnostics show safe request outcomes, policy denials, latency, activity and key last use without prompts or answers.
The monitoring stack continues to expose [metrics and Grafana dashboards](deployment.md) for gateway operations.

Retention is configurable between 32 and 3650 days.
The minimum preserves current monthly budget accounting.
After confirmation, cleanup removes settled usage and audit events older than the selected period; pending attempts are retained.
Back up durable state and keep the encryption key separately before destructive maintenance or a restore.
