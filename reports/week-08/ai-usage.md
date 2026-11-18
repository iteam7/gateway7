# AI usage — Week 08

## 2026-11-15 — Task #288 operator user management

- Tool: Codex, with Formater, TechLead and developer agents following the repository roles.
- Work: Inspected the existing protected operator console, client authentication, access limits, middleware selection and usage accounting; prepared [task #288](https://github.com/iteam7/gateway7/issues/288) and its implementation pull request.
- Scope: Implemented browser client creation, editing, suspension, restoration, deletion and one-time credential issuance, rotation and revocation; model permissions, concurrency and rate limits and additional middleware apply to subsequent requests without a restart.
  Opt-in private SQLite storage preserves client policies, token digests and client/model/UTC-day usage aggregates across restarts; the console filters and exports known totals and unknown-usage counts.
- Automated verification: The full regression suite passed 4104 tests in 82.19 seconds before the final narrow bootstrap-selector validation correction; all 23 affected storage tests, including four added regressions, then passed.
  Python compilation, Ruff formatting and lint and mypy passed for all 43 production files.
- Packaging and documentation: The deterministic HTTP demo, wheel build and an installed-wheel smoke outside the checkout passed, including packaged console assets, account creation, rotation, authorization, restart, suspension, deletion, export and token-digest privacy.
  Strict MkDocs and the generated-site check passed for 73 maintained pages and 10037 links/assets; Markdownlint passed all 130 Markdown files, and Lychee reported 407 successful changed-file link checks with no errors or exclusions.
- Browser verification: Real Chromium with synthetic local services exercised the complete account lifecycle, actual middleware masking and denial, usage filters and CSV, retained history after deletion, reserved identities, cleared credentials and logout.
  Desktop and 390-pixel mobile layouts had no horizontal overflow or page errors; the browser retained no credentials in local or session storage.
- Review: TechLead approved the actual final implementation, persistence, authorization, usage, documentation and browser behavior.
  The final rejected-save browser regression preserved the disabled boundary arrows, and the rebuilt wheel matched the frozen administration modules and static assets byte for byte; Formater POST approved publication.
- Boundary: Synthetic local verification only; no production deployment, external provider call, billing result, release, Customer acceptance or usability-session outcome is claimed.
  Compose definitions were rendered locally; the full container stack remains a CI check because this environment cannot access the Docker daemon.
  No raw usability material, participant identity, private deployment address or real credential was supplied to the agents for this task.
- Team assessment: TODO

## 2026-11-16 — Task #288 PostgreSQL primary database continuation

- Tool: Codex, with Formater, TechLead and developer agents following the repository roles.
- Request: The repository owner explicitly selected PostgreSQL as the primary administration database, started through Docker Compose, in the existing task and pull request.
- Work: Implemented the PostgreSQL management store with schema validation, transactional updates and exclusive session ownership, private environment-based configuration, a health-checked durable Compose service and explicit SQLite compatibility.
  Added the offline SQLite-to-PostgreSQL CLI migration, preserving the complete snapshot and original reporting epoch without changing the source or overwriting an initialized destination.
- Verification: The final complete suite against real PostgreSQL 17 and SQLite passed 4190 tests with one intentional PostgreSQL-session-only case skipped for the SQLite backend in 93.22 seconds.
  Compilation, Ruff formatting/lint and mypy passed for all 46 production files; the deterministic HTTP demo, locked wheel build and final container image build passed.
- Packaged behavior: An installed-wheel smoke outside the checkout passed the SQLite account lifecycle and the real PostgreSQL CLI migration, exact snapshot/epoch/digest/deleted-history preservation, unchanged source hash, initialized-target refusal, migrated authentication and usage export.
  The real Compose HTTP smoke passed client and credential management, immediate access-policy changes, authoritative database state, gateway and database restarts, persistent usage, filters, CSV and deleted-user history.
  The complete local monitoring Compose smoke, including that PostgreSQL check, passed; its disposable project, containers and volumes were removed.
- Documentation: Strict MkDocs/site validation passed for 75 maintained pages and 10465 links/assets; Markdownlint passed all 132 Markdown files; Lychee passed 442 changed-file link checks with zero errors or exclusions.
  TechLead reviewed and approved the final actual diff, database failure/ownership behavior, migration and architecture diagram; Formater POST approved publication.
- Environment adjustments: Local container builds used a temporary Dockerfile with a BuildKit-secret CA bundle and verified TLS; the monitoring run added internal service names to the session-only Grafana proxy bypass list.
  Public monitoring bind mounts needed local read/traverse permissions because the checkout had restrictive permissions; none of these adjustments changed tracked configuration.
  An existing model-catalog test received a deterministic fake clock after host-uptime floating-point rounding exposed its expiry assertion; the original boundary and stale-fallback assertions remain intact.
- Boundary: No production deployment, external provider call, billing result, release or Customer acceptance is claimed.
  The PostgreSQL and migration checks use synthetic local data; no real credential, participant identity or private deployment address is committed.
- Team assessment: TODO

## 2026-11-16 — Remove unnecessary migration from task #288

- Tool: Codex, with Formater, TechLead and developer agents following the repository roles.
- Request: The owner removed the SQLite-to-PostgreSQL migration scope because it is unnecessary for the intended first launch.
- Work: Removed the migration module, maintenance CLI command, transfer-only snapshot APIs and migration-only tests and guides; retained PostgreSQL primary Compose and the explicit SQLite backend.
  Startup integrity checks, exclusive database ownership, backend selection and credential privacy remain covered; FR-022 retains only its dated Dropped record and historical anchors.
- Verification: The final complete suite against real PostgreSQL 17 and SQLite passed 4184 tests with one intentional PostgreSQL-only case skipped for SQLite in 93.14 seconds.
  Compilation, Ruff formatting/lint and mypy passed for all 45 production files; the deterministic HTTP demo, wheel and final container image builds passed.
  An installed-wheel smoke outside the checkout verified account lifecycle persistence and the absence of the migration module, CLI command, snapshot-transfer APIs and alternate initialization argument.
  The complete monitoring Compose smoke and its integrated PostgreSQL HTTP lifecycle, live enforcement, restart, history and export checks passed on the final image; disposable Compose projects were removed.
  Strict MkDocs/site validation passed for 75 pages and 10458 links/assets; Markdownlint passed 132 files; Lychee passed 390 changed-file link checks without errors or exclusions.
- Review: TechLead approved the final actual diff, including the retained startup validation and backend/privacy regressions; the prior migration verification above remains historical rather than a current capability claim.
- Boundary: No production deployment, external provider call, release or Customer acceptance is claimed; verification used disposable synthetic local services and private test credentials.
- Team assessment: TODO

## 2026-11-16 — Task #295 administration and operations audit closure

- Tool: Codex, with Formater, TechLead and developer agents following the repository roles.
- Work: Implemented the owner-requested five audit corrections and seven administration feature areas in one cohesive pull request: revision conflicts, effective model permissions, complete terminal streaming metrics, dependency readiness/alerts and bounded off-loop database work; budgets/pricing, diagnostics, safe audit, named expiring keys/operators, live provider/model controls, precise UTC usage and bounded private operations.
- Verification: The final complete suite against real PostgreSQL 17 and SQLite passed 4365 tests with one intentional backend-specific skip in 142.41 seconds.
  Compilation, Ruff formatting/lint and whole-package mypy passed for all 53 production files; the deterministic HTTP demo, wheel and final container image passed.
  The wheel matched every frozen Python/console source byte for byte, packaged all external JavaScript modules and excluded the removed migration module.
- Independent cross-domain checks: A separate ASGI harness verified stale-editor conflicts preserve current permissions, viewer writes fail before parsing, hard-budget denials add no provider call and protected projections exclude credentials/content.
  Genuine pre-change installed-v1 SQLite and PostgreSQL fixtures retained profiles, old credentials, suspension/deletion, reserved IDs, original reporting epoch and known/unknown coarse usage under honest UTC-day bounds.
  API-created identities, multiple keys/revocation, operator roles, audit, prices, budgets, usage and encrypted provider configuration survived actual offline CLI backup/restore and fresh application boot on both backends.
  Missing master keys failed closed; the original external key recovered the active provider credential and subsequent calls, while initialized targets were refused and private backups contained no raw tokens, provider/master keys or conversation text.
  The same recovery drill passed from the installed wheel outside the checkout.
- Browser and operations: Real Chromium against PostgreSQL passed all console panels, mutations, stale-tab conflicts, exact Moscow/UTC expiry handling, numeric validation, database no-plaintext checks, logout clearing and mobile layout.
  The complete Compose smoke passed gateway authentication/policies/usage, isolated PostgreSQL lifecycle and restarts/history/export, Prometheus configuration with four alert rules and the Grafana monitoring path.
  Disposable verification projects were removed; session-only CA/proxy and public bind-mount permissions did not change repository TLS settings.
- Documentation and review: Strict MkDocs/site validation passed for 86 maintained pages and 12817 links/assets, Markdownlint passed 143 files, and Lychee passed 534 changed-file link checks without errors or exclusions.
  TechLead approved the final actual diff and Formater POST approved publication; the dependency resolver added only cryptography and its cffi/pycparser dependencies without upgrading existing packages or changing workflow gates.
- Boundary: Estimated costs use configured model prices rather than provider invoices; external telemetry and notification delivery still require private deployment configuration.
  No SSO, HA, simultaneous multiple-provider routing, SQLite-to-PostgreSQL migration, production deployment, billing reconciliation, Customer acceptance or human usability outcome is claimed.
- Team assessment: TODO

## 2026-11-17 — Task #297 plugin authoring

- Tool: Codex, with Formater, TechLead and developer agents following the repository roles, plus a separate agent given only a generated project and its installed Gateway7 environment.
- Work: Implemented the typed text-policy helper, reference-policy parity and native denial diagnostics; replaced the authoring workflow with project discovery, fixture schema 2, profile-aware execution, safe diagnostics, inspection and a disposable synthetic HTTP development service.
  Added guard/redactor projects with bundled agent instructions and version-matched public-contract guidance, progressive guides and installed-package verification.
- Compatibility: The owner authorized replacing older authoring flags and fixtures; raw middleware API 2 and transport API 1 remain supported independently.
  The package and generated minimum use the unreleased development version `0.5.0.dev0`; no release or tag was published.
- Independent agent trial: From the generated local instructions and installed public API, an agent added the synthetic rule `SYNTHETIC-AGENT-TRIAL`, observed failing fixtures, then passed 18 cases across all five profiles and two generated unit tests.
  Actual local HTTP returned 200 for a benign request and 403 for the new rule; no gateway checkout or core implementation was supplied to that agent.
  A separate real controlling-terminal test verifies Ctrl-C cleanup; the agent trial's terminal-wrapper termination behavior alone is not claimed as that proof.
- Automated verification: The complete regression suite passed 4197 tests with 67 skips under the local test configuration and one Python PTY warning in 107.87 seconds.
  The final template quality-tool correction separately passed 80 scaffold, version and secrets tests; fresh generated projects passed Ruff formatting/lint and strict mypy.
  Compilation, Ruff formatting and lint and mypy passed for all 50 production files; the deterministic HTTP demo passed.
- Packaging and operations: A fresh installed wheel outside the checkout passed both preset journeys, deliberate red/green changes, profile checks, generated unit tests, source-based development HTTP, normal installed-plugin HTTP with project source hidden and owned-process cleanup.
  The complete Compose smoke passed the gateway, PostgreSQL administration restart/history checks, Prometheus and Grafana; its disposable containers and volumes were removed.
  The local image build used the managed environment's CA through a temporary BuildKit-secret mount with TLS verification enabled; tracked trust settings were unchanged.
- Documentation and review: Strict MkDocs/site validation passed for 80 maintained pages and 11518 links/assets; Markdownlint passed all 137 Markdown files, changed-file link checks passed without errors, and actionlint passed the workflows.
  TechLead approved the actual code, profile oracle, confidentiality boundaries, packaged guidance and platform-verification design.
- Boundary: Verification uses synthetic local services and trusted Python plugins with accidental-network/process protection; the worker is not an operating-system sandbox for hostile code.
  No live provider call, production deployment, human usability study, Customer acceptance or course-completion result is claimed.
- Team assessment: TODO

## 2026-11-17 — PR #298 review corrections

- Tool: Codex, with Formater, TechLead and developer agents following the repository roles.
- Request and work: Fixed all seven confirmed review findings in the existing pull request: unsafe import-exception diagnostics, stale project bytecode, inconsistent native early-response heads, JSON tuple-field validation, named/required synthetic function selection, malformed-project JSON errors and normalized generated wheel-install filenames.
  Added deterministic regressions for each finding, including same-size/same-timestamp cache files, custom native identities and tool metadata, actual public HTTP tool choices and real builds/installations for repeated underscores.
- Verification: The complete final regression suite passed 4261 tests with 67 skips under the local test configuration and one existing PTY warning in 141.07 seconds.
  Compilation, Ruff formatting/lint and mypy passed for 51 production files; the deterministic HTTP demo, wheel and container image builds passed.
- Packaged checks: A fresh installed wheel outside the checkout passed both full authoring journeys with real Ruff/strict mypy, red/green fixtures, profile checks, current-source development HTTP, ordinary installed-plugin HTTP and owned-listener cleanup.
  Additional installed-only probes passed custom native early heads with JSON-array metadata, safe import-failure JSON and malformed-TOML JSON; all 55 packaged source/assets matched the final checkout, including the new scoped source loader.
- Operations and documentation: The complete monitoring/PostgreSQL Compose smoke and Prometheus configuration check passed; strict documentation validation passed for 80 pages and 11518 links/assets, and Markdownlint and actionlint passed.
  Managed-container verification used only a temporary CA-secret build mount and an internal-service proxy bypass; repository trust settings were unchanged.
- Review boundary: TechLead independently replayed the seven original probes against the corrected implementation.
  Plugins remain trusted code; no hostile-code sandbox, real provider call, deployment, release, human usability result or course-completion result is claimed.
- Team assessment: TODO

## 2026-11-17 — Resolve PR #298 conflicts with current main

- Tool: Codex, with Formater, TechLead and developer agents following the repository roles.
- Work: Merged current main `e2e13968a5dce9f11b99c4e3337166e5285dbf18`, containing administration PR #296, into the existing plugin-authoring branch through a normal merge.
  Resolved six documentation/evidence conflicts by preserving both histories, guide sets, navigation, ADRs and functional requirements; retained backup/restore and plugin commands, asynchronous accounting and native denial attribution together.
  The resolver reproduced the combined dependency lock unchanged, retaining cryptography and the development package version `0.5.0.dev0` without unrelated upgrades.
- Verification: The combined regression run had 4363 passing tests, 145 skips and one pre-existing wall-clock-sensitive native timeout fixture.
  Its test-only correction uses a pipeline-local controlled clock while retaining the original timeout, phase and exact provider-call assertions; all 226 tests in the affected native pipeline file passed.
  Compilation, Ruff formatting/lint and mypy passed for all 59 production files; the deterministic HTTP demo and final wheel/container builds passed.
- Installed package: A fresh environment outside the checkout passed both complete authoring journeys and the private offline backup/restore drill, including encrypted provider recovery, identities and pending accounting state.
  The backup tests passed two SQLite cases and skipped the optional PostgreSQL unit case; real PostgreSQL HTTP lifecycle checks are exercised by the Compose smoke.
  All 68 packaged source/assets matched the merged checkout, including public typing, external console modules, backup and fresh-source loading.
  Gateway, real PostgreSQL lifecycle and Prometheus checks passed locally; Grafana verification was interrupted by executor disk exhaustion, so final complete monitoring verification is left to the clean CI runner.
  Only this task's disposable containers/volumes and completed temporary environments were removed to recover space; repository tools, source and final package evidence were preserved.
- Review and documentation: TechLead approved the resolved documentation and semantic combination; runtime independently passed 86 focused cross-domain tests.
  Strict site validation passed for 91 maintained pages and 13987 links/assets; Markdownlint passed 148 files and actionlint passed.
- Boundary: This updates the existing pull request branch; it does not merge the pull request into main, publish a release, deploy the product or claim Customer acceptance.
  Both historical AI-usage entries and their TODO assessments remain preserved; the team's assessment of this merge is also pending.
- Team assessment: TODO

## 2026-11-18 — Task #308 correctness corrections

- Tool: Codex, with Formater, TechLead and developer agents following the repository roles.
- Work: Fixed the three accepted audit defects: early Chat keeps its selected model across live provider changes, cancelled admission releases only its unused durable reservation, and named operator self-rotation preserves the one-time replacement and current session.
  The frontend handoff also handles an old read returning 401 after the rotation commits but before its response arrives; failed rotation, external revocation and deliberate session changes retain their normal effect.
- Backend verification: The full regression run against SQLite and a dedicated task-created PostgreSQL Compose fixture passed 4537 tests with two skips and one existing PTY warning in 187.72 seconds.
  PostgreSQL used only loopback access, labelled task containers, independent test databases and tmpfs storage; no external database was touched.
  A normally installed wheel outside the checkout passed 25 additional model/cancellation regressions on both backends, including conservative accounting after an actual provider attempt.
- Browser verification: The original self-rotation and pre-response unauthorized-read failures were reproduced against the old behavior.
  The final four actual Chromium cases passed, covering delayed unauthorized reads before and after the handoff, duplicate submission, failed/revoked rotation, deliberate disconnect/new login, token visibility/copying and subsequent protected requests.
  TechLead independently repeated the browser and backend reproductions; credentials remain in memory and are cleared on logout.
  Browser execution was local; the committed browser regression is optional without Playwright/Chromium, and mandatory browser CI remains separate follow-up work.
- Package and documentation checks: Compilation, Ruff formatting/lint and mypy passed for 59 production files; the deterministic HTTP demo, wheel build, final JavaScript syntax checks and packaged-source equality passed.
  Strict documentation validation passed for 91 pages and 13987 links/assets; the three fixes were added only under the Unreleased changelog section.
  The final frontend-only guard and browser-test delta was verified by its browser cases and rebuilt assets; backend code was unchanged after the full regression run.
- Review and boundary: TechLead approved the final frozen diff.
  No public API, package version, dependency lock, workflow, release or deployment changed; no live provider call, human usability result or Customer acceptance is claimed.
- Team assessment: TODO
