# AI usage — Week 09

## 2026-11-27 — Prepare the Sprint 9 record, script and plan

- Tool: DeepSeek Harness coding agent with repository file tools, `npx markdownlint-cli2` and the GitHub CLI.
- Work: Wrote `docs/user-acceptance-tests.md` with `UAT-01` to `UAT-03` against the deployed `config/claude.yaml`, wrote `reports/week-09/meeting-script.md`, planned `SPRINT-09` and added the provisional `SPRINT-10` in `docs/project-plan.md`, and corrected the milestone inventory in `CONTRIBUTING.md`.
- Verification: markdownlint-cli2 reported 0 issues on every changed Markdown file; each expected result was traced to its source — `policy_denied` in `gateway7/errors.py`, `model_forbidden` in `docs/authentication.md` and the masking outputs in `config/claude.yaml`; no product code ran and no deployment was checked.
- Boundary: No meeting, decision, UAT run or Customer verdict was created; the script leaves every role `to confirm` and the UAT record has no run rows. Only synthetic values appear: a fake address, a fake number and a test term.
- Team assessment: TODO

## 2026-11-23 — Correct five PR #336 review findings

- Tool: OpenAI Codex with separate implementation, architecture review and verification agents.
- Work: Corrected session publication during cancellation, unrelated-session authentication failures, cancellation-safe management cleanup, mobile keyboard/accessibility navigation and email-preview match counts in the existing pull request.
- Verification: Session and cleanup regressions passed 48 checks on SQLite and disposable PostgreSQL; an independent reviewer repeated 16 backend cases. Console checks passed 34 cases including eight real Chromium journeys and accessibility-tree checks. Email preview/protected-field checks passed 11 cases and the reference middleware suite passed 264 cases; independent policy/console checks passed 102 cases.
- Full suite: 4,656 passed and nine optional/browser cases skipped on the final frozen sources with isolated PostgreSQL; the eight browser journeys passed separately in Chromium.
- Artifacts: A fresh installed wheel outside the checkout matches all 72 shipped sources/assets and passes the ordinary account/session/policy/restart/bearer flow; an independent installed check confirms valid concurrent sessions remain usable and two-address preview counts two matches. Format, lint, types and the strict 99-page site passed. The final full-suite and exact-head CI results are recorded with PR #336.
- Boundary: Only local synthetic accounts and disposable databases were used. No live target, real credential, additional feature, dependency, package version or workflow change was involved.
- Team assessment: TODO

## 2026-11-23 — Administration workspace for #335

- Tool: OpenAI Codex with separate implementation, architecture review and verification agents; GitHub CLI, pytest, Chromium, Docker Compose and the repository documentation tools.
- Work: Implemented password accounts and durable browser sessions, declarative policy administration, and a routed responsive console; updated configuration inventory, architecture and guides.
- Verification: The initial PostgreSQL-backed full suite passed 4,628 cases and skipped five browser/optional cases; two authentication-order regressions and stale local distribution metadata failed. The authentication fix preserved the original strict assertions and passed both previously failing cases plus all session cases on SQLite and PostgreSQL (29 passed); locked environment refresh made the release metadata check pass. Format, lint and package types passed.
- Independent checks: Reviewed access, CSRF, revocation and policy boundaries; exercised a disposable PostgreSQL deployment through a certificate-verified local HTTPS proxy. Secure cookies survived reload, gateway restart and container recreation; logout invalidated the session. Direct HTTP login was rejected. Browser and final artifact results are recorded with the pull request.
- Final artifacts: Built a fresh wheel and compared all 72 package sources/assets with the checkout and installed files. From an isolated environment outside the checkout, exercised account creation, cookie/CSRF authentication, real policy denial, restart, logout, bearer precedence and new asset serving. The demo, 21-file Markdown check and 808-link check passed; the final console run passed 33 cases including seven real Chromium journeys. TechLead independently approved the final browser journey and settled desktop/mobile captures. A repeat Docker build hit the local disk limit; the exact final image and monitoring stack are checked by CI.
- Boundary: Only synthetic accounts, credentials, messages and disposable databases were used. Existing bearer recovery remains available; no custom policy code, dependency, workflow or release changes were introduced. The current course assignment URL returned 404, so no Week 09 assignment-completion claim is made.
- Team assessment: TODO

## 2026-11-23 — Fix Markdown lint errors for #77

- Tool: Codex.
- Work: Added the missing blank line before the Week 8 report heading and restored the final newline in this file.
- Verification: Ran markdownlint on both affected AI-use reports; 0 issues.
- Boundary: Documentation formatting only; no tests or product code changed.
- Team assessment: TODO

## 2026-11-22 — Repair failed Windows checks for #77

- Tool: Codex.
- Work: Inspected the latest Windows CI failures, mapped the 21 failed pytest cases, and corrected the isolated Windows subprocess environment and a platform-dependent path assertion in tests/test_smoke_codex.py.
- Verification: Ran only the 21 cases that failed in the latest Windows CI run; all 21 passed locally in 8.36 seconds. Ruff formatting and lint checks passed for the changed test file. The full suite was not run.
- Boundary: Test-only changes; no product behavior or customer data changed. The Windows CI workflow has not yet rerun on this local change.
- Team assessment: TODO
