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

## Mask phone numbers before they leave

A security officer keeps customers' phone numbers out of the prompts that reach the provider.

- **Stories:** [`US-02`](https://github.com/iteam7/gateway7/issues/31)
- **Behavior:** [`FR-002`](functional-requirements/fr/FR-002.md)

## Add company middleware by configuration

An operator adds the company's own [middleware](glossary.md#middleware) to the gateway and sets its order without changing the gateway's code.

- **Stories:** [`US-03`](https://github.com/iteam7/gateway7/issues/32)
- **Behavior:** [`FR-003`](functional-requirements/fr/FR-003.md)
- **Decisions:** [`ADR-001`](architecture/adr/ADR-001.md), [`ADR-002`](architecture/adr/ADR-002.md)

## Block or log a flagged request

A security officer chooses whether a request containing a flagged term is stopped or only recorded.

- **Stories:** [`US-04`](https://github.com/iteam7/gateway7/issues/33)
- **Behavior:** [`FR-004`](functional-requirements/fr/FR-004.md)
- **Decisions:** [`ADR-002`](architecture/adr/ADR-002.md)

## Check the answer before delivery

A security officer has the model's answer cleaned of flagged terms before the developer sees it.

- **Stories:** [`US-05`](https://github.com/iteam7/gateway7/issues/34)
- **Behavior:** [`FR-005`](functional-requirements/fr/FR-005.md)
- **Decisions:** [`ADR-002`](architecture/adr/ADR-002.md)

## Exchange guarded function-tool turns

A developer connects an OpenAI-compatible harness, receives checked function calls and sends tool results back through the same policies.
The OpenAI provider can generate through upstream SSE, while the gateway checks the whole response before releasing its SSE representation.

- **Stories:** [`US-01`](https://github.com/iteam7/gateway7/issues/30), [`US-05`](https://github.com/iteam7/gateway7/issues/34)
- **Behavior:** [`FR-013`](functional-requirements/fr/FR-013.md), [`FR-005`](functional-requirements/fr/FR-005.md)
- **Design proposal:** [`ADR-005`](architecture/adr/ADR-005.md)

The [API reference](api.md#upstream-streaming-and-checked-sse) defines the bounded subset, and the [OpenCode V2 check](setup.md#opencode-v2) records its tested harness scenario.

## Find the middleware that failed or slowed a request

An operator finds which [middleware](glossary.md#middleware) failed or slowed a request from that request's identifier.

- **Stories:** [`US-12`](https://github.com/iteam7/gateway7/issues/140)
- **Behavior:** [`FR-011`](functional-requirements/fr/FR-011.md)
- **Decisions:** [`ADR-002`](architecture/adr/ADR-002.md)

## Start a middleware package

A plugin author or a coding agent gets a working middleware package to edit, with a configuration and examples that already pass.

- **Stories:** [`US-09`](https://github.com/iteam7/gateway7/issues/38)
- **Behavior:** [`FR-008`](functional-requirements/fr/FR-008.md)

## Check a middleware offline

A plugin author checks a middleware change against synthetic examples without a provider account or network access.

- **Stories:** [`US-08`](https://github.com/iteam7/gateway7/issues/37)
- **Behavior:** [`FR-007`](functional-requirements/fr/FR-007.md)
- **Decisions:** [`ADR-002`](architecture/adr/ADR-002.md)
