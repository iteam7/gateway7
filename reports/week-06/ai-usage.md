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

## Threshold review and Customer Review preparation

Codex used the GitHub connector and separate Formater, executing and reviewing agents to prepare [task #187](https://github.com/iteam7/gateway7/issues/187) and the evidence-ready parts of [task #188](https://github.com/iteam7/gateway7/issues/188).
The work compared the four existing threshold measures with dated repository records, preserved the original deadlines and unadopted proposals, and used the recorded plugin-installation run and DEC-020 contributor confirmation for the two supported outcomes.
It first drafted the four-dashboard readiness map and a live meeting script with explicit per-story verdict questions, Week 5 follow-ups and a request for actual Week 7 actions.
The representative approved that outline on 5 November and clarified the planned meeting date on 6 November.
That approval concerned preparation, not a meeting outcome or agreement on its proposed follow-ups.
The ongoing task removed a prematurely drafted meeting report and retained the distinction between source evidence and Customer validation.

On 7 November the representative reported that no Review had taken place because the demonstration was not ready.
Codex used that correction to record the unfulfilled Review and its exact reason, preserve the unused live script byte for byte, and prepare the canonical script for a proposed written exchange.
The written script was not sent and supplies no Customer response or completed Review.
The weekly report now maps actual merged evidence and the outstanding Assignment 6 requirements to their owner issues, rather than treating an issue, a source-level CI pass or a planned dashboard as proof of deployment.
After the representative reported PR #196 merged, Codex refreshed the readiness and coverage index against main `22ecc152f57ad096cd942050cd46d6d3457fb93d`, including its analytics plan and events, FR-015, proposed ADR-006/007, feature entries, external-backend container view, canonical QR-05/QRT script and dashboard definition.
The update links the six successful main-branch workflows and merged task-closing PR #196, while retaining the missing backend-computed metric, four dashboard screenshots and actual staging QRT result.
It also corrects the operator example so the QRT receives process environment variables and staging smoke mode is restored on exit.
No staging availability, deployed QRT or analytics value is inferred from the source or CI.
The only project-plan change aligns SPRINT-06 Due with the course's 8 November deadline; no commitment, velocity or release record is reconstructed.

No attendance, permission answer, dashboard demonstration, measured QRT result, Customer decision, story verdict, agreed Week 7 action or team-wide assessment was inferred from generated preparation or the representative's outline approval.
A factual meeting report will be written only after an actual Review, using its real exchange and outcomes.
The existing assessment above belongs to the separate guarded-harness work and is not filled by inference from this preparation task.

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

## Product analytics and telemetry handoff

Codex used Formater, TechLead, analytics, diagnosability and infrastructure agents to prepare [task #177](https://github.com/iteam7/gateway7/issues/177) and the remaining telemetry handoff.
The GitHub connector supplied the current course rules, main and the team's branches; source review found that [PR #194](https://github.com/iteam7/gateway7/pull/194) and [PR #195](https://github.com/iteam7/gateway7/pull/195) had merged into working branches rather than main.
The integration preserves their canonical QR-05, `check_sli.py`, dashboard definition, tests and genuine commit history instead of adding parallel versions.

The agents implemented typed start/completion events, the bounded optional OpenPanel exporter, deployment-owned source labels, the analytics plan and FR-015, and prepared the telemetry runbook and architecture records.
TechLead changed the generated QRT integration to remove automatic paid-provider warmup, validate a forbidden model before the negative request, keep the queries staging-only, bound response sizes and deadlines, and print only known safe result fields.
The existing dashboard definition was retained byte for byte; the container diagram was rendered and visually checked.
A final review also moved the QRT clock to the last response bytes, before parsing or stream cleanup; two slow-cleanup regressions verify that neither deadline can be extended.
The team has not supplied an assessment of this new increment; no member acceptance is inferred from the AI review or automated checks.

Local checks passed: 1,154 automated tests with Docker-dependent cases skipped, Python compilation, formatting, linting, type checking, the separate-process synthetic demonstration and wheel build.
Formatting and lint checks also covered the changed test files and canonical QRT script.
GitHub CI exposed four stale exact Compose environment expectations for the five optional analytics variables; the correction preserves those strict comparisons, isolates the fixture environment and adds a staging process-override regression.
That correction requires the Docker-dependent checks in CI because Docker is unavailable locally.
The strict documentation build and generated-site check passed for 59 maintained pages and 7,022 links/assets; all four Compose files passed the official Compose JSON schema.
These local results include scripted HTTP protocol tests, not a deployed OpenPanel query, a university-VM QRT pass, four live dashboards or a production deployment.
Docker was unavailable in the execution environment, so the new backend stack was not started locally.
No live-provider call, Customer Review, Customer decision, release or Moodle submission was performed by this work.

## Codex: Sprint planning scope

- Tool: Codex.
- Use: recorded the current estimated scope while distinguishing it from the unverified planning commitment.
- Team assessment: TODO.

## Codex: Analytics deployment

- Tool: Codex.
- Use: documented the deployed analytics backend, proxy and remaining verification.
- Team assessment: TODO.

## Codex dashboard verification for #179

Codex configured and checked the staging OpenPanel chart and captured sanitized preview evidence for task #179.

### Team assessment

TODO: the team records its assessment of this work.

## Codex dashboard verification for #180

Codex configured and checked the production OpenPanel chart and captured a sanitized empty view for task #180; no synthetic traffic was sent to the production project.

### Team assessment

TODO: the team records its assessment of this work.

## Codex observability pipeline verification

Codex configured and inspected the OpenObserve VM instance, organization-scoped credentials and TLS proxy for task #182.
It checked cross-organization authentication, ran a staging-preview SLI test and recorded that legacy log delivery and regular-gateway deployment were not verified.
The provider key check returned a country or territory restriction and did not establish key validity.

### Team assessment

TODO: the team records its assessment of this work.

## Codex dashboard verification for #183

Codex checked the staging OpenObserve dashboard and captured the numeric failure series generated by a VM-hosted staging preview for task #183.

### Team assessment

TODO: the team records its assessment of this work.

## Codex dashboard verification for #184

Codex checked the production OpenObserve dashboard and captured its sanitized empty view for task #184; no synthetic failure was sent to production.

### Team assessment

TODO: the team records its assessment of this work.

## Codex staging QRT preview

Codex ran QR-05 QRT-01 against an isolated staging candidate on the university VM for task #185 and recorded the observed preview timings.
The regular staging result remains unverified; an unrelated direct provider request returned a country or territory restriction.

### Team assessment

TODO: the team records its assessment of this work.

## Codex: Release readiness

- Tool: Codex.
- Use: documented the release evidence and outstanding dependencies.
- Team assessment: TODO.

## Week 6 evidence review and integration

Codex used Formater and TechLead agents to review the prepared backend and dashboard pull requests against the current course rules, exact task criteria and source commits.
The work preserved the original disclosures above and prepared one shared readiness index so sequential evidence merges retain every contributor's record.
It recovered the staging SLI screenshot and candidate QRT narrative from closed, unmerged PR #202 and PR #204 instead of claiming that their absence from main meant the operator had not run the check.
The index distinguishes the operator-recorded candidate PASS from promotion, complete matching log-query evidence, a defined non-smoke metric result, Customer Review and release completion.
The source-backed TLS review identifies the private-CA handoff and the current native client's certificate-trust limit; it does not disable verification or claim to have tested the private endpoints.
The narrow preparation tasks retain the larger deployment and release tasks as open references rather than declaring their unfinished criteria complete.
A teammate merged PR #198 during this review; the agents refreshed the remaining five branch candidates against that main revision and retained the merged branch unchanged.
The later task clarification does not claim that PR #198 had a closing-task link before it merged.

The first Windows quality run for the documentation-only PR #201 returned 49 policy denials and one timeout; Linux and the inspected main revision passed.
Repeating that unchanged quality workflow passed; no test or gate was weakened.
This review made no VM connection, provider request, Customer contact, VPN change, release or Moodle submission, and did not infer a team-wide assessment from automated or AI review.
The team's assessment of this preparation is still to be supplied by a member.

## Task #192: US-04 technical reconciliation

Codex used Formater, TechLead and an implementation agent to reconcile the existing US-04 acceptance criteria with the policy denial and startup diagnostics.
The implementation pins the middleware identity in the runner and constrains the unsupported-action diagnostic instead of echoing arbitrary configuration or request content.
The work adds policy, API and confidentiality regressions and aligns FR-004 with the unchanged story criteria.
The contributor-reported Customer acceptance remains separate from these technical checks; this work does not create a new Customer decision or infer acceptance from passing tests.
On 7 November, Codex reconciled the unpublished change with the newly merged OTLP implementation, preserving the request's exported error code and adding a regression across both HTTP APIs.
The earlier observability implementation and its AI account above remain intact.

**Team assessment:** TODO: the team records which generated output it accepted, changed or rejected and why after its own review.

### Task form-route deviation

Task #192 was created through the GitHub API using the repository task form's sections and the native Task type, rather than by submitting the web form.
Its native Responsible, Accountable and Priority values, matching assignees, Sprint 06 milestone and project item were verified after creation.
This declaration does not waive the course form requirement; the Week 6 report owner must carry this deviation into the completed weekly report.

## Task #192: reconcile policy diagnostics with published OTLP telemetry

Codex used Formater, an implementing agent and TechLead review to port the previously reviewed policy diagnostics onto current main while preserving the published telemetry error-code ownership.
Two chat API regressions check that a policy denial retains the correct exported error code and middleware correlation.
The focused API, privacy and telemetry checks passed; this technical verification does not create a new Customer verdict or close the story.

**Team assessment:** TODO: the team records which generated output it accepted, changed or rejected and why after its own review.

### Current-main publication reconciliation

The diagnostics were ported onto main 529ee3529cdf5dec51bb948740e2ed1282261f46 after the OpenPanel analytics and QR-05 work had been published.
The port preserves the published analytics lifecycle, completion classification, OTLP error-code pin, requirements and existing AI history; focused checks and review are recorded for the new base.
No old OpenObserve analytics implementation or unpublished replacement FR/ADR is included.

## Task #210: confirmed Week 6 retrospective

On 8 November, Codex drafted a retrospective for the contributor's confirmation from the repository evidence and the carried Week 5 actions.
The contributor confirmed that the team had held the retrospective, reported a positive overall assessment and approved the proposed observations and four actions.
The documentation preserves that approved meaning in English, including the owners, impacts, reasons and next-retrospective follow-up, while retaining the original Week 5 action quotations.
It also records the contributor's confirmation that Customer Review would not take place before the deadline and keeps that unfulfilled requirement separate from the completed team retrospective.
The preparation-task fields and objective checklists were corrected under the contributor's explicit authorization, and the API-versus-Issue-Form route for tasks #192 and #206–#208 is disclosed in the public report.
No original planning commitment, formal Actual Velocity, Customer verdict, meeting transcript, final deployment or release is inferred from those confirmations.
This documentation work performs no additional VM check or provider request; the earlier candidate observations retain their recorded scope.
The retrospective wording confirmation is not treated as a team-wide assessment of all generated work, and no such additional assessment is supplied here.

## Task #212: source completion and release preparation

Codex used Formater, an implementing agent and independent review to complete the remaining repository work that could be verified without new operator evidence.
The source/acceptance audit reconciled US-04 against the three exact policy tests in PR #209 and its existing DEC-020 Customer acceptance, then completed #33 and the narrow tasks #181/#183/#186 with their actual FR/ADR links.
The published implementation reviews and original acceptance remain separate from this later tracking correction; no new Customer verdict or pre-merge review is invented.

The version audit found that package, runtime and public API metadata still reported 0.1.0 despite the published v0.3.0 tag.
The preparation aligns the next candidate at 0.4.0, derives the public OpenAPI version from the runtime constant and tests it against both installed distribution and project metadata.
The project lock was regenerated using the documented `uv lock` command; only the root package version changed, with no transitive upgrades.
The generated company-plugin package version, plugin API version 2 and historical release sections retain their original meaning.

The focused version regression passed, and the local full suite passed 1,176 tests with 12 Docker-dependent checks skipped because Docker was unavailable locally.
Compile, format, lint, type checks and the HTTP demo passed.
The hash-locked 0.4.0 wheel was installed in an isolated environment and checked outside the checkout with isolated Python and no source-path override: distribution, runtime, API and OpenAPI versions all reported 0.4.0.
These automated and AI review results do not supply a new team assessment of the generated output; that assessment remains for a member's review of this preparation.

The report and plan now distinguish 5 completed SP from the later 21-SP scheduled estimate and pending final Actual Velocity.
The remaining-story carryover is a proposal; no issue milestone, sprint state, release tag, VM deployment or Moodle submission is changed by the document.
The upgrade-note draft retains the missing Customer Review and operator evidence as outstanding facts, not a course-approved waiver.
No raw telemetry, private access information, numerical analytics result or new deployed-QRT outcome was generated for this preparation.

## Task 138 tracker correction

Codex corrected the current plan and Week 6 report from the live closed Sprint 05 milestone without rewriting Week 5 history or inventing the original commitment.
Local links and whitespace passed; Markdown lint could not start because of a temporary dependency error. Site and external-link checks remain for PR CI.
TechLead approved the narrow factual correction; human Accountable review remains pending.
Team assessment: TODO.

