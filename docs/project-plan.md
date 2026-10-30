# Project plan

Corrected on 25 October 2026 under [task #95](https://github.com/iteam7/gateway7/issues/95), using the current tracker and the [SPRINT-04 retrospective](https://github.com/iteam7/gateway7/blob/main/reports/week-04/sprint-retrospective.md).
The correction records the work's current placement and the missing planning evidence; it does not reconstruct earlier team commitments.
Due dates follow [Assignment 4, Part 1](https://github.com/inno-itpd/itpd/blob/main/assignments/assignment-4.md#part-1-plan-the-sprint-refine-the-backlog-and-set-the-fields) and the [course syllabus](https://github.com/inno-itpd/itpd/blob/main/course/syllabus.md#3-weekly-curriculum--milestones): Weeks 4–9 are due on Saturday at 23:59, with no soft deadline.
The corrected SPRINT-04–09 dates below match the GitHub milestone due dates, updated and checked on 25 October.
The monitoring cadence and the unplanned sprint goals remain proposals for team review.
Updated on 30 October 2026 under [task #138](https://github.com/iteam7/gateway7/issues/138): the user delegated the new milestone choices and the remaining SPRINT-05 scope to AI-assisted planning.
This late planning update is dated when it was made; it supplies neither a start-of-sprint commitment nor a Customer verdict.

## Milestones

### MLS-03

- **Due:** 2026-10-17
- **Sprints:** [SPRINT-03](#sprint-03)
- **Advances:** [TOS-01](threshold-of-success.md#tos-01), [TOS-02](threshold-of-success.md#tos-02), [TOS-04](threshold-of-success.md#tos-04)

A client sends a chat request through a phone-masking plugin and receives an actual model's answer, with company plugins installable without changing the gateway core.
The candidate is [US-01](https://github.com/iteam7/gateway7/issues/30), [US-02](https://github.com/iteam7/gateway7/issues/31) and [US-03](https://github.com/iteam7/gateway7/issues/32), approved for building by [DEC-012](decisions.md#dec-012).
The deterministic upstream allowed by [DEC-011](decisions.md#dec-011) supports initial plugin checks; it does not replace US-01 AC-05 or the Customer's story verdicts.
The published release below is delivery evidence, not proof that the milestone's acceptance gates have all passed.

### MLS-05

- **Due:** 2026-10-31
- **Sprints:** [SPRINT-05](#sprint-05)
- **Advances:** [TOS-02](threshold-of-success.md#tos-02), [TOS-03](threshold-of-success.md#tos-03)

An operator can diagnose a failing or slow company plugin without exposing the request's content, and a reviewer can reproduce the gateway's request and response policy checks.
The remaining response-pipeline checks and the new per-request diagnostic record make the plugin boundary observable rather than treating the release as proof of correct composition.
The carried delivery, architecture and quality checks remain gates for the increment; their planned scope does not assert a passing result.

### MLS-07

- **Due:** 2026-11-14
- **Sprints:** [SPRINT-06](#sprint-06), [SPRINT-07](#sprint-07)
- **Advances:** [TOS-02](threshold-of-success.md#tos-02), [TOS-03](threshold-of-success.md#tos-03)

A company engineer can check a plugin on synthetic examples before enabling it, reproduce its configured gateway behavior and inspect usage by developer and model without reading payloads.
Configured access checks establish who can use each model; the usage record distinguishes their calls without introducing developer identities into aggregate metric labels.
The independent plugin workflow and offline examples provide repeatable evidence for the policy and plugin-extension goals; they do not change those goals' existing measures or deadlines.

## Sprints

The backlog links open the existing GitHub sprint milestones; the 30 October update selects remaining SPRINT-05 work without creating duplicate milestones or closing the ongoing sprint.
The available repository evidence supplies no pre-work story-point estimates or Customer acceptance verdicts for US-01–US-09.
The new estimates confirmed by azamatbayramov on 25 October concern remaining future verification and rework; they do not reconstruct earlier estimates or velocity.
Closed story issues therefore do not establish accepted completion or a measurable velocity under the [Definition of Done](definition-of-done.md#story).
Unselected future candidates stay in the unscheduled product backlog; legacy milestone placement does not establish that earlier refinement or sprint planning happened.

### SPRINT-03

A clean checkout runs the candidate's chat flow, phone masking and configurable company plugin, with the real-provider criterion and each Customer verdict recorded against its story.

- **Due:** 2026-10-17
- **Sprint Backlog:** [the issues assigned to SPRINT-03](https://github.com/iteam7/gateway7/milestone/1)

The candidate's unfinished work remains in this milestone pending explicit rescheduling and Customer review.
The release records delivery; it does not settle the outstanding story criteria or acceptance verdicts.

#### REL-03

Released as [v0.1.0](https://github.com/iteam7/gateway7/releases/tag/v0.1.0) on 2026-10-18.

### SPRINT-04

Proposed goal: a company engineer can run three interacting plugins and follow the instructions to add another without core edits, while the team explains and demonstrates the selected execution and failure behavior.

- **Due:** 2026-10-24
- **Sprint Backlog:** [the issues assigned to SPRINT-04](https://github.com/iteam7/gateway7/milestone/2)
- **Planned Velocity:** N/A — missing; the available records supply no pre-work planning or story-point total.
- **Actual Velocity:** N/A — not established; story estimates and Customer acceptance evidence are missing, and the milestone remains open.

The proposed outcome advances [TOS-03](threshold-of-success.md#tos-03) and responds to [DEC-014](decisions.md#dec-014) and [DEC-015](decisions.md#dec-015): justify the runner's design, make plugin failures diagnosable, and demonstrate composition beyond one masking plugin.
The [retrospective's planning finding](https://github.com/iteam7/gateway7/blob/main/reports/week-04/sprint-retrospective.md#what-did-not) reports that SPRINT-04 started without planning, an agreed backlog, planned velocity or agreed owners.
The goal above preserves the earlier proposal, and the backlog link records the current tracker state; neither supplies the missing pre-work agreement.
Assignment 4 follow-ups were created on 25 October and placed in SPRINT-05 as carryover, while existing unfinished SPRINT-04 issues remain in their original milestone pending a recorded rescheduling decision.

The Windows follow-ups have distinct evidence: the [25 October report on #84](https://github.com/iteam7/gateway7/issues/84#issuecomment-6401505160) records the deadline fix on `main` and 50 successful repetitions of its three deadline tests on Windows 11, with Accountable verification still pending.
[Task #77](https://github.com/iteam7/gateway7/issues/77) and [PR #78](https://github.com/iteam7/gateway7/pull/78) cover the Windows CI job, blocked by two other Windows failures in that report.
The two tasks remain separate, and this correction does not move or close either one.

#### REL-04

Released as [v0.2.0](https://github.com/iteam7/gateway7/releases/tag/v0.2.0) on 2026-10-26, without a Week 4 Customer Review; it is a technical release and establishes no Customer acceptance.

### SPRINT-05

An operator can identify a failing or slow company plugin without exposing request content, while a reviewer can reproduce the gateway's delivery and policy checks.

- **Due:** 2026-10-31
- **Sprint Backlog:** [the issues assigned to SPRINT-05](https://github.com/iteam7/gateway7/milestone/3)
- **Planned Velocity:** The original commitment is unavailable; the 30 October remaining-scope forecast is **8 SP**, calculated by hand as US-05 `3` + US-12 `5` from their current native `Story Points` values.

Planning update: 30 October 2026, through the user's delegated AI-assisted refinement and selection under [task #138](https://github.com/iteam7/gateway7/issues/138) and [task #139](https://github.com/iteam7/gateway7/issues/139).
The milestone is the selection record; this plan does not duplicate its issue list.
The remaining scope is the verification and resulting fixes for [US-05](https://github.com/iteam7/gateway7/issues/34), plus the new diagnostic story [US-12](https://github.com/iteam7/gateway7/issues/140).
Their estimates compare prospective scope with the already estimated backlog; they are not inferred from completed code or substituted for missing start-of-sprint estimates.
The historical [US-06](https://github.com/iteam7/gateway7/issues/35) remains in its existing milestone with no recorded estimate; its closed state supplies neither story points nor Customer acceptance, so the `8 SP` subtotal is not a reconstructed total for the original sprint.

All eight Assignment 4 carryover tasks created on 25 October retain their placement, as required by [task #95](https://github.com/iteam7/gateway7/issues/95); no unfinished historical work is silently moved or closed by this update.
New selection sets the sprint milestone, distinct native Responsible and Accountable values and exactly those two assignees together; scheduled tasks also carry native Priority.
Unselected refined stories retain their estimates without a milestone, role values or assignees.

Actual Velocity is added only at the real sprint close, after the Customer verdicts from [task #132](https://github.com/iteam7/gateway7/issues/132) establish which stories were accepted.
That close-out must record each unfinished issue's actual move to a later sprint before closing this milestone; missing historical estimates or review evidence are not replaced with zero.
The [SPRINT-04 actions](https://github.com/iteam7/gateway7/blob/main/reports/week-04/sprint-retrospective.md#actions) still require the tracker and review records to show their outcome, including the Customer review and remaining Windows work.
The completed [testing-plan task #137](https://github.com/iteam7/gateway7/issues/137) is preserved in the testing rows below; no new result is claimed by the planning update.

#### REL-05

### SPRINT-06

Provisional goal: a reviewer can verify configured model permissions and assess gateway usage and failures without recording raw prompts, responses or provider secrets.

- **Due:** 2026-11-07
- **Sprint Backlog:** [SPRINT-06 milestone; selection pending](https://github.com/iteam7/gateway7/milestone/4)

#### REL-06

### SPRINT-07

Provisional goal: a plugin author can assess synthetic examples offline and a non-author can reproduce the documented plugin workflow through the gateway's core request flow.

- **Due:** 2026-11-14
- **Sprint Backlog:** [SPRINT-07 milestone; selection pending](https://github.com/iteam7/gateway7/milestone/5)

#### REL-07

### SPRINT-08

Provisional goal: a reviewer can reproduce a released gateway configuration and verify its dependency, secret and release controls from the documented baseline.

- **Due:** 2026-11-21
- **Sprint Backlog:** [the issues currently assigned to SPRINT-08](https://github.com/iteam7/gateway7/milestone/6)

#### REL-08

### SPRINT-09

Provisional goal: the final gateway release demonstrates the agreed core task, with usability findings, Customer decisions and evidence for every threshold outcome ready for the final presentation.

- **Due:** 2026-11-28

#### REL-09

## Quality Requirement Testing Plan

Each row is one quality requirement test and what it found at its last check; the test itself is defined in its requirement's file.

| QR | QRT | Status | Checked | Planned for sprint | Evidence |
| --- | --- | --- | --- | --- | --- |
| [QR-01](quality-requirements/qr/QR-01.md) | [QR-01 QRT-01](quality-requirements/qr/QR-01.md#qrt-01) | Not verified | None | [SPRINT-05](#sprint-05) | None |
| [QR-02](quality-requirements/qr/QR-02.md) | [QR-02 QRT-01](quality-requirements/qr/QR-02.md#qrt-01) | Not verified | None | [SPRINT-05](#sprint-05) | None |
| [QR-03](quality-requirements/qr/QR-03.md) | [QR-03 QRT-01](quality-requirements/qr/QR-03.md#qrt-01) | Not verified | None | [SPRINT-05](#sprint-05) | None |
| [QR-03](quality-requirements/qr/QR-03.md) | [QR-03 QRT-02](quality-requirements/qr/QR-03.md#qrt-02) | Not verified | None | [SPRINT-05](#sprint-05) | None |

## Progress Monitoring

- **Review:** proposed team review every Thursday at 18:00 Europe/Moscow, before Saturday's 23:59 deadline and separate from the Customer meeting; the team still needs to confirm this cadence.
- **Checked by:** each scheduled issue's Responsible member presents implementation evidence, its distinct Accountable member checks the acceptance criteria, and the whole team compares the sprint goal with completed work and unresolved gates.
- **Review inputs:** read the [threshold of success](threshold-of-success.md) and [risk register](risks.md), review each trigger and response, and record outcomes in the artifact they change; a threshold change or candidate removal requires the Customer's recorded decision.
- **Testing plan:** read every row of the [Quality Requirement Testing Plan](#quality-requirement-testing-plan) that is not `Passes`, and keep its result and planned sprint until a new check is recorded.
- **Visible at:** the [Sprints table view](https://github.com/orgs/iteam7/projects/1/views/3) and [GitHub sprint milestones](https://github.com/iteam7/gateway7/milestones), with the table's reported configuration described in [CONTRIBUTING.md](https://github.com/iteam7/gateway7/blob/main/CONTRIBUTING.md#project-views-and-scheduling).
- **Refinement:** the SPRINT-06/07 horizon retains the previously refined configured-access and offline-plugin candidates, [US-07](https://github.com/iteam7/gateway7/issues/36) at `3 SP` and [US-08](https://github.com/iteam7/gateway7/issues/37) at `5 SP`, and adds [US-13](https://github.com/iteam7/gateway7/issues/141) at `8 SP` for SPRINT-06 consideration on 30 October under [task #139](https://github.com/iteam7/gateway7/issues/139).
  Refinement stays in the issues through runnable criteria, dependencies, owning-specification links and native estimates; none exceeds `13 SP`, so this pass requires no split and produces no separate refinement document.
  US-13 remains a future candidate while its owning specification is prepared under task #139; that specification must resolve on `main` before the story is selected.
  The future candidates remain without a milestone, Responsible, Accountable or assignees until selected; a horizon is not a capacity commitment.
- **Scheduling gate:** actual selection sets the existing sprint milestone, two distinct native Responsible/Accountable values and exactly the same two assignees together, plus Priority for a task.
  The SPRINT-05 backlog preserves the carryover placement while the new US-12 selection and prospective US-05 estimate are recorded on 30 October; this update does not certify every legacy issue's fields.
- **Velocity check:** sum selected stories' native estimates by hand and distinguish the new remaining-scope forecast from the unavailable original commitment.
  At close, count only completed, Customer-accepted stories with recorded estimates and document actual rescheduling; absent historical estimates or acceptance evidence do not imply zero velocity.
- **Tracker reconciliation:** the 30 October pass checks the existing SPRINT-05 milestone, native estimates and the new story's scheduling against the plan; the legacy US-06 estimate and Customer verdicts remain unresolved historical evidence gaps.
  The Accountable reviewer checks the live tracker before accepting [task #138](https://github.com/iteam7/gateway7/issues/138); a local plan edit alone does not settle those gaps.
- **Release check:** verify the tag on `main`, changelog, Customer decisions and remaining work before closing a sprint; reschedule unresolved issues explicitly and protect published tags from movement and deletion.
