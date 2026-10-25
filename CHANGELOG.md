# Changelog

All notable changes to Gateway7 are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) with tags prefixed by `v`.

## [Unreleased]

### Added

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
- Project plan for SPRINT-03 to SPRINT-09, with the first release and weekly progress monitoring.
- Week 3 customer meeting report and decisions reconstructed from the privately supplied transcript, with unresolved story verdicts and Week 4 follow-ups.
- Project glossary of request-flow, plugin and demonstration terms, linked from the documentation site.

### Changed

- Breaking plugin API version 2: replace independent request/response hooks with `handle(request, context, call_next)` and one YAML `middleware` list; responses unwind in reverse order.
- Middleware time budgets cover their own preprocessing and postprocessing, excluding downstream waits, while the complete request remains under one deadline.
- Week 3 report links the published documentation, release, merged work and current checks, and identifies the remaining validation and scheduling gaps.
- Assignment 3 follow-up clarifies setup, release and submission steps, plugin timeout limits, and the remaining evidence needed to assess the success threshold.
- Agent instructions in `AGENTS.md` describe the repository layout, checks, conventions and files agents must not edit.

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

[Unreleased]: https://github.com/iteam7/gateway7/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/iteam7/gateway7/releases/tag/v0.1.0
