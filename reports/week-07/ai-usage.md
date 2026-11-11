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
