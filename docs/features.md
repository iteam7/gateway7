# Features

The capabilities Gateway7 offers, in the order a user meets them.
The words Gateway7 uses in its own sense are in the [glossary](glossary.md).

## Chat without a provider key

A developer gets a model's answer through the gateway while the [provider](glossary.md#provider) key stays on the server.

- **Stories:** [`US-01`](https://github.com/iteam7/gateway7/issues/30)
- **Behavior:** [`FR-001`](functional-requirements/fr/FR-001.md)
- **Decisions:** [`ADR-001`](architecture/adr/ADR-001.md), [`ADR-003`](architecture/adr/ADR-003.md), [`ADR-004`](architecture/adr/ADR-004.md)

## Limit each client to its models

An operator gives each [client](glossary.md#client) its own token and decides which models it may use.

- **Stories:** [`US-07`](https://github.com/iteam7/gateway7/issues/36)
- **Behavior:** [`FR-006`](functional-requirements/fr/FR-006.md)
- **Decisions:** [`ADR-003`](architecture/adr/ADR-003.md)

## Keep one client's work within its capacity

An operator can give each [client](glossary.md#client) an optional concurrent-request limit, shared across chat APIs and retained through delivery and cleanup.
A busy client receives HTTP 429 while another client can proceed within the independent global pipeline capacity.
The [client guide](authentication.md#limit-concurrent-client-requests) explains configuration and the one-process boundary.

- **Stories:** [`US-07`](https://github.com/iteam7/gateway7/issues/36), extended by the operator request in [task #239](https://github.com/iteam7/gateway7/issues/239).
- **Behavior:** [`FR-016`](functional-requirements/fr/FR-016.md)
- **Decisions:** [`ADR-003`](architecture/adr/ADR-003.md)

## Control each client's request rate

An operator can assign each [client](glossary.md#client) an optional request-rate bucket shared across chat APIs.
Requests rejected before admission consume no quota, while admitted requests consume one token even if a later policy or provider fails.
The [rate guide](authentication.md#limit-a-clients-request-rate) explains continuous refill, safe retry headers and process-local restart behavior.

- **Stories:** [`US-07`](https://github.com/iteam7/gateway7/issues/36), extended by the operator request in [task #240](https://github.com/iteam7/gateway7/issues/240).
- **Behavior:** [`FR-017`](functional-requirements/fr/FR-017.md)
- **Decisions:** [`ADR-003`](architecture/adr/ADR-003.md)

## Read a protected client usage snapshot

An operator uses a separate credential to read each [client](glossary.md#client)'s provider usage, with durable daily model reports when managed accounts are enabled.
Unknown usage remains explicit for each direction, including failed and cancelled attempts; response-side denials retain observed provider usage.
The [operator snapshot guide](authentication.md#operator-usage-snapshot) explains credential separation, persistence scope and the snapshot fields.
Daily managed aggregates remain distinct from the arbitrary timestamp intervals specified by [FR-012](functional-requirements/fr/FR-012.md) and from a billing ledger.

- **Stories:** [`US-13`](https://github.com/iteam7/gateway7/issues/141), partial increment
- **Behavior:** [`FR-019`](functional-requirements/fr/FR-019.md)
- **Decisions:** [`ADR-003`](architecture/adr/ADR-003.md)

## Mask phone numbers before they leave

A security officer keeps customers' phone numbers out of the prompts that reach the provider.

- **Stories:** [`US-02`](https://github.com/iteam7/gateway7/issues/31)
- **Behavior:** [`FR-002`](functional-requirements/fr/FR-002.md)

## Add company middleware by configuration

An operator adds the company's own [middleware](glossary.md#middleware) and configures shared and additional per-client policies without changing the gateway's code.

- **Stories:** [`US-03`](https://github.com/iteam7/gateway7/issues/32)
- **Behavior:** [`FR-003`](functional-requirements/fr/FR-003.md), [`FR-018`](functional-requirements/fr/FR-018.md)
- **Decisions:** [`ADR-001`](architecture/adr/ADR-001.md), [`ADR-002`](architecture/adr/ADR-002.md)

## Block or log a flagged request

A security officer chooses whether a request containing a flagged term is stopped or only recorded.

- **Stories:** [`US-04`](https://github.com/iteam7/gateway7/issues/33)
- **Behavior:** [`FR-004`](functional-requirements/fr/FR-004.md)
- **Decisions:** [`ADR-002`](architecture/adr/ADR-002.md)

## Check the answer before delivery

A security officer uses buffered delivery to have the model's answer cleaned of flagged terms before the developer sees it.

- **Stories:** [`US-05`](https://github.com/iteam7/gateway7/issues/34)
- **Behavior:** [`FR-005`](functional-requirements/fr/FR-005.md)
- **Decisions:** [`ADR-002`](architecture/adr/ADR-002.md)

## Exchange guarded function-tool turns

A developer connects an OpenAI-compatible harness, receives checked function calls and sends tool results back through the same policies.
The OpenAI provider can generate through upstream SSE; by default, protected buffered delivery checks the whole response before releasing client SSE.
[Early text](api.md#opt-in-to-early-chat-completions-text) is an explicit opt-in for compatible request-only middleware; a response-policy incompatibility returns HTTP 400 unless an earlier request hook denies with HTTP 403, with zero provider calls in either case.

- **Stories:** [`US-01`](https://github.com/iteam7/gateway7/issues/30), [`US-05`](https://github.com/iteam7/gateway7/issues/34)
- **Behavior:** [`FR-013`](functional-requirements/fr/FR-013.md), [`FR-005`](functional-requirements/fr/FR-005.md)
- **Design proposal:** [`ADR-005`](architecture/adr/ADR-005.md)

The [API reference](api.md#upstream-streaming-and-checked-sse) defines the bounded subset, and the [OpenCode V2 check](setup.md#opencode-v2) records its tested harness scenario.
The separate [native Responses HTTP subset](api.md#native-responses-http) retains ordered native calls/results through native hooks and checked JSON/SSE, with explicit opaque/hosted consent boundaries; independent review and real Codex verification remain separate.
Its [native early-text opt-in](api.md#opt-in-to-native-early-text) admits only an eligible leading assistant prefix; held complex profiles keep their canonical identity/order without a first-token latency promise, and end-to-end/container/live verification is not claimed.

## Find the middleware that failed or slowed a request

An operator finds which [middleware](glossary.md#middleware) failed or slowed a request from that request's identifier.

- **Stories:** [`US-12`](https://github.com/iteam7/gateway7/issues/140)
- **Behavior:** [`FR-011`](functional-requirements/fr/FR-011.md)
- **Decisions:** [`ADR-002`](architecture/adr/ADR-002.md)

## Inspect client access and middleware

An operator can manage each [client](glossary.md#client)'s account, tokens, access, limits and additional middleware, and inspect its usage in one browser workspace when durable management is enabled.

- **Stories:** [US-07](https://github.com/iteam7/gateway7/issues/36), [US-13](https://github.com/iteam7/gateway7/issues/141), [US-03](https://github.com/iteam7/gateway7/issues/32)
- **Behavior:** [FR-021](functional-requirements/fr/FR-021.md), [FR-023](functional-requirements/fr/FR-023.md), [FR-027](functional-requirements/fr/FR-027.md), [FR-020](functional-requirements/fr/FR-020.md), [FR-019](functional-requirements/fr/FR-019.md)
- **Decisions:** [ADR-003](architecture/adr/ADR-003.md), [ADR-008](architecture/adr/ADR-008.md), [ADR-009](architecture/adr/ADR-009.md)

## Start a middleware package

A plugin author or a coding agent gets a working middleware package to edit, with a configuration and examples that already pass.

- **Stories:** [`US-09`](https://github.com/iteam7/gateway7/issues/38)
- **Behavior:** [`FR-008`](functional-requirements/fr/FR-008.md)

## Check a middleware offline

A plugin author checks actual Chat, typed-tool, native Responses and eligible early-stream behavior against synthetic schema-2 examples without a provider account or external network access.
The report separates declared hooks from positive passing profile evidence; the [authoring guide](authoring.md) starts with a generated guard or redactor.

- **Stories:** [`US-08`](https://github.com/iteam7/gateway7/issues/37)
- **Behavior:** [`FR-007`](functional-requirements/fr/FR-007.md)
- **Decisions:** [`ADR-002`](architecture/adr/ADR-002.md)

## Inspect and try a plugin project

An author inspects the exact versioned descriptor/settings contract, then runs current source through a disposable loopback HTTP gateway with a synthetic upstream.
The command owns ports and cleanup, replaces credentials and management configuration in memory, and never changes production import paths.
The [cookbook](plugin-cookbook.md) and [agent guide](plugin-agent-guide.md) use the generated local contract to make a failing example pass before packaging a normal wheel.

- **Behavior:** [FR-029](functional-requirements/fr/FR-029.md), [FR-030](functional-requirements/fr/FR-030.md)
- **Design:** [ADR-012](architecture/adr/ADR-012.md)

## Understand core-task completion

A product analyst can compare chat starts and completions through a privacy-safe [event](glossary.md#event) stream.
The [analytics plan](analytics.md) defines the focus metric and its counter-metric; every metric excludes [smoke traffic](glossary.md#smoke-traffic).
Collection is optional, and a backend outage leaves requests usable while observations may be lost.

- **Stories:** [US-14](https://github.com/iteam7/gateway7/issues/174)
- **Behavior:** [FR-015](functional-requirements/fr/FR-015.md)
- **Design:** [ADR-006](architecture/adr/ADR-006.md)

## Diagnose a failed request

An operator can look up a request by its random identifier and compare it with [SLI-01](observability.md#sli-01), the five-minute P95 by route and outcome.
The [observability pipeline](glossary.md#observability-pipeline) exports a per-request log point and a histogram without message content.
The [staging check](quality-requirements/qr/QR-05.md#qrt-01) verifies the visibility deadlines; deployment and screenshots remain separate evidence from local protocol tests.

- **Stories:** [US-15](https://github.com/iteam7/gateway7/issues/175)
- **Behavior:** [FR-014](functional-requirements/fr/FR-014.md)
- **Design:** [ADR-007](architecture/adr/ADR-007.md)

## Control usage and investigate client activity

An operator can inspect each [client](glossary.md#client)'s model use and request outcomes, estimate known costs and control daily or monthly usage allowance.

- **Stories:** [US-13](https://github.com/iteam7/gateway7/issues/141), [US-07](https://github.com/iteam7/gateway7/issues/36), [US-12](https://github.com/iteam7/gateway7/issues/140)
- **Behavior:** [FR-024](functional-requirements/fr/FR-024.md), [FR-026](functional-requirements/fr/FR-026.md)
- **Decisions:** [ADR-010](architecture/adr/ADR-010.md)

## Change the provider without interrupting admitted work

An operator can manage the gateway's [provider](glossary.md#provider), credential, model defaults and aliases while admitted requests finish through their existing adapter.

- **Stories:** [US-01](https://github.com/iteam7/gateway7/issues/30), [US-07](https://github.com/iteam7/gateway7/issues/36)
- **Behavior:** [FR-025](functional-requirements/fr/FR-025.md)
- **Decisions:** [ADR-011](architecture/adr/ADR-011.md)

## Recover managed administration from a private backup

An operator can recover [client](glossary.md#client) access and accounting state into an empty database of the same backend.

- **Stories:** [US-07](https://github.com/iteam7/gateway7/issues/36), [US-13](https://github.com/iteam7/gateway7/issues/141)
- **Behavior:** [FR-028](functional-requirements/fr/FR-028.md)
- **Decisions:** [ADR-010](architecture/adr/ADR-010.md)
