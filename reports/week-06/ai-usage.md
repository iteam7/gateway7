# AI usage — Week 06

## Tools

Codex with the GitHub connector prepared the provider-streaming and OpenCode increment in [task #153](https://github.com/iteam7/gateway7/issues/153).
Codex used separate Formater, TechLead, core-model/middleware, provider-streaming, API and harness-verification agents under the repository's agent workflow.
OpenCode V2.2.2 was the real external harness used for the local synthetic integration check; it did not generate the gateway implementation.

## What the tools were used for

Codex inspected the current Gateway7 and OpenCode protocol sources, prepared typed function-tool messages, collected and validated actual upstream OpenAI-format SSE, retained complete response middleware before downstream SSE, and extended the existing API, provider and policy tests.
The agents also updated the API and plugin documentation, proposed ADR-005, and added FR-013 for the guarded agent exchange.
Formater prepared an isolated checkout from main and ran the repository checks.
TechLead reviewed the integration and its boundaries.

The harness verifier ran OpenCode against a deterministic local OpenAI-format upstream with synthetic credentials and a synthetic local file.
The normal scenario required a function call, local tool execution, a matching tool-result request and a final answer containing the file's control string.
The blocked-argument scenario required a policy denial before any tool execution or final assistant text.
These checks establish those selected scenarios against the scripted upstream; they are not evidence of a live OpenAI account run or general compatibility with every OpenCode feature.

## What was done with the output

The agents retained full-message response checks and explicitly documented buffered downstream delivery, rather than claiming generation-time token delivery.
The review tightened structured policy coverage, tool history and capability checks, terminal stream validation, safe accounting, and native text API regression behavior.
The implementation reuses existing negative test parametrizations and adds positive stream and function-tool checks.
A full-suite-only admission-test failure was traced to a measured 66.61 ms generation-2 garbage collection inside its 30 ms request budget.
The test now collects unrelated setup cycles before scheduling that timed request; its timeout, capacity, cancellation and no-late-forwarding assertions remain unchanged.
The full automated suite passed with 1077 tests and 11 skips, and the local documentation checks passed.
The all-Markdown external link check remained incomplete after the execution network timed out on GitHub; no exclusions were added and no external availability pass was claimed.
No Customer verdict, team decision, live-provider result, release, deployment or acceptance of task criteria was inferred from generated code or a synthetic run.

## Pull request preparation

After the user's explicit request to create a pull request, Codex prepared publication against the updated main branch.
That branch had already published FR-012 for developer usage reporting, so the unpublished guarded-agent draft was assigned FR-013 before its first publication.
The published FR-012, project plan and Week 05 report were preserved byte for byte; both requirements remain in the index and navigation.
No runtime source changed during this documentation integration.

## Team assessment

TODO: the team records which generated output it accepted, changed or rejected and why after its own review.

## Observability signals and the active SLI

Claude Code (a cloud session started from the project chat) prepared [task #181](https://github.com/iteam7/gateway7/issues/181) at DeniBorsh's request.
It read Assignment 6 and the course's observability requirements, then added `gateway7/telemetry.py`, which exports one structured log record and one request-duration histogram observation per API request over OTLP/HTTP when `TELEMETRY_ENABLED` is true.
It rewrote `docs/observability.md` as the observability plan with SLI-01, added FR-014, the operation terms in the glossary, the gateway's telemetry configuration in the deployment guide, `.env.example` and live Compose, and the tests in `tests/test_telemetry.py`.

The session checked the export against a local OpenObserve v1.1.2 container with synthetic credentials and the synthetic demo provider.
That check showed that a cumulative histogram's first failure gives a `NaN` five-minute P95 under `rate`, so the export uses delta temporality and the SLI query sums the window instead.
The local check is not staging evidence: no university VM, staging organization or dashboard was used, and no QRT result is claimed.

### Team evaluation for the observability signals

TODO: the team records which generated output it accepted, changed or rejected and why after its own review.

## Staging diagnosability requirement and check

The same Claude Code session prepared [task #185](https://github.com/iteam7/gateway7/issues/185): QR-05 with its deployed QRT-01, its index and testing-plan rows, and `scripts/check_sli.py` with a test against a scripted gateway and OpenObserve stand-in.
It ran the script against the synthetic demo gateway and a local OpenObserve v1.1.2 container, where it printed `PASS QR-05 QRT-01`; that run is a development check, not the staging result.
The testing-plan row stays `Not verified` until a member runs the check against staging from the university network and records its output, commit and screenshot.

### Team evaluation for the diagnosability requirement

TODO: the team records which generated output it accepted, changed or rejected and why after its own review.

## Staging SLI dashboard definition

For [task #183](https://github.com/iteam7/gateway7/issues/183), the same session built the SLI-01 chart in a local OpenObserve v1.1.2 organization, rendered it with a headless browser to confirm separate `ok` and `client_error` series, and tracked the sanitized definition in `monitoring/openobserve/gateway7-sli-dashboard.json` with a test that keeps its query equal to the plan's.
The staging dashboard itself, its failure-traffic check and its sanitized screenshot need the university VM and remain for a member to produce; the local rendering is not that evidence and is not committed.

### Team evaluation for the dashboard definition

TODO: the team records which generated output it accepted, changed or rejected and why after its own review.
