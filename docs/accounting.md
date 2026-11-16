# Usage, costs and budgets

The managed console separates provider accounting, HTTP diagnostics and budget reservations.
Provider accounting counts actual provider attempts, including failures and cancelled streams.
HTTP diagnostics also show rejected requests that made no provider attempt.
Neither view stores prompts, answers, tool arguments or bearer credentials.

## Exact intervals and history

The detailed usage report selects provider calls by their original UTC start time.
`start` is inclusive and `end` is exclusive; both accept timezone-aware ISO timestamps.
An omitted interval selects the last 30 days.
A call that starts before midnight and finishes after midnight belongs to its start day.
Use the `hour` or `day` bucket for the time series, and client/model filters and bounded pages for the table.
CSV downloads read bounded pages rather than constructing the complete raw history in memory.

An existing version-one database is upgraded transactionally in place.
Its clients, digests, deleted-user identifiers, original start time and daily totals remain intact.
Those older totals have day precision: the gateway cannot reconstruct missing call timestamps, model prices or request records.
The report includes a legacy daily total only when the selected interval contains that whole UTC day, marks its precision, and reports excluded partial-day legacy rows separately.
Hourly series cannot allocate those older daily totals to individual hours.
This database schema upgrade does not transfer data between SQLite and PostgreSQL.

## Prices and known costs

Prices are operator-entered estimates in integer micro-US dollars per million input or output tokens.
One US dollar is 1,000,000 micro-US dollars.
Each provider attempt captures the selected model price and pricing revision before forwarding.
Later price edits apply to new calls and do not rewrite earlier costs.
The gateway rounds each call's calculated cost upward to the next micro-US dollar.

Known input and output tokens are counted independently.
An omitted, invalid or unavailable direction stays unknown instead of becoming a reported zero.
A known monetary total includes only calls with both token directions and a captured price.
Unknown-cost counts remain visible alongside that total.
These estimates do not reproduce provider invoices, taxes, negotiated discounts, separate cache/reasoning prices or charges the provider does not report.

## Daily and monthly limits

A budget rule can apply to one user, one model, both, or the whole gateway.
All keys belonging to the same user share the same applicable rules.
The period is a UTC day or calendar month.
A rule can limit tokens, micro-US dollars, or both.
`warn` rules report the threshold without denying calls; `hard` rules require sufficient available allowance before forwarding.
The warning threshold is 80 percent of the configured limit.
Several matching rules apply together.

Before a provider call, the gateway durably reserves a conservative text-input allowance and the request's explicit, validated output-token ceiling.
Text input uses the serialized UTF-8 payload size plus framing allowance; the gateway does not pretend to implement a provider's private tokenizer.
Multimodal, remote-file and other input with no safe local text bound is rejected when a hard budget applies.
Hard cost limits also require a price for the selected model.
The same transaction checks existing reservations and inserts the new one, preventing concurrent requests or different keys from each spending the same remaining allowance.

A terminal observation settles a reservation once.
Known usage replaces the corresponding reserved allowance; unknown usage keeps that direction's conservative reservation.
A crashed or interrupted process leaves the pending reservation visible across restart.
The gateway does not silently refund an unconfirmed provider charge.
Unexpected usage exceeding a reservation is recorded explicitly and contributes to subsequent enforcement.
A historical version-one call with unknown usage cannot be ignored when a new hard token budget covers that period; historical unknown prices likewise prevent a hard cost budget from assuming free usage.

These limits govern gateway admission under the configured reservation assumptions.
They do not establish a contractual provider-side spending cap or distributed multi-replica quota.
Request-rate limits and concurrent-request limits remain separate admission controls.

## Retention and operational checks

Retention is configurable from 32 through 3,650 days, with a default of 90 days.
The minimum keeps the entire current UTC month available for daily and monthly budget enforcement.
The periodic purge removes older terminal request/provider events and audit records, while retaining unresolved reservations and durable daily numeric and known-cost rollups.
The report marks daily precision after archival and exposes the actual retained-detail boundary; increasing retention later does not recreate deleted request timestamps.
Deleting a user does not transfer its history or make its identifier available to another account.

Readiness and generation fail closed when the management database session becomes unavailable.
Use the protected diagnostics view to inspect per-user outcomes, latency, last activity and the key's last-use time.
Configured limits describe policy; live occupancy and remaining request-rate allowance describe current admission state.
No user or key identifier is added to public Prometheus labels.

Administrative changes share an optimistic revision and an audit record.
Refresh after a revision conflict before saving another operator's changes.
Private backups preserve the backend, schema version, control revision, digests, encrypted provider credentials, accounting history and unresolved reservations.
Restore requires the same backend and an empty destination; the private encryption key remains necessary to use backed-up provider credentials.
