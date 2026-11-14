# AI usage — Week 07

## 2026-11-06 — Implementation verification and earlier acceptance

- Tools: OpenCode; Codex CLI 0.153.4 for the isolated synthetic harness.
- Work: Scoped implementation review, regression support, harness verification, read-only inventories and evidence reconciliation.
- Results: The 3093-test code QA and later 3102-test parser checkpoint passed on their recorded revisions.
  Package, demo, monitoring Compose, full documentation, Chat/OpenCode and isolated synthetic Codex read/full-correlated-result replay evidence retain their original scopes, not blanket current-source approval or concurrent-process coverage.
- Native acceptance: Earlier SSE validation failed; later JSON, checked buffered SSE and an independent early-text case passed on their tested revisions.
  The early case delivered 79 nonempty events out of 87 before upstream completion/EOF; this is not full-profile time-to-first-token proof.
  A named-function response failed DTO validation on the earlier revision, and replay was not run.
  The rejected live field was not retained, so later compatibility corrections do not establish its identity.
- Team assessment: TODO

## 2026-11-09 — Final compatibility verification and disclosure

- Tool: OpenCode.
- Work: TEMP artifact recovery, exact-proposal and actual-diff review tracking, nullable response-tool compatibility correction, affected Python QA, fresh intended-diff/privacy checks and disclosure preparation.
- Current offline result: The nine-file correction is independently actual-diff approved and accepts omitted/null-only response-tool echoes without changing request/history contracts.
  Current affected QA passed 3119 tests with zero failures, skips, xfails or deselections, including all 11 Compose-configuration cases; Ruff format/lint and mypy passed for 34 production files.
  Earlier package/demo/monitoring/docs/client/live-text evidence was not rerun or promoted to the final revision.
- Final live result: Exactly one upstream attempt returned HTTP 403 in the authentication category; replay and final stages were gated and not run.
  No raw cause or error code was retained, so invalid-key, region, billing and DTO-regression explanations are not established.
  Usage and monetary cost are unknown, not zero; owned clients, servers, process groups and private prefixes were reported cleaned up.
- Accounting: 17 NEW implementation upstream attempts are closed; historical audit attempts remain separate and are not summed into this total.
  No retry, diagnostic or additional runtime allocation is authorized.
- Outcome: CHANGES REQUIRED / external live acceptance BLOCKED; the current named-call/result/final cycle remains unverified, and HTTP 403 does not establish a product defect.
  Any external follow-up requires separate explicit authorization; no readiness, team/Customer decision or weekly-assignment completion is claimed.
- Team assessment: TODO

## 2026-11-09 — Publication preparation and Git workflow

