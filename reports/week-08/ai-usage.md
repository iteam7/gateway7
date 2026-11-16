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
