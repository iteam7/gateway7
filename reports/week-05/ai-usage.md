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

TODO: Team members must record what they accepted, changed or rejected after reviewing the providers, middleware, CLI, deployment/observability, compatible API, access control and plugin-authoring workflow.

## Deviations to carry into the weekly report

- The user explicitly requested the provider, middleware, CLI, deployment and observability work in one MR; task #89 and PR #90 therefore cover the whole pilot and retain the earlier middleware migration.
- Task #89 was originally created through the GitHub API. Its Task type, human Responsible/Accountable pair, matching assignees, milestone and Priority remain for the team to set; no role or schedule was inferred.
- The existing `main` has no `FR-nnn` or `ADR-nnn` records for this work. The task retains this missing specification trace as a declared gap, rather than inventing accepted course requirements.
- At the source check on 25 October, Assignment 4 was the latest published assignment. This file records the implementation assistance only and does not claim completion of the Week 5 report or any unpublished assignment.

## Architecture documentation for task #92

On 25 October, azamatbayramov asked Codex to carry out [task #92](https://github.com/iteam7/gateway7/issues/92).
Formater read the current course requirements, checked the issues and remote repository, and prepared a separate working copy whose tracked files matched the merged implementation.
The AI TechLead wrote the container architecture and three ADR drafts; a diagram agent produced an SVG and a Python standard-library generator, then the TechLead reviewed the image and implementation claims.
The work adds the product-vision backlink and documentation navigation without changing the gateway runtime.

The review kept the three deployed applications distinct from Python modules, described the synthetic upstream as a demo-only child process, and retained the existing incoming report anchors and dated team clarification.
The ADRs compare options against the implemented system without inventing a historical options meeting.
They remain Proposed: [task #91](https://github.com/iteam7/gateway7/issues/91) has not supplied the required FR/QR records, so the Drivers and ADR fields identify that dependency instead of linking nonexistent specifications.
The missing requirement mapping and human acceptance leave task #92 AC-03 and part of AC-04 unfinished.
No Week 4 meeting, Customer verdict or team acceptance of the new ADR text is claimed.

The committed SVG matched its generator, and regeneration was byte-identical when invoked outside the repository.
The image was visually inspected; XML parsing, Python compilation and Ruff checks passed for the generator.
Markdown lint passed all 56 files; strict MkDocs and the site checker passed 27 maintained pages and 2076 links/assets, including local anchors and report exclusion.
Formater checked the diff and the real remote base before publication; external link checking and the other PR workflow results belong to the pull request evidence.
The source checkout and the remote-only binary report artifacts are preserved; the local snapshot history is not pushed.
The pull request is a draft referring to #92, with no closing keyword while its dependency and acceptance criteria remain incomplete.

### Team evaluation for the architecture draft

TODO: Team members must record what they accepted, changed or rejected after reviewing the architecture, diagram and ADR drafts.
The AI review and automated checks do not replace that assessment or the Accountable member's approval.