- Tool: OpenCode.
- Use: Publication preparation and Git workflow: repository/course checks, intended-diff review, remote refresh, follow-up [task #220](https://github.com/iteam7/gateway7/issues/220) creation and branch naming.
- Publication boundary: One intended commit and a Draft PR; no merge, force push, history rewrite or new runtime allocation.
- Verification boundary: The branch is 80 commits behind fetched main; retained local tests are not merged-result verification, and the external HTTP 403 live-acceptance blocker remains unresolved.
- Team assessment: TODO

## 2026-11-09 — Historical report provenance

- Tool: OpenCode.
- Use: Read-only mapping of the Week 06 AI-usage merge conflict.
- Historical evidence: The feature-side Week 06 report, including its 121 additions relative to the common base, remains preserved verbatim at [commit 1dfc87b160d9445c36a046219b4af1773a037744](https://github.com/iteam7/gateway7/blob/1dfc87b160d9445c36a046219b4af1773a037744/reports/week-06/ai-usage.md).
  This is an earlier audit record, not work newly performed, rerun or reassessed in Week 07.
- Team assessment: TODO

## 2026-11-10 — Main integration and publication preparation

- Tool: OpenCode.
- Use: Reviewed the pending main-into-feature merge and prepared its ordinary merge commit and normal push to the existing Draft PR; actual source, documentation and report-mapping reviews were approved.
- Preservation: Canonical main Week 06 is retained, and the existing Week 07 body and immutable historical report reference are unchanged.
- Merged Python QA: 3249 passed with zero failures, errors, skips, xfails, xpasses or deselections, including all 12 Compose-configuration cases; Ruff format/lint, mypy for 36 production files and one synthetic demo passed.
  The isolated environment used genuine project metadata 0.4.0 without changing the 52 locked dependencies; the earlier 3119-test result remains historical, not merged-source validation.
- Documentation QA: 111 Markdown files/zero issues, strict MkDocs, site checks for 59 pages/7141 links-assets, Lychee nine changed pages/301 successes/zero errors/exclusions and actionlint six workflows passed before this append.
- Publication boundary: This entry records verification and publication preparation, not a PR merge, release or human acceptance; the request remains Draft.
- Live boundary: The last named request returned HTTP 403 in the authentication category; cause, usage and cost are unknown, replay/final were not run, and the 17 NEW implementation attempts remain closed with no additional provider calls or live-runtime allocation.
- Team assessment: TODO

## 2026-11-10 — Bounded proxy verification

- Tool: OpenCode.
- Work: Verified the current Gateway/Pipeline/HTTPProvider native Responses path with gpt-4.1-mini through the selected second distinct valid HTTP proxy.
- Route: The first nonbillable models probe timed out before any HTTP status; a separately allocated second-proxy probe returned HTTP 200 with verified production CONNECT routing.
  Each generation call matched the current selected proxy and verified official-target SNI/TLS; the two calls used two TCP connections, two CONNECTs and two POST-header transmissions, without retries, extra probes or direct fallback.
- Result: Both gateway/upstream POSTs returned HTTP 200; forced named function, deterministic lookup, replay of the complete actual ordered output plus its correlated function result, and exact final marker passed, including strict SDK/native identity, argument, distinct call/item identity and source/client usage checks.
- Usage: First call 65 input/6 output/71 total; second call 86 input/10 output/96 total; aggregate 151 input/16 output/167 total, with monetary cost unknown.
- Isolation: Python 3.12.14, HTTPX 0.28.1 and OpenAI SDK 3.41; 52 locked dependencies and source/configuration bindings were unchanged, exporters were disabled, owned responses/apps/provider clients/transports were closed and the worker was reaped with no owned runtime remaining.
- Accounting: These two NEW generation calls are closed separately from the historical 17 implementation attempts, with no allocations remaining.
- Scope: The previously blocked named/result/final acceptance passed for this current proxy route and these two calls; the historical HTTP 403 cause remains unknown, and the first timeout does not establish key invalidity or a dead proxy.
  Proxy continuity uses only the ordinal/selection rule, not historical secret-value equality; this is not universal OpenAI compatibility, custom/media/hosted execution, production rollout or required human PR acceptance.
- Team assessment: TODO

## 2026-11-10 — Proxy verification publication preparation

- Tool: OpenCode.
- Use: Checked repository/course rules, the report-only diff, source/configuration preservation, remote branch and Task/PR mapping, and prepared publication of the completed proxy verification in the existing Draft PR.
- Boundary: No product source or configuration changed and no tests, harnesses or provider calls were repeated; the bounded proxy PASS does not establish the historical HTTP 403 cause or universal compatibility.
- Team assessment: TODO

## 2026-11-11 — Task 222 startup and model access

- Tool: OpenCode.
- Use: Implemented and documented [Task #222](https://github.com/iteam7/gateway7/issues/222): explicit `serve --secrets-file` startup and optional provider/client model limits.
- Access: Effective limits intersect; an absent list imposes no restriction at that level and `[]` denies all models, with authentication and privacy preserved.
- Catalog: Added authenticated, bounded cached OpenAI discovery and opaque model IDs for the supported text Chat/Responses APIs; catalog presence does not prove endpoint or modality compatibility.
- Review: Independent actual-diff reviews approved the implementation, documentation and two-fixture correction after the CLI lifecycle findings were closed.
- Verification: Final full pytest passed 3566 tests without failures, errors, skips or deselections; formatting, lint, types, compilation, synthetic demo, wheel build, outside-checkout locked runtime installation, installed CLI/authoring/synthetic smoke and corrected provenance checks passed.
- Documentation: Strict site validation, corrected current-checkout Markdown and the five-page link check passed.
- Boundary: Historical failing runs remain historical; no real provider-account, upstream catalog or live generation verification was performed for this task, and universal compatibility is not claimed.
- Team assessment: TODO

## 2026-11-11 — Task 222 publication preparation

- Tool: OpenCode.
- Use: Checked current rules, Task #222 and branch/PR mapping, reviewed the intended diff and prepared its authorized commit and Draft PR publication.
- Boundary: Reused the closed implementation checks without repeating product, provider or live-account tests; publication does not establish rollout, universal compatibility or human approval.
- Team assessment: TODO

## 2026-11-11 — Task #223

- Tool: Codex.
- Work: Reject ambiguous JSON in native and Chat requests.
- Verification: 295 affected native/Chat/Responses HTTP tests passed; Ruff format/lint and mypy for app.py passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #224

- Tool: Codex.
- Work: Enforce final JSON response delivery deadlines.
- Verification: 370 affected native/Chat/stream/Responses HTTP tests passed; Ruff format/lint and mypy for app.py passed.
- Follow-up: The existing post-header metrics case now expects cancellation for a downstream OSError, matching checked Responses delivery; 255 affected metrics/core/Responses tests passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #225

- Tool: Codex.
- Work: Preserve safe Allow headers on HTTP 405 errors.
- Verification: 298 affected core, OpenAI HTTP and access tests passed; Ruff format/lint and mypy for app.py passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #226

- Tool: Codex.
- Work: Reject ambiguous nonstreaming provider JSON responses.
- Verification: 500 targeted provider/transport tests passed; Ruff format/lint and mypy for all 36 production files passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #227

- Tool: Codex.
- Work: Complete Chat provider stream cleanup despite cancellation.
- Verification: 813 affected provider, Responses and proxy tests plus 233 HTTP/early-stream tests passed; Ruff format/lint and mypy for all 37 production files passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #228

- Tool: Codex.
- Work: Preserve cancellation and deadlines in buffered Chat calls.
- Verification: 397 affected core, early and native pipeline tests passed; Ruff format/lint and mypy for all 36 production modules passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #229

- Tool: Codex.
- Work: Validate plugin topology before constructing middleware.
- Verification: 128 affected core and plugin tests passed; Ruff format/lint and mypy for all 36 production files passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #230: Bound YAML configuration parsing and alias traversal

- Tool: Codex in ChatGPT Work Mode.
- Work: Implemented byte-bounded YAML loading and one graph-validation pass with memoized alias depths, plus synthetic file/graph regressions and the documented limits.
- Verification: 153 affected configuration, CLI and offline tooling tests passed; Ruff format/lint and mypy for 36 production files passed.
- Additional checks: The synthetic HTTP demonstration, wheel build, strict MkDocs build, 59-page/7,141-link site check and affected Markdown lint passed.
- Review: The separate TechLead agent approved the actual implementation, tests and documentation; team-member review remains pending.
- Boundary: Synthetic checks only; no live provider calls, deployment, release, merge or Customer acceptance was performed.
- Team assessment: TODO

## 2026-11-11 — Task #231

- Tool: Codex.
- Work: Reject ambiguous and unbounded JSON in Chat SSE events.
- Verification: 840 affected provider-stream tests passed, including 19 new strict-event regressions; Ruff format/lint and mypy for all 36 production modules passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #232

- Tool: Codex.
- Work: Revalidate nested Chat middleware state before forwarding.
- Verification: 405 targeted pipeline tests and the full suite passed: 3253 passed, 12 Docker-dependent skips; Ruff format/lint and mypy for all 36 production modules passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #233

- Tool: Codex.
- Work: Reject inconsistent partial Responses usage totals.
- Verification: 984 affected native Responses tests and the full suite passed: 3254 passed, 12 Docker-dependent skips; Ruff format/lint and mypy for all 36 production modules passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #234: Generate plugin dependencies for the current Gateway7 API

- Tool: Codex in ChatGPT Work Mode.
- Work: Aligned generated package metadata with the running Gateway7 minor version and documented the range; validated current and future version examples and the generated offline project.
- Verification: 34 scaffold, offline tooling and testability tests passed; Ruff format/lint and mypy for 36 production files passed.
- Additional checks: The synthetic HTTP demonstration, wheel build, strict MkDocs build, 59-page/7,141-link site check and affected Markdown lint passed.
- Review: The separate TechLead agent approved the actual implementation, tests and documentation; team-member review remains pending.
- Boundary: Synthetic checks only; no live provider calls, deployment, release, merge or Customer acceptance was performed.
- Team assessment: TODO

## 2026-11-11 — Task #235: Keep telemetry resource attributes within the privacy allowlist

- Tool: Codex in ChatGPT Work Mode.
- Work: Replaced ambient resource detection with the fixed service/environment resource allowlist and checked actual exported synthetic log/metric resources.
- Verification: 107 telemetry, SLI and analytics tests passed; Ruff format/lint and mypy for 36 production files passed.
- Additional checks: The synthetic HTTP demonstration, wheel build, strict MkDocs build, 59-page/7,141-link site check and affected Markdown lint passed.
- Review: The separate TechLead agent approved the actual implementation, tests and documentation; team-member review remains pending.
- Boundary: Synthetic checks only; no live provider calls, deployment, release, merge or Customer acceptance was performed.
- Team assessment: TODO

## 2026-11-11 — Task #236

- Tool: Codex.
- Work: Retain observed Chat usage when response cleanup fails, on top of the strict decoder from task #226.
- Verification: 628 affected provider, transport and usage-metric tests passed; Ruff format/lint and mypy for all 36 production files passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Source-reported counts are observed accounting, not proof of transport completion, successful output or monetary cost.
  Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #238

- Tool: Codex.
- Work: Add stable client identities and account suspension.
- Verification: 258 affected access, model routing, Chat and Responses tests passed; Ruff format/lint, mypy for config.py/auth.py and both changed documents markdownlint passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #239

- Tool: Codex.
- Work: Enforce per-client concurrent request limits.
- Verification: Full suite passed: 3285 passed, 12 Docker-dependent skips; 63 targeted admission tests, Ruff format/lint, mypy for all 36 production files, Markdown, strict MkDocs and site checker (60 pages, 7323 links/assets) passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #240

- Tool: Codex.
- Work: Enforce per-client request-rate quotas.
- Verification: Full suite passed: 3311 passed, 12 Docker-dependent skips; 481 affected tests, Ruff format/lint, mypy for all 36 production modules, Markdown, strict MkDocs and site checker (61 pages, 7504 links/assets) passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #241

- Tool: Codex.
- Work: Apply additional content-policy chains per client.
- Verification: Combined full suite passed: 3357 passed, 12 Docker-dependent skips; 134 focused policy/admission tests and 5 INFO privacy cases passed. Ruff format/lint, mypy for all 37 production modules, synthetic demo, wheel, Markdown, strict MkDocs and site checker (62 pages, 7681 links/assets) passed.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #242

- Tool: Codex.
- Work: Expose an authenticated operator-only client usage snapshot.
- Verification: Final full suite passed: 3455 passed, 12 Docker-dependent skips; 98 feature tests and 704 affected tests passed. Ruff format/lint, mypy for all 38 production modules, Markdown, strict MkDocs and site checker (63 pages, 7868 links/assets) passed. Independent review covered buffered cancellation/late usage and partial native error accounting.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Task #257

- Tool: Codex.
- Work: Add a read-only operator web console.
- Verification: Final full suite passed: 3478 passed, 12 Docker-dependent skips; 23 console API cases, Ruff format/lint, mypy for all 39 production modules, demo, wheel and extracted-wheel assets passed. JavaScript syntax, Markdown, strict MkDocs and site checker (64 pages, 8061 links/assets) passed. Actual Gateway browser verification covered separate operator authentication, refresh, logout, suspended clients, limits, policy order and known/unknown usage; owned preview servers were stopped.
- Review: Independent TechLead code review approved the implementation; this is technical review, not team or Customer acceptance.
- Boundary: Synthetic local checks only; no external provider calls, deployment or merge.
- Team assessment: TODO

## 2026-11-11 — Aggregate release review (Task #263)

- Tool: Codex.
- Work: Consolidated the twenty reviewed hardening, client-control and operator-console changes into one release-review branch and PR at the repository owner's request.
- Provenance: Refreshed main and every component PR head; remote head SHAs matched the recorded component manifest, and component trees matched the reviewed checkpoints.
  The resolved merge preserves current main and the actual remote component commit histories, with the original PRs and branches retained.
- Verification reuse: Product source, tests, maintained documentation and assets are unchanged from the approved integration; its 3665 passed tests, 12 local Docker-dependent skips, formatting, lint, types, demo, wheel/assets, JavaScript and documentation results are reused by exact-tree comparison, not presented as a new run.
- Current checks: The aggregation disclosure passed Markdown lint and whitespace checks; new aggregate CI is reported on the PR.
- Review shape: The owner requested one combined colleague-review link instead of twenty separate review links; the component work remains traceable in the aggregate PR.
- Boundary: No task #222 or unrelated branch import, new product behavior, main merge, version bump, tag, deployment or GitHub Release publication.
- Team assessment: TODO

## 2026-11-11 — Task 222 main integration

- Tool: OpenCode.
- Use: Resolved ordinary main-into-feature integration for [Task #222](https://github.com/iteam7/gateway7/issues/222) and prepared the existing Draft PR update, preserving main client controls, unrestricted-model console projection and catalog exemption from generation admission.
- Review: Independent actual-diff reviews approved the 14-file source integration, four documentation files, exact report union and deterministic real-Timeout deadline-test correction; production deadlines were not increased.
- Verification: Latest merged-source full pytest passed all 4006 tests with zero failures/errors/skips, and one unchanged synthetic demo passed all 15 checkpoints; earlier production Ruff formatting/lint and mypy checks remain applicable without repetition.
  Documentation QA passed full Markdown (116 files), strict MkDocs/site checks (64 pages, 8070 links/assets) and five-page Lychee (79 successes, zero errors/exclusions).
- History: Earlier 4005-pass/one-failure pytest and demo exit 1 remain historical failed runs; the latest fresh passes clear the latest gates, not the still-unknown historical demo failure cause.
- Preservation: Both published report histories and all 30 existing team-assessment placeholders remain verbatim; finished-week evidence and released changelog history are unchanged.
- Boundary: Synthetic local validation only; no new live provider/catalog/generation, installed-package verification, rollout, PR merge or human acceptance is claimed.
- Team assessment: TODO

## 2026-11-11 — Task #222 PR review correction

- Tool: Codex.
- Work: Fixed cancellation of explicit-secrets local startup when an API-v2 middleware catches cancellation and returns; the lifecycle receives the original cancellation through its finish signal and completes owned cleanup before it propagates.
- Regression: A real Gateway/API-v2 plugin test fails against the reviewed PR head and passes with the fix; it checks repeated cancellation during cleanup, original cancellation identity, same-task lifespan ownership, restored synthetic environment, no server start and no surviving owned jobs.
- Verification: The corrected source passed 80 focused CLI/private-file tests and one full pytest run with 3995 passes and 12 local skips because Docker Compose is unavailable.
  Production Ruff formatting/lint and mypy passed for all 41 files; the unchanged synthetic demo and wheel build passed.
- Review: Independent actual-diff TechLead review approved the narrow handshake correction and regression; earlier Task #222 evidence above remains historical and unchanged.
- Boundary: No real credential files, existing launcher/server, live providers, model permissions/catalog behavior, dependencies, deployment or merge were changed.
- Team assessment: TODO

## 2026-11-13 — Issue housekeeping for previous sprints

- Tool: DeepSeek Harness (DSH).
- Work: At the team lead's explicit instruction, the session closed the previous-sprint issues #175, #176, #178, #182, #185 and #189 as completed through the team lead's GitHub account (`ExFuseMe`); the issue events record the closures at `2026-11-13T14:38Z`, and the reopen-and-close of #175 and #185 during the review is part of that history.
  The team lead confirmed that the work was delivered outside the repository and decided that the closures stand after the Formater review raised the missing record evidence.
  The repository itself does not show the planned velocity for #176, the production scopes for #178 and #182, the QRT result for #185, the `REL-06` tag for #189, or the Customer acceptance for story #175; the closure of those items is the team lead's record decision, not new evidence.
  The Formater review withheld its approval on that tracker state; the divergence is recorded here, and the reopen-and-close history is in the comments on [#175](https://github.com/iteam7/gateway7/issues/175) and [#185](https://github.com/iteam7/gateway7/issues/185).
- Boundary: No code, documentation, release, tag or deployment changed; the closures and the reopen-and-close are tracker actions only.
- Team assessment: TODO

## 2026-11-13 — Task #267: UT-01 design and QR-06

- Tool: DeepSeek Harness (DSH), with a Formater POST review and a TechLead gap review.
- Work: Designed UT-01 under Assignment 7: the test record, the surveys, the consent template, the session template with its observation sheet and dry run, the results stub, QR-06 with its manual QRT-01, the quality matrix and testing-plan rows, ten glossary terms, four risks, and the site navigation.
- Accepted: the course's standard SEQ and SUS instruments and the `Critical` / `Major` / `Minor` severity classes.
- Changed: the severity scale, the placement of session dates, the stop rule, the Metric and Statistic definitions, and the results tables; each change came from a Formater finding against the course requirements.
- Rejected: nothing; no generated requirement, finding or measurement was kept without a rule behind it.
- No usability material: no participant data, session note or recording exists yet, so no agent was given one; only the design text was shared with the subagents.
- Verification: markdownlint reported zero issues, `lychee --offline` zero errors, and `mkdocs build --strict` with `docs-build/check_site.py` passed.
- Boundary: The design claims no participant data, usability result, verdict, Customer decision or release; nothing was committed, pushed or published by this entry.
- Team assessment: TODO

## 2026-11-13 — UT-01 design confirmation and issue #267 follow-up

- Tool: Codex.
- Work: Rebased the existing UT-01 design from closed PR #273 onto the current `main` base, checked it against the pinned Assignment 7 and usability-testing requirements, and added an explicit task-to-instrumentation map.
- Team confirmation: DeniBorsh ratified the documented scenarios, participant profile, QR-06 Learnability measure and SEQ bar, SPRINT-08 run plan, and the facilitator, observer and data-custodian assignments on 13 November 2026.
- Boundary: This entry records that team confirmation only. It does not claim Customer review, pilot, participant data, findings, QR verdict, or Week 7 results; Customer review/pilot remains tracked by #270.
- Team assessment: TODO

## 2026-11-14 — Task #270 Customer design-review preparation

- Tool: Codex, TechLead.
- Work: Prepare a 30-minute live review script against the team-confirmed UT-01 design in PR #275, with three separate permissions before recording, actual production/staging demonstrations, prior-source questions, execution-plan agreement and decision/action read-back.
- Verification: Check the five required script sections, 30-minute agenda, question-to-agenda assignment and linked artifacts; the script distinguishes prepared design from demonstrated readiness.
- Boundary: No meeting slot, review roles, pilot, permission answer, Customer decision or agreed action is invented; #270 remains incomplete until the actual pilot/review and rework are evidenced.
- Team assessment: TODO
