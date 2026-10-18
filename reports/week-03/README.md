# Week 03 report — Gateway7, Team 7

**Status:** Repository baseline checked on 18 October 2026 at `main` commit `0dc248f92e3dc35201e8343c1625cb15599aa1fe`; this update also incorporates the supplied 16 October meeting record. The release and documentation site exist; explicit Customer story verdicts, agreed follow-up assignments, complete sprint assignments and final human assessment remain open.

## Summary

Gateway7's Python gateway, configurable request/response plugins and deterministic HTTP demonstration are on `main`.
The threshold of success, risk register, Definition of Done and contribution guide are also on `main`; this follow-up adds the project plan and refreshes their evidence.
[REL-03](../../docs/project-plan.md#rel-03) was published as [v0.1.0](https://github.com/iteam7/gateway7/releases/tag/v0.1.0) on 18 October, after the 17 October hard deadline, at [commit 0e291413](https://github.com/iteam7/gateway7/commit/0e291413b39e957b7ac86bc3f2ecd417cedfe7d0).
The [documentation site](https://iteam7.github.io/gateway7/) is live.
The release's existence does not establish Customer acceptance or US-01 AC-05: the actual Claude/Gemini response is still outside the recorded evidence.
No candidate story is moved out by this update.
The [meeting report](meeting-report.md) records the architecture/prototype presentation, Customer's requests for deeper execution/failure explanation and three interacting plugins ([DEC-014](../../docs/decisions.md#dec-014), [DEC-015](../../docs/decisions.md#dec-015)), and the Week 2 carry-over outcomes.

## Coverage

| Deliverable | Artifact or current status |
| --- | --- |
| Architecture preparation | [docs/architecture/README.md](../../docs/architecture/README.md), delivered to `main` through [PR #51](https://github.com/iteam7/gateway7/pull/51); the [meeting report](meeting-report.md#summary) records requested execution/failure detail, not architecture acceptance |
| Threshold of success | [docs/threshold-of-success.md](../../docs/threshold-of-success.md), linked from [docs/product-vision.md#goal](../../docs/product-vision.md#goal); four goals remain Open; [docs/threshold-review.md](../../docs/threshold-review.md) proposes precise corrections to the TOS-02/TOS-04 measures for Customer review |
| Project plan | [docs/project-plan.md](../../docs/project-plan.md): MLS-03, SPRINT-03–09, REL-03 and Progress Monitoring; proposed review cadence needs team confirmation |
| Risk register | [docs/risks.md](../../docs/risks.md) |
| Stack decision | [docs/decisions.md#dec-013](../../docs/decisions.md#dec-013), with Python dependencies, lockfile, ignore entries and Dependabot configuration |
| Definition of Done | [docs/definition-of-done.md](../../docs/definition-of-done.md) |
| Contributing guide | [CONTRIBUTING.md](../../CONTRIBUTING.md), including commit/PR/review rules and project views |
| Sprint milestones and issue fields | [Sprint milestones](https://github.com/iteam7/gateway7/milestones) are reported complete by checked ACs in [task #64](https://github.com/iteam7/gateway7/issues/64); all 39 checked non-PR issues returned no milestone, no assignees and no issue-field values. Organization field definitions/visibility were not freshly verified |
| GitHub project | [Sprints table view](https://github.com/orgs/iteam7/projects/1/views/3); setup is reported by [PR #82](https://github.com/iteam7/gateway7/pull/82), with its verification boundary in [CONTRIBUTING.md](../../CONTRIBUTING.md#project-views-and-scheduling); live layout and coverage were not freshly verified |
| Minimum usable product | [US-01](https://github.com/iteam7/gateway7/issues/30), [US-02](https://github.com/iteam7/gateway7/issues/31), [US-03](https://github.com/iteam7/gateway7/issues/32): implementation on `main`; live-provider AC-05 and Customer verdicts still lack evidence |
| Changelog and first release | [CHANGELOG.md](../../CHANGELOG.md), [v0.1.0 release](https://github.com/iteam7/gateway7/releases/tag/v0.1.0) and [docs/project-plan.md#rel-03](../../docs/project-plan.md#rel-03); tag protection remains pending |
| Documentation site | [Published documentation](https://iteam7.github.io/gateway7/), linked from the root README; successful deployment is cited below |
| Setup and run instructions | [docs/setup.md](../../docs/setup.md), including Windows PowerShell commands, linked from [README.md](../../README.md) |
| Week 2 action points | [reports/week-03/meeting-report.md#previous-action-points](meeting-report.md#previous-action-points): both presentations occurred; infrastructure confirmation is carried forward |
| Week 2 open questions | [reports/week-03/meeting-report.md#previous-open-questions](meeting-report.md#previous-open-questions): all six addressed or carried forward; Python and the retrospective presentation date are established |
| Meeting script | [reports/week-03/meeting-script.md](meeting-script.md), prepared for 16 October; preparation is not evidence of the meeting outcome |
| Customer validation | [reports/week-03/meeting-report.md](meeting-report.md), reconstructed from a privately supplied transcript; no per-story verdicts were recorded, and transcript publication/private-submission permission remains to be confirmed |
| AI usage | [reports/week-03/ai-usage.md](ai-usage.md); the team's assessment remains TODO and must be supplied by a human |

## Minimum usable product candidate

The [Week 2 candidate](../week-02/README.md#minimum-usable-product-candidate), approved for building by [DEC-012](../../docs/decisions.md#dec-012), remains US-01, US-02 and US-03.
Its core task is to send a chat request through a phone-masking plugin and receive an actual model's answer, with company plugins installable without changing the core.
[DEC-011](../../docs/decisions.md#dec-011) permits a deterministic upstream for initial plugin validation; it does not remove US-01 AC-05.
The plan retains this scope in [MLS-03](../../docs/project-plan.md#mls-03), without interpreting the release as acceptance of the candidate.

## Customer-meeting outcome

The [16 October meeting report](meeting-report.md) is based on the supplied transcript, with participant review still pending.
It records a running mock-provider phone-masking example and an explanation of the YAML configuration and Python plugin interface.
Customer requested clearer execution/failure rationale and a three-plugin demonstration through [DEC-014](../../docs/decisions.md#dec-014) and [DEC-015](../../docs/decisions.md#dec-015).
The [story evidence table](meeting-report.md#summary) separates what was actually shown from the existing acceptance criteria.

| Candidate story | Recorded Week 3 Customer verdict |
| --- | --- |
| [US-01](https://github.com/iteam7/gateway7/issues/30) | Not recorded; no story-verdict DEC-nnn is available |
| [US-02](https://github.com/iteam7/gateway7/issues/31) | Not recorded; no story-verdict DEC-nnn is available |
| [US-03](https://github.com/iteam7/gateway7/issues/32) | Not recorded; no story-verdict DEC-nnn is available |

No genuine acceptance/rejection DEC can be reconstructed from this discussion; the candidate remains US-01–03, and US-04–09 are not represented as accepted.
The next validation must run each AC and obtain explicit verdicts, then record their DECs and issue comments.
The report proposes Week 4 dates and presenters for the requested follow-ups, clearly separating these proposals from agreed meeting commitments.
A participant must review the paraphrase, confirm action ownership/dates and establish the missing permission answers.
The supplied transcript is kept private; it has not been published or verified as submitted to instructors, and publication has not been described as refused.

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
The prototype from PR #53 reached `main` through that merge on 17 October, after the 16 October meeting.
[Task #52](https://github.com/iteam7/gateway7/issues/52) still has open state and unchecked criteria; its accountable reviewer must reconcile the merged implementation with those criteria before completing the task. That completion would not accept its stories.

At the checked `main` commit `0dc248f92e3dc35201e8343c1625cb15599aa1fe`, the latest [Markdown check](https://github.com/iteam7/gateway7/actions/runs/39164086111), [link check](https://github.com/iteam7/gateway7/actions/runs/39164085856) and [documentation build/deployment](https://github.com/iteam7/gateway7/actions/runs/39164086109) succeeded.
The public documentation home page returned HTTP 200 and Gateway7 content on 18 October.
These runs precede this documentation follow-up; its own checks are attached to its PR, and the final submission must cite the latest successful runs after merging.
No new link-check exclusions are introduced by this update.
The existing workflow accepts HTTP 429 and 503 as an availability workaround; a green run is therefore not proof that every external URL returned HTTP 200. Required submission links still need to be opened before submission.

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
[Task #84](https://github.com/iteam7/gateway7/issues/84) subsequently reported an intermittent Windows deadline/cancellation defect that can accept a late plugin result.
The proposed Windows CI remains in [draft PR #78](https://github.com/iteam7/gateway7/pull/78); the earlier 99-test pass and current Ubuntu checks do not establish that the defect is fixed.

## Documentation workflow evidence

The documentation implementation's recorded review covered a strict MkDocs build, **13 pages / 821 links and assets**, desktop/mobile navigation and both rendered architecture diagrams.
That historical count predates the threshold, risk register and project plan pages; it is not a count for the current site.
The earlier Pages-disabled state has been superseded by the successful main deployment cited above.

## Remaining submission gates

| Who acts | Where | What settles the gate |
| --- | --- | --- |
| Customer and meeting participant | [US-01](https://github.com/iteam7/gateway7/issues/30), [US-02](https://github.com/iteam7/gateway7/issues/31), [US-03](https://github.com/iteam7/gateway7/issues/32), [meeting report](meeting-report.md) | Run the existing ACs, including an authorized real-provider call, obtain actual verdict DECs and issue comments, and confirm the report, follow-up owners/dates and transcript permissions |
| Customer and team | [Threshold clarification proposal](../../docs/threshold-review.md), [Progress Monitoring](../../docs/project-plan.md#progress-monitoring) | Resolve the TOS-02/TOS-04 measure inconsistencies without silently moving the bar; assess expired Week 3 evidence and risk windows, and confirm the proposed team review time |
| Team members assigning and reviewing work | [Task #52](https://github.com/iteam7/gateway7/issues/52), [task #67](https://github.com/iteam7/gateway7/issues/67), [sprint milestones](https://github.com/iteam7/gateway7/milestones) | Assign actual Responsible/Accountable members, those same two assignees and the proper sprint; reviewer checks task ACs. Reconcile merged task #52 and reschedule unfinished work before closing the released SPRINT-03 milestone |
| Organization owner and project maintainer | [Task #65](https://github.com/iteam7/gateway7/issues/65), [task #66](https://github.com/iteam7/gateway7/issues/66) | Verify public single-select field definitions/options/pinning, public project access, repository description, every open issue and required table columns/grouping; record review evidence and check the actual task ACs, which remain unticked despite closure |
| Repository administrator | Repository Settings → Rules → Rulesets | Protect `v0.1.0` against update and deletion with an active tag rule; the inspected ruleset protects only `main` |
| Human reviewers and submission owner | [AI usage](ai-usage.md), [PR #85](https://github.com/iteam7/gateway7/pull/85) | Supply the team's accepted/changed/rejected assessment, complete independent PR review, merge the reviewed artifacts and prepare the final same-commit submission below |

The private Moodle submission is still a separate deliverable. After merging, select one final `main` commit, repeat the setup/checks at that commit and update the report's final green CI evidence.
The PDF is at most two pages, identifying Gateway7, Team 7 and Week 3; it contains the private GitHub-username/name/university-email roster, the full-commit report permalink, the instructor-accessible meeting recording or its truthful absence reason, and the privacy confirmation. If public transcript publication was refused, the transcript goes in an appendix outside the two-page limit; the permission outcome must first be established.
Open the submitted permalink and private links, then create the repository ZIP from that same commit. Keep the PDF, private source material and ZIP outside the public repository; a PR-branch snapshot or the earlier v0.1.0 tag is not the final submission state while the new report and plan are absent from it.

## Deviations

- Task #50 was created through the GitHub connector API using the task form's sections, numbered acceptance criteria and `task` label, rather than by submitting the web form. The available writing route is API-based; the issue remains reviewable, but this declaration does not waive the course's form requirement.
- Task #50 has no evidenced pair of distinct human owners, Responsible/Accountable values, matching assignees or sprint milestone. These remain unresolved; the task is not represented as correctly scheduled. The team must set those values together before treating its scheduling as complete.
- Task #52 also used the GitHub connector API with the task form's sections and `task` label. Its distinct Responsible/Accountable members, matching assignees and sprint milestone remain unassigned; this does not claim the task is correctly scheduled.
- Task #54 used the same API route because the available writing capability does not submit the task form. Its sections, numbered criteria and `task` label preserve reviewability but do not waive the form requirement. Responsible/Accountable members, matching assignees and sprint remain unset; later project setup is recorded in the coverage table above.
- Task issues [#64](https://github.com/iteam7/gateway7/issues/64), [#65](https://github.com/iteam7/gateway7/issues/65), [#66](https://github.com/iteam7/gateway7/issues/66) and [#67](https://github.com/iteam7/gateway7/issues/67) were created through the GitHub CLI rather than the task form, at the contributor's request, because the agent doing the work has no signed-in browser to submit the form. Each body carries every section of the form in its order, a numbered `AC-nn` checklist and the `task` label applied by hand, as the form would.
- Task [#79](https://github.com/iteam7/gateway7/issues/79) used the GitHub connector API because the available browser was signed out and could not submit the task form. Its body preserves the form's sections and numbered criteria, and carries the `task` label; this declaration does not waive the form requirement. No sprint, role values or assignees were assigned.

- The project plan and this evidence refresh are prepared on 18 October, after the Week 3 hard deadline and after v0.1.0 was published. They are a separate follow-up change and are not represented as files already included in the release tag.
- The architecture/prototype reached `main` through PR #51 on 17 October; PR #53 had first merged into its architecture branch that day. The 16 October meeting therefore preceded the main merge, contrary to the required merge-before-meeting sequence. This later documentation update records the sequence and cannot repair it retrospectively.
- v0.1.0 was published on 18 October. The required protection against moving/deleting the tag is not configured in the checked repository rulesets; an administrator must add it. This declaration does not satisfy tag protection.
- The supplied transcript establishes that the architecture/prototype meeting occurred before the release, but it contains no explicit acceptance/rejection of the candidate stories. The required release-after-story-validation sequence therefore remains unestablished; the release title does not supply those verdicts.
- The meeting report is reconstructed retrospectively from the privately supplied transcript. It did not record AC-by-AC verdicts, separate permission answers or agreed Week 4 owners/dates. The report preserves those gaps and labels proposed scheduling; participant confirmation and actual Customer validation are still required. No transcript is published, and private instructor submission is not claimed.
- The seven sprint milestones and field setup do not establish issue-level scheduling: the checked candidate/task issues still have no milestone, Responsible/Accountable values or matching assignees. The plan's proposed monitoring cadence also remains subject to team confirmation.

## Privacy

This update commits no private-only material; the full submission's privacy confirmation remains with the team.
The demonstration uses public synthetic values and includes no real provider credential or customer conversation.
