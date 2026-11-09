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
