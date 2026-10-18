# Week 03 report — Gateway7, Team 7

**Status:** Updated on 18 October 2026 against `main` at `0dc248f92e3dc35201e8343c1625cb15599aa1fe`; the release and documentation site exist, but customer validation, complete sprint assignments and final human assessment are still open.

## Summary

Gateway7's Python gateway, configurable request/response plugins and deterministic HTTP demonstration are on `main`.
The threshold of success, risk register, Definition of Done and contribution guide are also on `main`; this follow-up adds the project plan and refreshes their evidence.
[REL-03](../../docs/project-plan.md#rel-03) was published as [v0.1.0](https://github.com/iteam7/gateway7/releases/tag/v0.1.0) on 18 October, after the 17 October hard deadline, at [commit 0e291413](https://github.com/iteam7/gateway7/commit/0e291413b39e957b7ac86bc3f2ecd417cedfe7d0).
The [documentation site](https://iteam7.github.io/gateway7/) is live.
The release's existence does not establish Customer acceptance or US-01 AC-05: the actual Claude/Gemini response is still outside the recorded evidence.
No candidate story is moved out by this update.

## Coverage

| Deliverable | Artifact or current status |
| --- | --- |
| Architecture preparation | [docs/architecture/README.md](../../docs/architecture/README.md), delivered to `main` through [PR #51](https://github.com/iteam7/gateway7/pull/51); Customer evaluation not recorded |
| Threshold of success | [docs/threshold-of-success.md](../../docs/threshold-of-success.md), linked from [docs/product-vision.md#goal](../../docs/product-vision.md#goal); goals remain Open |
| Project plan | [docs/project-plan.md](../../docs/project-plan.md): MLS-03, SPRINT-03–09, REL-03 and Progress Monitoring; proposed review cadence needs team confirmation |
| Risk register | [docs/risks.md](../../docs/risks.md) |
| Stack decision | [docs/decisions.md#dec-013](../../docs/decisions.md#dec-013), with Python dependencies, lockfile, ignore entries and Dependabot configuration |
| Definition of Done | [docs/definition-of-done.md](../../docs/definition-of-done.md) |
| Contributing guide | [CONTRIBUTING.md](../../CONTRIBUTING.md), including commit/PR/review rules and project views |
| Sprint milestones and issue fields | [Sprint milestones](https://github.com/iteam7/gateway7/milestones) exist per [task #64](https://github.com/iteam7/gateway7/issues/64); scheduled task milestones, Responsible/Accountable values and matching assignees remain unset in the checked issue data |
| GitHub project | [Sprints table view](https://github.com/orgs/iteam7/projects/1/views/3); setup is recorded by [PR #82](https://github.com/iteam7/gateway7/pull/82), with its verification boundary in CONTRIBUTING |
| Minimum usable product | [US-01](https://github.com/iteam7/gateway7/issues/30), [US-02](https://github.com/iteam7/gateway7/issues/31), [US-03](https://github.com/iteam7/gateway7/issues/32): implementation on `main`; live-provider AC-05 and Customer verdicts still lack evidence |
| Changelog and first release | [CHANGELOG.md](../../CHANGELOG.md), [v0.1.0 release](https://github.com/iteam7/gateway7/releases/tag/v0.1.0) and [docs/project-plan.md#rel-03](../../docs/project-plan.md#rel-03); tag protection remains pending |
| Documentation site | [Published documentation](https://iteam7.github.io/gateway7/), linked from the root README; successful deployment is cited below |
| Setup and run instructions | [docs/setup.md](../../docs/setup.md), including Windows PowerShell commands, linked from [README.md](../../README.md) |
| Week 2 action points | Carry-over source: [reports/week-02/meeting-report.md#action-points](../week-02/meeting-report.md#action-points); the closing `Previous action points` section is still missing from the Week 3 meeting report |
| Week 2 open questions | Carry-over source: [reports/week-02/meeting-report.md#open-questions](../week-02/meeting-report.md#open-questions); the closing `Previous open questions` section is still missing from the Week 3 meeting report |
| Meeting script | [reports/week-03/meeting-script.md](meeting-script.md), prepared for 16 October; preparation is not evidence of the meeting outcome |
| Customer validation | `reports/week-03/meeting-report.md` and applicable transcript evidence are not present; see the participant handoff below |
| AI usage | [reports/week-03/ai-usage.md](ai-usage.md); the team's assessment remains TODO and must be supplied by a human |

## Minimum usable product candidate

The [Week 2 candidate](../week-02/README.md#minimum-usable-product-candidate), approved for building by [DEC-012](../../docs/decisions.md#dec-012), remains US-01, US-02 and US-03.
Its core task is to send a chat request through a phone-masking plugin and receive an actual model's answer, with company plugins installable without changing the core.
[DEC-011](../../docs/decisions.md#dec-011) permits a deterministic upstream for initial plugin validation; it does not remove US-01 AC-05.
The plan retains this scope in [MLS-03](../../docs/project-plan.md#mls-03), without interpreting the release as acceptance of the candidate.

## Customer-meeting outcome

No Week 3 meeting report or source establishing its story verdicts was available for this update.
The planned 16 October meeting is not treated as proof that any story was shown, accepted, rejected or removed.

| Candidate story | Recorded Week 3 Customer verdict |
| --- | --- |
| [US-01](https://github.com/iteam7/gateway7/issues/30) | Not recorded; no story-verdict DEC-nnn is available |
| [US-02](https://github.com/iteam7/gateway7/issues/31) | Not recorded; no story-verdict DEC-nnn is available |
| [US-03](https://github.com/iteam7/gateway7/issues/32) | Not recorded; no story-verdict DEC-nnn is available |

A participant must write `reports/week-03/meeting-report.md` from the actual meeting record, using the course's eight sections in order: Metadata, Previous action points, Previous open questions, Summary, Decisions, Action points, Open questions and Disagreements.
The handoff is:

- Establish the actual date, attendees, duration and answers to the recording/publication questions; do not infer them from the script.
- Close or carry forward the three Week 2 action rows: presenting the architecture, presenting the technical prototype, and confirming infrastructure scope. Architecture, code and CI now provide preparation/implementation evidence; they do not prove the presentations occurred.
- Answer or carry forward all six Week 2 open questions. Python is grounded in [DEC-013](../../docs/decisions.md#dec-013); plugin capacity, secret storage, contract validation, demo versus real-provider scope and the presentation date still need their actual outcomes recorded.
- Record each shown story's acceptance or rejection against its AC-nn in `docs/decisions.md`, link the resulting DEC-nnn from the report, and add the outcome to the affected story issue. Any candidate removal needs its own Customer decision.
- Record at least two actual meeting action points with GitHub owners and due dates inside Week 4. No action or owner is invented to fill this requirement.
- Supply the transcript when required by the meeting format and permission outcome; keep private-only material in the Moodle submission.

## Contribution

These links establish repository contributions, not role assignments or human assessment of AI output.

| Member | Evidenced work |
| --- | --- |
| azamatbayramov | Architecture and prototype: [PR #51](https://github.com/iteam7/gateway7/pull/51), including [PR #53](https://github.com/iteam7/gateway7/pull/53); documentation workflow and guides: [PR #60](https://github.com/iteam7/gateway7/pull/60); publication/project evidence: [PR #80](https://github.com/iteam7/gateway7/pull/80) |
| ExFuseMe | Threshold of success: [PR #58](https://github.com/iteam7/gateway7/pull/58); risk register: [PR #59](https://github.com/iteam7/gateway7/pull/59), later delivered to `main` through PR #83 |
| iceberkut | Sprint milestone documentation: [PR #68](https://github.com/iteam7/gateway7/pull/68); issue-field and project setup records: [PR #81](https://github.com/iteam7/gateway7/pull/81), [PR #82](https://github.com/iteam7/gateway7/pull/82); risk-register integration: [PR #83](https://github.com/iteam7/gateway7/pull/83) |
| DeniBorsh | Windows demo/test fixes and setup instructions: [PR #73](https://github.com/iteam7/gateway7/pull/73), [PR #74](https://github.com/iteam7/gateway7/pull/74), [PR #75](https://github.com/iteam7/gateway7/pull/75), release changelog: [PR #76](https://github.com/iteam7/gateway7/pull/76); published [v0.1.0](https://github.com/iteam7/gateway7/releases/tag/v0.1.0) |

## Repository evidence

[PR #51](https://github.com/iteam7/gateway7/pull/51) merged into `main` and closed [task #50](https://github.com/iteam7/gateway7/issues/50).
The prototype from PR #53 reached `main` through that merge; task #52's issue state is not used as proof of completed story acceptance.

At the checked `main` commit `0dc248f92e3dc35201e8343c1625cb15599aa1fe`, the latest [Markdown check](https://github.com/iteam7/gateway7/actions/runs/39164086111), [link check](https://github.com/iteam7/gateway7/actions/runs/39164085856) and [documentation build/deployment](https://github.com/iteam7/gateway7/actions/runs/39164086109) succeeded.
The public documentation home page returned HTTP 200 and Gateway7 content on 18 October.
These runs precede this documentation follow-up; its own checks are attached to its PR, and the final submission must cite the latest successful runs after merging.
No new link-check exclusions are introduced by this update.

## Python prototype evidence

The earlier Linux validation recorded `uv sync --locked`, `compileall`, **99 passing tests** and a successful separate-process `python -m demo.run`.
The manual request returned HTTP 200 with `pong — deterministic upstream`; the fake upstream confirmed the server key, and captured logs did not expose it.
A disposable checkout also verified the literal plugin-installation check: only `config/demo.yaml` and a new `company_plugins/sample.py` changed; after restart the upstream received `ping[checked-by-sample]`.
These are recorded automated checks, not a real-provider call or Customer verdict.

| Candidate check | Evidence boundary |
| --- | --- |
| US-01 / AC-01–04 | Separate-process fake HTTP response, server-key forwarding, missing-key startup failure and captured-log/client redaction checks |
| US-01 / AC-05 | Claude adapter and offline contract tests; no actual Claude/Gemini response in the recorded evidence |
| US-02 / AC-01–03 | Exact synthetic phone formats, prior conversation history and unchanged order/date fixture |
| US-03 / AC-01–03 | Module/config-only installation with restart, two-path Git-status check, missing configured modules and A/B order |

## Clean-checkout run on Windows

The Windows 11 clean-checkout run on 17 October used `main` at `b548813`, uv 0.13.1 and pinned Python 3.12.
Installation, compilation and manual HTTP requests passed in Git Bash and Windows PowerShell 5.1.
The run found two Windows-specific problems: generated test IDs caused **98 passed / 2 errors**, and the demo's path comparison failed.
PR #73 fixed the path comparison, PR #74 fixed test IDs, and PR #75 added PowerShell instructions; branch validation then reported a successful demonstration and **99 passed** on the same machine.
Those fixes are now on `main` and in v0.1.0; a fresh Windows replay of the final submitted commit is still required.

## Documentation workflow evidence

The documentation implementation's recorded review covered a strict MkDocs build, **13 pages / 821 links and assets**, desktop/mobile navigation and both rendered architecture diagrams.
That historical count predates the threshold, risk register and project plan pages; it is not a count for the current site.
The earlier Pages-disabled state has been superseded by the successful main deployment cited above.

## Remaining submission gates

- A meeting participant completes the report, Customer DEC-nnn verdicts, Week 2 carry-over and at least two real Week 4 actions.
- The team sets actual SPRINT-03 task milestones, Responsible/Accountable values and matching assignees. The checked candidate/task issues still have empty values; a plan file or setup PR does not assign them.
- A repository administrator protects v0.1.0 against movement and deletion; the checked rulesets cover `main`, with no tag-targeting rule.
- A human completes the accepted/changed/rejected assessment in `ai-usage.md` and confirms the proposed weekly review cadence in the plan.
- After review and merge, the team replays the submitted state, updates final main-check evidence and prepares the Moodle permalink/PDF/snapshot from one actual main commit.

## Deviations

- Task #50 was created through the GitHub connector API using the task form's sections, numbered acceptance criteria and `task` label, rather than by submitting the web form. The available writing route is API-based; the issue remains reviewable, but this declaration does not waive the course's form requirement.
- Task #50 has no evidenced pair of distinct human owners, Responsible/Accountable values, matching assignees or sprint milestone. These remain unresolved; the task is not represented as correctly scheduled. The team must set those values together before treating its scheduling as complete.
- Task #52 also used the GitHub connector API with the task form's sections and `task` label. Its distinct Responsible/Accountable members, matching assignees and sprint milestone remain unassigned; this does not claim the task is correctly scheduled.
- Task #54 used the same API route because the available writing capability does not submit the task form. Its sections, numbered criteria and `task` label preserve reviewability but do not waive the form requirement. Responsible/Accountable members, matching assignees and sprint remain unset; later project setup is recorded in the coverage table above.
- Task issues [#64](https://github.com/iteam7/gateway7/issues/64), [#65](https://github.com/iteam7/gateway7/issues/65), [#66](https://github.com/iteam7/gateway7/issues/66) and [#67](https://github.com/iteam7/gateway7/issues/67) were created through the GitHub CLI rather than the task form, at the contributor's request, because the agent doing the work has no signed-in browser to submit the form. Each body carries every section of the form in its order, a numbered `AC-nn` checklist and the `task` label applied by hand, as the form would.
- Task [#79](https://github.com/iteam7/gateway7/issues/79) used the GitHub connector API because the available browser was signed out and could not submit the task form. Its body preserves the form's sections and numbered criteria, and carries the `task` label; this declaration does not waive the form requirement. No sprint, role values or assignees were assigned.

- The project plan and this evidence refresh are prepared on 18 October, after the Week 3 hard deadline and after v0.1.0 was published. They are a separate follow-up change and are not represented as files already included in the release tag.
- v0.1.0 was published on 18 October. The required protection against moving/deleting the tag is not configured in the checked repository rulesets; an administrator must add it. This declaration does not satisfy tag protection.
- No Week 3 Customer verdict record was available when the release and report were checked, so the required release-after-validation sequence cannot be established from the repository evidence. No missing verdict is inferred from the release title.
- The seven sprint milestones and field setup do not establish issue-level scheduling: the checked candidate/task issues still have no milestone, Responsible/Accountable values or matching assignees. The plan's proposed monitoring cadence also remains subject to team confirmation.

## Privacy

This update commits no private-only material; the full submission's privacy confirmation remains with the team.
The demonstration uses public synthetic values and includes no real provider credential or customer conversation.
