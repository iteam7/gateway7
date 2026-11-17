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
