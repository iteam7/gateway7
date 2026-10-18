# Week 03 report — Gateway7, Team 7

**Status:** In progress; architecture, a runnable Python demonstration and the documentation workflow are prepared for review. The complete MUP, customer verdicts, delivery to `main`, live documentation site and release remain pending.

## Summary

Prepared the [architecture](../../docs/architecture/README.md) for [task #50](https://github.com/iteam7/gateway7/issues/50): component responsibilities, a [customer view](../../docs/architecture/README.md#customer-view), contracts and first-version limits.
The concise [request lifecycle](../../docs/architecture/README.md#request-lifecycle) retains independent hook chains, fail-closed errors, usage and cancellation boundaries.
Built the first Python slice under [task #52](https://github.com/iteam7/gateway7/issues/52), following the contributor's language selection in [DEC-013](../../docs/decisions.md#dec-013).
It runs the gateway and fake provider as separate HTTP processes, imports company plugins by configuration and restart, masks the exact synthetic phone fixtures and demonstrates independent request/response order.
[Setup](../../docs/setup.md), the [customer demo](../../docs/demo.md) and the [meeting script](meeting-script.md) prepare the planned 16 October call.
The actual Claude/Gemini call, complete working MUP, customer validation and release are not evidenced by the deterministic demonstration.
`REL-03` and its tag have not been evidenced here; no candidate story is moved out by this update.
Prepared the requested Assignment 3 items 6, 7, 14 and 15 under [task #54](https://github.com/iteam7/gateway7/issues/54); documentation publication and its live README link remain pending as detailed below.

## Coverage

Pending rows describe unfinished Assignment 3 work, not completed deliverables.
Missing files and unverified external artifacts are not linked as though they exist.

| Deliverable | Artifact or current status |
| --- | --- |
| Architecture preparation | [docs/architecture/README.md](../../docs/architecture/README.md), aligned with the Python prototype; Customer evaluation pending |
| Threshold of success | Pending: `docs/threshold-of-success.md` and the product-vision link |
| Project plan | Pending: `docs/project-plan.md`, including SPRINT-03–09 and release sections |
| Risk register | Pending: `docs/risks.md` |
| Stack decision | [DEC-013](../../docs/decisions.md#dec-013), Python manifest and `uv.lock`, Python ignore entries and Dependabot's `uv` ecosystem |
| Definition of Done | [docs/definition-of-done.md](../../docs/definition-of-done.md), prepared for review with separate Story, Task and Pull Request standards |
| Contributing guide | [CONTRIBUTING.md](../../CONTRIBUTING.md), including commit/branch/PR rules, review procedure and docs setup; public project/table view pending verification |
| Sprint milestones and issue fields | Pending evidence for SPRINT-03 scheduling, Responsible/Accountable values and matching assignees; task #50/#52/#54 metadata remains unresolved |
| GitHub project | Public project and required table view not verified in this contribution |
| Minimum usable product | [US-01](https://github.com/iteam7/gateway7/issues/30), [US-02](https://github.com/iteam7/gateway7/issues/31), [US-03](https://github.com/iteam7/gateway7/issues/32): deterministic implementation/checks prepared; real-provider AC-05, human review, merge and Customer verdicts pending |
| Changelog and first release | [CHANGELOG.md](../../CHANGELOG.md) records Unreleased changes; tagged release and REL-03 evidence pending |
| Documentation site | [docs/README.md](../../docs/README.md) and [.github/workflows/docs.yml](../../.github/workflows/docs.yml): site/build prepared; Pages activation, public deployment and live URL verification pending |
| Setup and run instructions | [docs/setup.md](../../docs/setup.md) and [README.md](../../README.md): setup/run link, locked dependencies and HTTP demo present; README's live site hyperlink pending deployment |
| Week 2 action points | Architecture and runnable prototype prepared for the two presentation commitments in [reports/week-02/meeting-report.md#action-points](../week-02/meeting-report.md#action-points); presentation and infrastructure outcomes still belong in the later meeting report |
| Week 2 open questions | Python answered by DEC-013; the [architecture review questions](../../docs/architecture/README.md#review-questions-and-week-2-follow-up) carry forward capacity, secret source and contract validation; meeting outcomes pending |
| Meeting script | [reports/week-03/meeting-script.md](meeting-script.md), prepared for 16 October; facilitation roles remain TODO |
| Customer validation | Week 3 meeting report, story verdicts and applicable transcript evidence not supplied for this contribution |
| AI usage | [reports/week-03/ai-usage.md](ai-usage.md); human evaluation pending |

## Minimum usable product candidate

Carry forward the [Week 2 candidate](../week-02/README.md#minimum-usable-product-candidate), approved for building by [DEC-012](../../docs/decisions.md#dec-012): US-01, US-02 and US-03.
Its core task is to send a chat request through a phone-masking plugin and receive an actual model's answer, with company plugins installable without changing the core.
[DEC-011](../../docs/decisions.md#dec-011) permits a deterministic upstream for initial plugin validation; US-01 AC-05 still requires an actual Claude/Gemini response.
This update changes neither the candidate nor its acceptance criteria.

## Customer-meeting outcome

No Week 3 meeting outcome is recorded by this contribution.
No story acceptance, rejection or removal is claimed, and no new customer decision is created.
Both Week 2 presentation commitments now have preparation evidence; neither is claimed presented before the call.

## Contribution

| Member | Work evidenced by this update |
| --- | --- |
| azamatbayramov | Requested the architecture MR, selected Python, requested the runnable customer prototype and the scoped documentation workflow; [task #50](https://github.com/iteam7/gateway7/issues/50), [task #52](https://github.com/iteam7/gateway7/issues/52) and [task #54](https://github.com/iteam7/gateway7/issues/54) track AI-assisted preparation |

Other members' work and human review of this document must be added from their actual evidence before submission.
This table does not assign Responsible or Accountable roles for task #50, #52 or #54.

## Repository evidence

Task #50 covers architecture preparation; task #52 covers the runnable Python increment and its documentation; task #54 covers the scoped documentation workflow.
[PR #53](https://github.com/iteam7/gateway7/pull/53) merged into the architecture branch on 17 October; [PR #51](https://github.com/iteam7/gateway7/pull/51) remains open against `main`.
Task #54 is based on that architecture branch; its PR must target `main` after #51 merges before its own main merge.
No Week 3 task merge to `main` or current green `main` checks are claimed here.
Add the merged PR and latest green link/Markdown runs before submitting the completed weekly report.
No link-check exclusions are added by this contribution.

The initial architecture checks passed: Markdownlint CLI2 0.23.2 over all 32 Markdown files, local targets and anchors for the 46 links in the five changed files, Mermaid 11.12.1 parsing of both architecture diagrams, and `git diff --check`.
For the request-flow expansion, the three edited Markdown files, their 36 links and local anchors, both Mermaid diagrams, and `git diff --check` were checked again and passed.
The five distinct GitHub destinations were also retrieved successfully through the connector; GitHub Actions results are recorded on the PR.

## Python prototype evidence

On 15 October, `uv sync --locked` completed, `uv run --locked python -m compileall -q gateway7 demo` passed, and `uv run --locked pytest -q` reported **99 passed**.
One upstream Starlette TestClient deprecation warning remains; it did not affect the checks.
The final `uv run --locked python -m demo.run` completed successfully with two real local HTTP processes and all exact acceptance fixtures.
The manual commands from `docs/setup.md` were also run: the README curl returned HTTP 200 and `pong — deterministic upstream`, the recorder reported `key_accepted: true`, and captured service logs omitted the synthetic key.
Because executor calls have separate loopback namespaces, the two manual service commands and curl were exercised within one validation process; the commands, environment names, config and ports were unchanged.

Formater separately copied the final source into a disposable Git checkout, verified imports used that copy, observed an unmodified `ping` upstream, installed the sample file, changed configuration and restarted.
The next request returned HTTP 200 and the upstream recorded `ping[checked-by-sample]`.
`git status --porcelain --untracked-files=all` listed exactly the following, with no other changed path:

```text
 M config/demo.yaml
?? company_plugins/sample.py
```

The gateway source was unchanged, the fake upstream accepted the server key, and neither client output nor logs exposed it.
TechLead reviewed all generated code and issued **APPROVED** after correcting and regression-testing startup error sanitization and strict plugin contract validation.
These are observed automated/AI review results, not a human approval or Customer verdict.
The Python workflow uses a locked install, automated tests and the same process demonstration; its action references are pinned to released commit SHAs.
There is no Docker claim: the documented and tested launch route is uv.

Formater's final documentation checks passed: Markdownlint CLI2 0.23.2 over all 37 Markdown files, 119 local link targets/anchors across 11 changed Markdown files, all three architecture diagrams parsed by Mermaid 11.12.1, and `git diff --check`.
The link check here verifies local targets and anchors; external-link and Python workflow results are recorded on the pull request.

| Candidate check | Current evidence boundary |
| --- | --- |
| US-01 / AC-01–04 | Separate-process fake HTTP answer, accepted server key, named missing-key startup failure and captured-log/client redaction checks |
| US-01 / AC-05 | Claude adapter with offline contract tests only; no real key or live provider result was available |
| US-02 / AC-01–03 | Tests and demo cover the three exact synthetic formats, earlier conversation history and unchanged order/date fixture |
| US-03 / AC-01–03 | Module/config-only installation with restart, a literal two-path Git-status check, missing configured modules including disabled declarations, and A/B order |
| Contract failure behavior | Startup contract/settings checks, fail-closed hook results, independent response chain and isolated per-request state are automated checks |
| Human and delivery gates | TODO: human evaluation, distinct accountable reviewer, Customer story verdicts, merge to `main`, clean submitted-state replay and release |

Task #52 does not satisfy the entire Assignment 3 checklist.
The threshold, plan, risks, project/sprint fields, docs-site publication, meeting outcomes, release and submission wrapper remain pending as listed above; the Definition of Done and contribution guide are prepared under task #54.

## Documentation workflow evidence

Task #54 prepares only the requested Assignment 3 items 6, 7, 14 and 15.
TechLead approved the Definition of Done, contribution guide, README navigation and documentation build changes after reviewing the full diff.
Markdownlint passed all **39 Markdown files**; the strict MkDocs build produced **13 pages**, and generated-site validation passed **821 links/assets**.
Chromium checks covered desktop/mobile navigation, the mobile menu and both architecture diagrams, including the Customer view's upward response arrows, with no failed requests or external runtime assets.
All **16 historical report citations** remain intact in repository source and render as plain text on the site; the site excludes weekly reports.
The workflow builds every pull request, including the stacked target, and reserves Pages artifact upload/deployment for `main`; its actions use released full-SHA pins with version comments.

GitHub Pages was still disabled (`has_pages: false`) when checked on 17 October.
The available connector does not expose Pages settings; administrator activation, the first authorized `main` deployment and public URL verification remain pending.
The root README therefore records the intended Pages address as pending text rather than a verified live hyperlink; Assignment 3 items 14 and 15 are not complete.
The activation and verification steps are in [CONTRIBUTING.md](../../CONTRIBUTING.md#build-and-preview-the-site).
These automated checks and AI approval do not replace the distinct human reviewer, task acceptance checkboxes or Customer decisions.

## Deviations

- Task #50 was created through the GitHub connector API using the task form's sections, numbered acceptance criteria and `task` label, rather than by submitting the web form. The available writing route is API-based; the issue remains reviewable, but this declaration does not waive the course's form requirement.
- Task #50 has no evidenced pair of distinct human owners, Responsible/Accountable values, matching assignees or sprint milestone. These remain unresolved; the task is not represented as correctly scheduled. The team must set those values together before treating its scheduling as complete.
- Task #52 also used the GitHub connector API with the task form's sections and `task` label. Its distinct Responsible/Accountable members, matching assignees and sprint milestone remain unassigned; this does not claim the task is correctly scheduled.
- Task #54 used the same API route because the available writing capability does not submit the task form. Its sections, numbered criteria and `task` label preserve reviewability but do not waive the form requirement. Responsible/Accountable members, matching assignees and sprint remain unset; the public project/table view is also unverified.
- Task issues [#64](https://github.com/iteam7/gateway7/issues/64), [#65](https://github.com/iteam7/gateway7/issues/65), [#66](https://github.com/iteam7/gateway7/issues/66) and [#67](https://github.com/iteam7/gateway7/issues/67) were created through the GitHub CLI rather than the task form, at the contributor's request, because the agent doing the work has no signed-in browser to submit the form. Each body carries every section of the form in its order, a numbered `AC-nn` checklist and the `task` label applied by hand, as the form would.
- Task [#79](https://github.com/iteam7/gateway7/issues/79) used the GitHub connector API because the available browser was signed out and could not submit the task form. Its body preserves the form's sections and numbered criteria, and carries the `task` label; this declaration does not waive the form requirement. No sprint, role values or assignees were assigned.

## Privacy

The demonstration uses public synthetic values only; no real provider credential or customer conversation is included.
A repository-wide privacy confirmation remains required before the Week 3 submission.
