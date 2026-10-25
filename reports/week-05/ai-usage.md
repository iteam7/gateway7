# Week 05 AI usage

## Tools and work

Codex extended [task #89](https://github.com/iteam7/gateway7/issues/89) on 25 October 2026 at azamatbayramov's request to prepare one deployable Gateway7 pilot in one pull request.
The work builds on the async middleware migration recorded in the [Week 4 AI report](../week-04/ai-usage.md).
Developer agents worked on provider adapters, reference middleware, CLI/runtime metrics, and Docker Compose with Prometheus and Grafana.
A separate AI TechLead reviewed their changes and updated the architecture; Formater checked the repository workflow, documentation and publication.
The review required explicit process cleanup when SIGTERM arrives during startup or serving, correct attribution of invalid next-handler metric failures, and treating excessive usage values as unknown before they reach counters.
The Compose smoke was strengthened to verify phone/email masking, response redaction, provider-call counts and the Grafana datasource query path.
The AI review does not supply the required approval from another team member or a Customer verdict.

## Handling and checks

The adapters are checked with synthetic HTTP transports against the documented provider protocols.
These tests can establish payload conversion, usage handling and failure behavior; they do not establish access to a live model or successful provider billing/account setup.
Reference policy tests cover transformations, benign messages, request history, configuration failures and whether blocked requests reach the provider.
CLI and metric checks exercise installed commands, startup errors, readiness and bounded metric labels without prompt text or credentials.
The final automated results and container validation are recorded in the pull request, including any environment limits.
No live-provider call, Customer acceptance, story closure, release or deployment to a shared environment is claimed.

## Team evaluation

TODO: Team members must record what they accepted, changed or rejected after reviewing the providers, middleware, CLI and deployment/observability bundle.

## Deviations to carry into the weekly report

- The user explicitly requested the provider, middleware, CLI, deployment and observability work in one MR; task #89 and PR #90 therefore cover the whole pilot and retain the earlier middleware migration.
- Task #89 was originally created through the GitHub API. Its Task type, human Responsible/Accountable pair, matching assignees, milestone and Priority remain for the team to set; no role or schedule was inferred.
- The existing `main` has no `FR-nnn` or `ADR-nnn` records for this work. The task retains this missing specification trace as a declared gap, rather than inventing accepted course requirements.
- At the source check on 25 October, Assignment 4 was the latest published assignment. This file records the implementation assistance only and does not claim completion of the Week 5 report or any unpublished assignment.
