# Changelog

All notable changes to Gateway7 are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) with tags prefixed by `v`.

## [Unreleased]

## [0.3.0] - 2026-10-31

### Added

- OpenAI upstream SSE consumption and checked client SSE with guarded function-tool turns, plus a reproducible OpenCode V2 tool-cycle smoke check.
- Reproducible middleware diagnostics and an offline pipeline-overhead benchmark, with a complete synthetic authoring walkthrough.
- A ready-to-copy OpenAI `.env.example` for one-command live Compose startup and an in-container smoke check.
- Optional startup transport extensions for provider calls, with an HTTP(S) forward-proxy module and environment-referenced proxy credentials.
- An installed `gateway7 smoke` command for bounded live readiness, client access and one chat check, with safe diagnostic reports.
- A concise features guide linking each capability to its stories, behavior and design decisions.

### Fixed

- Generated middleware installation instructions use `uv pip` in the documented environment.
- Live Compose forwards the configured proxy environment variable, with an OpenAI launch and rehearsal recipe.

## [0.2.0] - 2026-10-26

### Added

- Component and numbered request-sequence diagrams, with a code map and lifecycle explanation in the maintained architecture guide.
- A configurable per-process limit of 64 active pipelines by default, with immediate safe HTTP 503 responses when capacity is full.
- Late Week 4 report linking the delivered artifacts and remaining evidence, with the release and submission sequence documented for the team.
- OpenAI-compatible chat completions and model discovery with an explicitly supported non-streaming API subset.
- Gateway client Bearer tokens and per-client access to configured models, enforced before company middleware or provider calls.
- Middleware starter generation and offline fixture checks with expected/actual results and automation-friendly exit codes.
- Server-held OpenAI Chat Completions and Gemini generateContent adapters alongside Claude, with bounded non-streaming calls, normalized token usage and safe provider errors.
- Reference middleware for email masking, configurable block/log content policy and response redaction, with synthetic fixtures and strict settings.
- An installed `gateway7` CLI for configuration validation, serving, a key-free demo and model requests.
- A non-root Docker image and Docker Compose pilot stack with readiness checks, Prometheus and provisioned Grafana dashboards.
- Bounded-label request, provider and middleware metrics, including latency, policy outcomes, errors and reported token usage without prompt or response text.
- Async middleware execution traces with instance, direction, request identifier, outcome and timing.
- Synthetic demonstration of phone masking, a policy guard and response transformation together, plus request-side error/timeout and response-side failure cases.
- Quality requirements priority matrix with four scenarios, and ten functional requirements with their containers and acceptance criteria.
- Container architecture diagram with a reproducible source, responsibilities and state ownership, and three architectural decision records linked to the functional and quality requirements.
- Project glossary of request-flow, plugin and demonstration terms, linked from the documentation site.
- Week 5 Customer Review script covering the missing Week 4 review, Week 3 carry-over and story verdicts for US-01 to US-09.

### Changed

- Customer documentation now starts with a short quickstart and clear paths for application developers, middleware authors and operators, with tested synthetic examples.
- Known canonical token usage is counted when a decoded provider response is rejected, while invalid or unavailable usage remains unknown.
- Upstream failures expose bounded diagnostic reasons in safe logs and a separate metric while retaining existing client errors and provider-call metrics.
- Sprint plan dates and backlog links reconciled with the Assignment 4 calendar, with missing planning, estimation and review evidence stated explicitly.
- Breaking plugin API version 2: replace independent request/response hooks with `handle(request, context, call_next)` and one YAML `middleware` list; responses unwind in reverse order.
- Middleware time budgets cover their own preprocessing and postprocessing, excluding downstream waits, while the complete request remains under one deadline.
- Task and user story issue forms follow the Week 4 shape: the task form applies the `Task` type and requires `Requirements`, the story form adds `Specified by` and checkbox criteria, and neither applies labels.
- The story form applies the `User Story` type, documentation finds stories by that type, and the `task`, `user-story` and `moscow:*` labels are retired.
- Agent instructions in `AGENTS.md` describe the repository layout, checks, conventions and files agents must not edit.
- Demonstration acceptance checklist covers US-01 to US-09 and separates automated mock checks, known gaps and evidence still needed.

### Fixed

- Interrupted `gateway7 chat` requests return exit status 130 and close the pending client connection instead of reporting success.
- Gateway shutdown attempts every initialized middleware and closes the provider even when a plugin shutdown hook cancels or fails.
- Oversized upstream responses are rejected at the first overflowing transport chunk, without consuming later chunks or appending the overflowing chunk to the response buffer.

## [0.1.1] - 2026-10-19

### Added

- Project plan for SPRINT-03 to SPRINT-09, with the first release and weekly progress monitoring.
- Week 3 customer meeting report and decisions reconstructed from the privately supplied transcript, with unresolved story verdicts and Week 4 follow-ups.

### Changed

- Week 3 report links the published documentation, release, merged work and current checks, and identifies the remaining validation and scheduling gaps.
- Assignment 3 follow-up clarifies setup, release and submission steps, plugin timeout limits, and the remaining evidence needed to assess the success threshold.

## [0.1.0] - 2026-10-18

### Added

- Python text-chat gateway with server-held provider credentials, strict input validation and safe error responses.
- Trusted modules installed by restart, separate ordered request and response hooks, and fail-closed execution.
- Phone masking over conversation history and a one-file sample company plugin.
- Deterministic HTTP upstream and repeatable customer demonstration with locked setup instructions.
- Windows PowerShell commands for running the two services manually.
- Definition of Done and contribution guide with task/review standards and setup navigation.
- Locked documentation build with local Mermaid assets, pull-request validation and a main-only GitHub Pages workflow; first deployment pending.

### Fixed

- The one-command demonstration's plugin-installation check now passes on Windows, where it compared backslash paths with POSIX paths.
- The documented test command no longer errors on Windows, where one case's generated test ID exceeded the environment-variable size limit.

[Unreleased]: https://github.com/iteam7/gateway7/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/iteam7/gateway7/releases/tag/v0.3.0
[0.2.0]: https://github.com/iteam7/gateway7/releases/tag/v0.2.0
[0.1.1]: https://github.com/iteam7/gateway7/releases/tag/v0.1.1
[0.1.0]: https://github.com/iteam7/gateway7/releases/tag/v0.1.0
