# Configuration plan

**Reviewed:** 2026-11-18.

This inventory describes the configuration that controls Gateway7's sources, checks, build, deployment and maintained evidence.
It implements the [configuration management requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/configuration-management-requirements.md) for [task #302](https://github.com/iteam7/gateway7/issues/302).
Owners below are maintenance roles, not newly appointed people: the task's Responsible member prepares an update and its different Accountable member verifies it under [CONTRIBUTING](https://github.com/iteam7/gateway7/blob/main/CONTRIBUTING.md#project-views-and-scheduling).
The deployment operator maintains private runtime settings; TechLead owns architecture and agent task boundaries, and Formater owns Git workflow checks under [AGENTS](https://github.com/iteam7/gateway7/blob/main/AGENTS.md#roles).
The inventory is a repository review, not a deployment verdict, a new sprint commitment or completion of [planning task #299](https://github.com/iteam7/gateway7/issues/299).

## How to maintain the inventory

Give each item one stable CFG-nn heading and retain its identifier when its location changes.
Use Active for a maintained item; if a real item is removed, retain its section as Dropped with the removal date and reason rather than reusing its identifier.
No removed configuration item was established in this review, so none is invented as an example.
A file family is recorded through its directory or index, not a separate item for every instance.
Configuration evaluation judges how convenient the artifact set is for an explicit local goal; mandatory course conformance remains a fixed constraint, not a preference to debate.
A configuration review inspects items, connections and fitness for their purposes, including mandatory checks and a goal-based evaluation; it records the inspected commit and inaccessible settings rather than assuming passing CI or live settings.
Apply [the course rule](https://github.com/inno-itpd/itpd/blob/main/requirements/configuration-management-requirements.md) when reviewing each item's connections and baseline.

Update the affected item, its connections and the linked glossary or risks in the same pull request as a configuration change.
For private settings, update the public shape/runbook and record the actual value and verification privately; never copy secrets into the inventory.
Use a frozen, identified reviewed commit/tag state and its lockfiles as a baseline; a release baseline also identifies the actual tag and deployment evidence.
A reproducible build needs the same source, resolved dependencies, tools and relevant environment, not merely a matching version string.
See [RISK-09](risks.md#risk-09), [RISK-10](risks.md#risk-10), [RISK-11](risks.md#risk-11) and [RISK-12](risks.md#risk-12) for failure responses.

## Source control and release

### CFG-01

Repository workflow and tracker configuration

- **Status:** Active
- **Type:** GitHub settings and tracked issue/PR templates.
- **Purpose:** Keep changes traceable to one task and reviewer; without consistent workflow settings, unrelated work or unreviewed changes can reach main.
- **Owner:** Formater checks workflow; task Responsible and Accountable members maintain their tracker fields; repository administrator maintains protected settings.
- **Where:** Repository branch/tag protection and Pages settings (administrator interface; not publicly linked), [project](https://github.com/orgs/iteam7/projects/1), [issue forms](https://github.com/iteam7/gateway7/tree/main/.github/ISSUE_TEMPLATE), [PR template](https://github.com/iteam7/gateway7/blob/main/.github/pull_request_template.md) and [contributor workflow](https://github.com/iteam7/gateway7/blob/main/CONTRIBUTING.md#from-a-task-to-a-merged-change).
- **Connections:** `enforces` the independent review and green checks in [CFG-02](#cfg-02); bypassed protection can admit a change without those checks.
  `reads` the completion rules in [CFG-12](#cfg-12); changing an issue form without those rules can make tasks omit observable acceptance criteria.
- **What good looks like:** One task per PR with one closing line, separate author/reviewer, all AC boxes verified, scheduled role fields consistent and no direct main changes, under the [repository requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/repository-requirements.md).
  Actual branch rules, required checks, tag protection and live project settings were not inspected in this repository-file review; their enforcement is unverified, not assumed absent or passing.

### CFG-03

Release and package version baseline

- **Status:** Active
- **Type:** Version metadata and release procedure.
- **Purpose:** Connect an installed version to reviewed release source; without aligned metadata and release procedure, a version string cannot identify the evaluated increment.
- **Owner:** Release preparer and independent verifier, assigned through the release task; Formater checks Git actions.
- **Where:** [pyproject.toml](https://github.com/iteam7/gateway7/blob/main/pyproject.toml), [runtime version](https://github.com/iteam7/gateway7/blob/main/gateway7/__init__.py), [changelog](https://github.com/iteam7/gateway7/blob/main/CHANGELOG.md), [version test](https://github.com/iteam7/gateway7/blob/main/tests/test_release_version.py) and [release handoff](https://github.com/iteam7/gateway7/blob/main/CONTRIBUTING.md#release-and-submission-handoff).
- **Connections:** `reads` [CFG-08](#cfg-08) to regenerate the root package lock entry after a version bump; mismatched project/runtime/distribution versions make the baseline ambiguous.
  `cites` [CFG-12](#cfg-12) review evidence before publishing; a tag alone proves neither Customer acceptance nor deployment.
  `produces` the source baseline for [CFG-06](#cfg-06); a checkout hash without an image check does not identify running code.
- **What good looks like:** Project and runtime versions match, the wheel test agrees, reviewed release prerequisites precede publication, and a protected immutable tag names a commit on main.
  Follow [planning and release requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/planning-requirements.md); live tag protection remains unverified in this review.

## Checks

### CFG-02

Continuous integration workflows

- **Status:** Active
- **Type:** GitHub Actions workflow family.
- **Purpose:** Reject broken changes before publication; without the workflows, a PR can ship invalid Python, Compose, prose or site output without an automated gate.
- **Owner:** Task Responsible member updates a workflow in its own PR; Accountable member reviews the gate.
- **Where:** [Workflow directory](https://github.com/iteam7/gateway7/tree/main/.github/workflows); entrypoints are python.yml, quality-requirements.yml, actionlint.yml, markdown.yml, lychee.yml and docs.yml.
- **Connections:** `reads` [CFG-04](#cfg-04), [CFG-05](#cfg-05), [CFG-08](#cfg-08) and [CFG-09](#cfg-09) for actual check/build settings; a stale command or tool version can invalidate their results.
  `produces` the successful runs required by [CFG-01](#cfg-01) and the main-only Pages publication in [CFG-05](#cfg-05); changing triggers can leave either route unchecked.
- **What good looks like:** PR and main checks exercise the locked Python stack, quality scenarios, Compose, workflows and docs; action references use full commit SHAs with version comments, and only the successful main docs job publishes.
  Keep the named gates and permissions aligned with [CI requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/repository-requirements.md#continuous-integration); a file review does not assert that the latest run passed.

### CFG-04

Python and repository check settings

- **Status:** Active
- **Type:** Static analysis, test and Markdown/link-check configuration.
- **Purpose:** Give local and CI checks the same scope; without explicit discovery, lint and link rules, a green result may omit relevant gateway files or broken evidence links.
- **Owner:** Task Responsible member for the affected check, verified by Accountable; TechLead reviews code-related changes.
- **Where:** [pyproject.toml tool sections](https://github.com/iteam7/gateway7/blob/main/pyproject.toml), [Markdown settings](https://github.com/iteam7/gateway7/blob/main/.markdownlint-cli2.jsonc), [link exclusions](https://github.com/iteam7/gateway7/blob/main/.lycheeignore) and [check commands](https://github.com/iteam7/gateway7/blob/main/AGENTS.md#checks).
- **Connections:** `cites` [CFG-02](#cfg-02) as its CI consumer; changing pytest discovery or lint scope can leave an advertised gate checking fewer files.
  `reads` dependencies from [CFG-08](#cfg-08); divergent tool resolutions can produce different results on the same code.
  `enforces` the Markdown produced under [CFG-12](#cfg-12); an unjustified exclusion can hide a broken evidence link.
- **What good looks like:** Python 3.11+ code is formatted at line length 100, Ruff E4/E7/E9/F checks and mypy checks are enabled, pytest discovers tests/, and Markdown/link checks retain justified private-link exclusions only.
  Use [CI requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/repository-requirements.md#continuous-integration) and [repository requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/repository-requirements.md) when changing these gates.

### CFG-05

Documentation publication and site checks

- **Status:** Active
- **Type:** MkDocs navigation, rendering hooks and generated-site validation.
- **Purpose:** Publish maintained docs with local assets; without navigation and site checks, a new guide can be unreachable or weekly evidence can leak into the published site.
- **Owner:** Documentation task Responsible member, independently verified by Accountable.
- **Where:** [mkdocs.yml](https://github.com/iteam7/gateway7/blob/main/mkdocs.yml), [docs index](README.md), [build support index](https://github.com/iteam7/gateway7/tree/main/docs-build) and [build instructions](https://github.com/iteam7/gateway7/blob/main/CONTRIBUTING.md#build-and-preview-the-site).
- **Connections:** `reads` locked tools/assets from [CFG-09](#cfg-09) ; missing Mermaid installation fails the build hook.
  `cites` [CFG-02](#cfg-02) as the CI trigger; a changed workflow path can stop publication.
  `produces` the published form of the maintained artifacts governed by [CFG-12](#cfg-12); missing nav entries, wrong relative external-doc links or missing anchors fail strict/site validation.
- **What good looks like:** Strict MkDocs build and check_site.py pass, every new docs page is in nav and the index, the hook bundles local Mermaid and strips report citation links from rendered pages.
  Main-only Pages publication follows the [repository documentation rules](https://github.com/inno-itpd/itpd/blob/main/requirements/repository-requirements.md); actual Pages source and environment policies remain unverified in this file review.

## Environments and secrets

### CFG-06

Gateway build and deployment modes

- **Status:** Active
- **Type:** Container build, Compose overlays, sample runtime YAML and promotion procedure.
- **Purpose:** Keep demo, live and managed-account modes explicit; without overlays and promotion rules, an operator can run the wrong provider or promote an image that never passed staging.
- **Owner:** Deployment operator maintains environment selection; task Responsible/Accountable members maintain tracked definitions.
- **Where:** [Dockerfile](https://github.com/iteam7/gateway7/blob/main/Dockerfile), [Compose family](https://github.com/iteam7/gateway7/tree/main) (compose.yaml, compose.live.yaml, compose.admin.yaml, compose.admin-sqlite.yaml and compose.telemetry-client.yaml), [sample configuration index](https://github.com/iteam7/gateway7/tree/main/config), [setup](setup.md), [operator onboarding](admin-controls.md#first-sign-in), [session policy](authentication.md#password-sessions-and-https), [operator-created HTTPS override](authentication.md#run-the-managed-console-over-local-https) and [deployment runbook](deployment.md).
- **Connections:** `reads` the locked runtime in [CFG-08](#cfg-08) and environment/credential contract in [CFG-07](#cfg-07); the wrong overlay or unset required variable selects the wrong mode or prevents startup.
  `reads` [CFG-12](#cfg-12)'s maintained session/policy instructions; stale cookie defaults can prevent sign-in, while omitted activation ordering can misstate which configured policies remain mandatory.
  `reads` [CFG-10](#cfg-10)'s monitoring/backend networks; wrong network names prevent signal delivery while local health may still pass.
  `reads` [CFG-03](#cfg-03)'s reviewed commit; a checkout hash without running-image verification can misidentify the deployed version.
- **What good looks like:** Default services bind loopback, the gateway runs as UID/GID 10001, provider keys stay server-side and staging/production use separate projects, ports, state and secrets.
  The optional HTTPS console override reuses the pinned telemetry nginx image with a private certificate directory and requires proxy restart after a gateway namespace change.
  Shared password sessions retain Secure cookies and HTTPS; the insecure development exception is confined to a direct loopback host and peer.
  Managed policy settings are durable validated data and do not authorize arbitrary plugin imports.
  Verify the running image revision and staging QRTs before promotion under [deployment requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/repository-requirements.md#environments-and-deployment).
  Private deployment values and actual currently running revisions were not inspected; tracked definitions are not live readiness evidence.

### CFG-07

Secret contract and private-value exclusions

- **Status:** Active
- **Type:** Public environment-variable template, ignore rules and confidentiality check.
- **Purpose:** Describe credential names without values; without this contract and exclusions, operators can miss a required value or contributors can publish a real secret.
  The optional `GATEWAY7_DRAFT_OLLAMA_MODEL` selects a credential-free local model for [editable policy suggestions](admin-controls.md#generate-an-editable-policy-or-test-cases).
- **Owner:** Deployment operator supplies and rotates private values; task Responsible/Accountable members check the public shape.
- **Where:** [.env.example](https://github.com/iteam7/gateway7/blob/main/.env.example), [.gitignore](https://github.com/iteam7/gateway7/blob/main/.gitignore), [confidentiality checker](https://github.com/iteam7/gateway7/blob/main/scripts/check_confidentiality.py) and [secret runbook](deployment.md#configuration-and-secrets) and [operator credential/session contract](operator-identities.md#named-operators-and-recovery).
- **Connections:** `produces` the variable-name contract for [CFG-06](#cfg-06) and [CFG-10](#cfg-10); a renamed variable without overlay/runbook updates can stop startup or export to the wrong scope.
  `enforces` privacy boundaries for [CFG-11](#cfg-11) and [CFG-12](#cfg-12); putting private inputs in prompts, logs or evidence can leak them even when .env is ignored.
- **What good looks like:** Only names and empty placeholders are tracked, real secrets and private databases stay outside Git, ingestion credentials are environment-specific, and secret-bearing output is reviewed before publication.
  Operator passwords, opaque session cookies and CSRF proofs are private credentials; bootstrap/automation bearers remain separate from normal password sign-in.
  Logical backups retain password hashes and managed policy data but exclude authenticated browser sessions.
  Ignore rules are not access controls or proof that history is clean; follow [repository privacy rules](https://github.com/inno-itpd/itpd/blob/main/requirements/repository-requirements.md) and [RISK-09](risks.md#risk-09).

### CFG-10

Monitoring, telemetry and dashboard configuration

An optional top-level `grafana_url` links the operator overview to a configured HTTP(S) dashboard path without query parameters or credentials.

- **Status:** Active
- **Type:** Prometheus/Grafana provisioning, backend Compose, TLS proxy shape and dashboard/query definitions.
- **Purpose:** Observe outcomes and segregate synthetic traffic; without matching scrape/query/filter configuration, failures can go unseen and product metrics can count test events.
- **Owner:** Deployment operator maintains private backend settings; analytics/observability task Responsible member maintains public queries, verified by Accountable.
- **Where:** [Monitoring index](https://github.com/iteam7/gateway7/tree/main/monitoring), [backend Compose](https://github.com/iteam7/gateway7/blob/main/compose.telemetry.yaml), [analytics plan](analytics.md), [observability plan](observability.md) and [telemetry runbook](deployment.md#telemetry-pipelines).
- **Connections:** `reads` the mounts and network selections in [CFG-06](#cfg-06); incorrect selections stop scraping or backend delivery.
  `reads` credential-variable names from [CFG-07](#cfg-07); mismatched names prevent ingestion.
  `produces` signal/query evidence for [CFG-12](#cfg-12); a stale saved query can misstate the result.
  A changed metric name without dashboard/alert/query updates breaks diagnosis; mismatched source filters can count synthetic traffic as product value.
- **What good looks like:** Prometheus scrapes the gateway at five-second intervals, Grafana reads its provisioned datasource/dashboard, alerts match exported metric names, and each backend scope has separate credentials and correct seven-day queries.
  The TLS proxy uses external backend networks and private certificate material; only its public shape is inventoried.
  Follow [observability requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/observability-requirements.md) and [analytics requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/analytics-requirements.md); actual dashboard state, retention and deployed digests are not established by these templates.

## Dependencies and builds

### CFG-08

Python dependency and packaging baseline

- **Status:** Active
- **Type:** Package manifest, uv resolution lock and container toolchain.
- **Purpose:** Resolve runtime/dev dependencies consistently; without the lock and package metadata, identical source can resolve different packages or produce an unusable wheel.
- **Owner:** Dependency-update task Responsible member and Accountable verifier; TechLead reviews compatibility impact.
- **Where:** [pyproject.toml](https://github.com/iteam7/gateway7/blob/main/pyproject.toml), [uv.lock](https://github.com/iteam7/gateway7/blob/main/uv.lock), [Dockerfile](https://github.com/iteam7/gateway7/blob/main/Dockerfile) and [version/dependency commands](https://github.com/iteam7/gateway7/blob/main/CONTRIBUTING.md#prepare-a-package-version).
- **Connections:** `produces` resolved packages for [CFG-02](#cfg-02) checks and [CFG-06](#cfg-06) images; unlocked installation can test a different dependency graph from the deployed gateway.
  `reads` package metadata maintained by [CFG-03](#cfg-03); mismatched versions can break installed-wheel verification.
  `cites` the update-proposal source [CFG-13](#cfg-13); an unchecked lock refresh can change compatibility beyond the intended version bump.
- **What good looks like:** uv sync/run use --locked, the lock is regenerated by uv rather than edited, declared Python support remains >=3.11,<3.14, and the isolated installed-wheel smoke succeeds.
  CI pins uv 0.12.23; Docker pins Python 3.12.14 and uv 0.12.23 by version, while their base tags remain mutable unless digest-pinned.
  Follow [CI requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/repository-requirements.md#continuous-integration) and [RISK-11](risks.md#risk-11); a lock alone does not freeze OS packages, image tags or external provider behavior.

### CFG-09

Documentation dependency baseline

- **Status:** Active
- **Type:** Hash-locked Python tools and npm-locked browser assets.
- **Purpose:** Fix documentation tools and local browser assets; without these locks, a tool update can change rendering or remove required diagrams from the same source.
- **Owner:** Documentation dependency task Responsible member, verified by Accountable.
- **Where:** [requirements-docs.in](https://github.com/iteam7/gateway7/blob/main/requirements-docs.in), [requirements-docs.txt](https://github.com/iteam7/gateway7/blob/main/requirements-docs.txt), [docs-build package manifest/lock index](https://github.com/iteam7/gateway7/tree/main/docs-build) and [regeneration procedure](https://github.com/iteam7/gateway7/blob/main/CONTRIBUTING.md#update-documentation-dependencies).
- **Connections:** `cites` [CFG-05](#cfg-05) as its rendering consumer and [CFG-02](#cfg-02) as its installer; a changed MkDocs version without a regenerated hash lock fails sync, while a missing npm lock makes asset resolution unstable.
  `cites` [CFG-13](#cfg-13) as its dependency-proposal source; Mermaid changes require an actual rendered diagram review as well as build validation.
- **What good looks like:** MkDocs 1.6.1 and its dependencies install with --require-hashes in an isolated docs environment; npm ci installs Mermaid 12.3.0 from the lock and the local bundle is published by the hook.
  Use Python 3.12.14/Node 24.19.0 as pinned in the docs workflow, regenerate locks through the documented commands, and keep runtime/docs dependency scopes separate under [CI requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/repository-requirements.md#continuous-integration).

### CFG-13

Dependency update automation

- **Status:** Active
- **Type:** Dependabot schedule.
- **Purpose:** Surface stale pins for review; without the schedule and ecosystem paths, security and compatibility updates can remain undiscovered.
- **Owner:** Dependency-update task Responsible member and independent Accountable reviewer; repository administrator maintains app permissions.
- **Where:** [Dependabot configuration](https://github.com/iteam7/gateway7/blob/main/.github/dependabot.yml).
- **Connections:** `triggers` update proposals for [CFG-02](#cfg-02)'s actions, [CFG-08](#cfg-08)'s uv and [CFG-09](#cfg-09)'s pip/npm dependencies; missing ecosystem/directory coverage leaves a baseline without automated proposals.
  `triggers` [CFG-02](#cfg-02) checks through update PRs; automerging a failing update would invalidate the assumed baseline.
- **What good looks like:** Weekly github-actions, uv, root pip and /docs-build npm update checks retain manifest/lock consistency and action SHA/version comments.
  Actual Dependabot run state, alerts and app permissions were not inspected; container image tags and external backend configuration need separate operator review rather than an assumed update service.
  Follow [configuration requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/configuration-management-requirements.md) and the contingency in [RISK-11](risks.md#risk-11).

## Agent context and artifacts

### CFG-11

Agent instruction and delegation context

- **Status:** Active
- **Type:** Repository-wide instructions and role instruction family.
- **Purpose:** Make AI follow the artifact layout and role boundaries; without these instructions, an agent can edit historical evidence, invent decisions or skip the required checks.
- **Owner:** TechLead owns role/task boundaries; Formater checks workflow; the instruction task's Accountable member verifies changes.
- **Where:** [AGENTS.md](https://github.com/iteam7/gateway7/blob/main/AGENTS.md), [role definitions index](https://github.com/iteam7/gateway7/tree/main/.claude/agents) and [CONTRIBUTING](https://github.com/iteam7/gateway7/blob/main/CONTRIBUTING.md).
- **Connections:** `enforces` [CFG-01](#cfg-01)'s Git rules; stale instructions can bypass the intended review route.
  `reads` [CFG-04](#cfg-04)'s check commands; stale commands can skip the relevant check.
  `enforces` [CFG-12](#cfg-12)'s artifact placement; a wrong path can publish private evidence or hide maintained docs.
  Contradictory or stale agent instructions can skip verification, edit historical evidence or invent a decision even when the product builds.
  Its upkeep rule points to this inventory so a changed configuration cannot silently leave another item's description stale.
- **What good looks like:** Agents read current course rules for covered work, use the assigned role boundaries, preserve human edits, record AI use with team assessment TODO and perform the relevant checks.
  Keep instruction context concise enough to read, but do not assume a model's finite context window retains earlier approvals or complete evidence after handoff.
  Apply [AI usage requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/weekly-report-requirements.md#ai-usage-report); no particular external user-level instruction or private agent settings were inspected.

### CFG-12

Maintained artifact and weekly evidence process

- **Status:** Active
- **Type:** Documentation layout, completion rules and report-production convention.
- **Purpose:** Separate maintained requirements from dated evidence; without the layout and completion rules, a report can duplicate stale tracker state or present a task merge as Customer acceptance.
- **Owner:** Artifact task Responsible member and Accountable verifier; TechLead owns architecture, while actual team/Customer decisions require their real source.
- **Where:** [docs index](README.md), [Definition of Done](definition-of-done.md), [reports index](https://github.com/iteam7/gateway7/tree/main/reports), [task/PR templates](https://github.com/iteam7/gateway7/tree/main/.github) and [artifact rules](https://github.com/iteam7/gateway7/blob/main/AGENTS.md#do-not-edit).
- **Connections:** `produces` maintained pages for [CFG-05](#cfg-05); a misplaced page can be omitted from the site.
  `cites` [CFG-03](#cfg-03)'s real release baseline and [CFG-02](#cfg-02)'s check results; an unsupported citation can falsely imply completed acceptance.
  `cites` [CFG-06](#cfg-06) through the operator onboarding and session/policy guides; instructions that conflate application clients with operator accounts can grant the wrong type of access.
  A broken evidence link or an unsupported pass verdict severs traceability even if the linked code is correct.
  `reads` the constraints in [CFG-07](#cfg-07) privacy rules and [CFG-11](#cfg-11)'s AI-use disclosure; omission can expose private inputs or omit required disclosure.
- **What good looks like:** docs/ is the maintained source; reports/week-NN/ contains dated evidence and AI disclosure with no invented assessment.
  A weekly report file is an instance produced by this process, not a separate configuration item; finished-week corrections go into the current week.
  Follow [report requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/weekly-report-requirements.md#weekly-public-report) and [repository requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/repository-requirements.md), preserve stable identifiers and cite real Customer decisions only.

### CFG-14

Upstream course requirements skill

- **Status:** Active
- **Type:** Skill and its repository-local routing instruction.
- **Purpose:** Route an agent to the current course rule for each artifact; without the upstream skill and local read instruction, cached assumptions can make a structurally valid PR violate current course requirements.
- **Owner:** Course maintainers own the upstream skill; the Gateway7 instruction task Responsible/Accountable members maintain local integration, with TechLead checking role boundaries.
- **Where:** [Course SKILL.md](https://github.com/inno-itpd/itpd/blob/main/SKILL.md) and the opening course-rule routing instruction in [AGENTS.md](https://github.com/iteam7/gateway7/blob/main/AGENTS.md).
- **Connections:** `produces` routed requirement references for [CFG-12](#cfg-12)'s artifact process; a stale router copy can cite the wrong artifact rules.
  `enforces` current-rule reading through [CFG-11](#cfg-11)'s repository instruction; losing that integration can make agent work rely on memory.
- **What good looks like:** Agents consult the current upstream skill and the routed rule/assignment before covered work, without copying an unmaintained local ruleset or modifying upstream course files.
  The integration follows [agent instruction requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/agent-instructions-requirements.md#what-it-states) and [course materials as a skill](https://github.com/inno-itpd/itpd/blob/main/requirements/repository-requirements.md#the-course-materials-as-an-agent-skill).

## Review limits and unintroduced configuration

The tracked sources and procedures linked above were inspected; running CI, branch/tag protection, actual Pages settings, private deployment values and live backend/dashboard configuration need their own authenticated verification.
Do not infer a pass or fail for those settings from this inventory.
No separate .editorconfig, pre-commit hook configuration or standalone coverage policy was found in the reviewed tracked sources; these absent controls have no CFG identifier.
The local .agents-log.md is an ignored workflow output under CFG-11, not public weekly evidence.
An operator's private Compose overrides and backend digests remain private instances of CFG-06/CFG-10 and must be checked against the current runbook when evaluating a deployed baseline.
