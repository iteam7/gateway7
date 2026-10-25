# Week 05 AI usage

## Tools and work

Codex extended [task #89](https://github.com/iteam7/gateway7/issues/89) on 25 October 2026 at azamatbayramov's request to prepare one deployable Gateway7 pilot in one pull request.
The work builds on the async middleware migration recorded in the [Week 4 AI report](../week-04/ai-usage.md).
Developer agents worked on provider adapters, reference middleware, CLI/runtime metrics, and Docker Compose with Prometheus and Grafana.
A separate AI TechLead reviewed their changes and updated the architecture; Formater checked the repository workflow, documentation and publication.
The review required explicit process cleanup when SIGTERM arrives during startup or serving, correct attribution of invalid next-handler metric failures, and treating excessive usage values as unknown before they reach counters.
The Compose smoke was strengthened to verify phone/email masking, response redaction, provider-call counts and the Grafana datasource query path.
The AI review does not supply the required approval from another team member or a Customer verdict.

Later on 25 October, azamatbayramov selected the compatible inbound API, gateway client tokens with model access, middleware generation and offline fixture testing as the next implementation work.
Codex extended the same task and pull request, preserving the earlier pilot and its verification evidence.
The extension adds SDK-facing protocol checks, authentication/authorization boundaries and the generated-plugin workflow to the review scope.
Review kept authorized model selection outside plugin-visible payloads and preserved provider usage/finish metadata, rejected undeclared plugin fields and unsupported API options, and disabled implicit trailing-slash redirects.
The generated-package installation check uses the reviewed Gateway7 wheel and installs the plugin with `--no-deps`, so it cannot substitute an unrelated package resolution for the reviewed runtime.
The review also required interrupted offline checks to return a failure after cleaning up their worker, instead of being treated as an orderly successful server shutdown.

On 25 October, for [task #93](https://github.com/iteam7/gateway7/issues/93), Claude Code drafted `docs/glossary.md` and rewrote the root `AGENTS.md` with layout, checks, conventions and do-not-edit sections while keeping the team's agent roles and PRE/POST workflow.
Its Formater agent checked the draft against the course glossary and agent-instruction requirements, compared every path and command in `AGENTS.md` with the repository and the CI workflows, and traced each glossary definition to the linked artifact and the gateway code.

On 25 October, for [task #96](https://github.com/iteam7/gateway7/issues/96), Claude Code drafted the [next Customer Review script](meeting-script.md) and extended the [demo evidence matrix](../../docs/demo.md#acceptance-checklist) to US-01–US-09.
It mapped each acceptance criterion to the existing demo runner, tests and smoke scripts by name, and marked criteria without an exact check as needing a dry-run instead of treating related tests as evidence.
It did not run the demonstration; the Accountable reviewer's dry-run, the meeting date and the role assignments remain with the team.

## Handling and checks

The adapters are checked with synthetic HTTP transports against the documented provider protocols.
These tests can establish payload conversion, usage handling and failure behavior; they do not establish access to a live model or successful provider billing/account setup.
Reference policy tests cover transformations, benign messages, request history, configuration failures and whether blocked requests reach the provider.
CLI and metric checks exercise installed commands, startup errors, readiness and bounded metric labels without prompt text or credentials.
For the initial pilot, the [Ubuntu Compose CI check](https://github.com/iteam7/gateway7/actions/runs/40192076568/job/121165000016) built the non-root image, started the actual gateway/Prometheus/Grafana stack, validated Prometheus configuration and passed the HTTP policy, metric, scrape, dashboard and datasource-query smoke.
The local environment had no Docker or Podman; container verification therefore ran in CI rather than being inferred from YAML parsing.
The initial pilot had 359 passing tests and a separate installed-wheel check.
The extension's fresh-wheel check generated a plugin, installed it as a normal package outside the checkout and exercised it through authenticated SDK HTTP calls.
It checked the offline pass, mismatch and invalid-setup exit codes, and verified that a forbidden model caused no additional provider call.
The check exposed inherited proxy settings affecting local SDK requests; the example client and smoke use an explicit HTTP client that ignores those settings.
The final results for the compatible API, access control and developer workflow extension are recorded in the same pull request.
No live-provider call, Customer acceptance, story closure, release or deployment to a shared environment is claimed.

## Team evaluation

TODO: Team members must record what they accepted, changed or rejected after reviewing the providers, middleware, CLI, deployment/observability, compatible API, access control and plugin-authoring workflow, and after reviewing the glossary and `AGENTS.md` for task #93 and the review script and evidence matrix for task #96.

## Deviations to carry into the weekly report

- The user explicitly requested the provider, middleware, CLI, deployment and observability work in one MR; task #89 and PR #90 therefore cover the whole pilot and retain the earlier middleware migration.
- Task #89 was originally created through the GitHub API. Its Task type, human Responsible/Accountable pair, matching assignees, milestone and Priority remain for the team to set; no role or schedule was inferred.
- The existing `main` has no `FR-nnn` or `ADR-nnn` records for this work. The task retains this missing specification trace as a declared gap, rather than inventing accepted course requirements.
- At the source check on 25 October, Assignment 4 was the latest published assignment. This file records the implementation assistance only and does not claim completion of the Week 5 report or any unpublished assignment.
