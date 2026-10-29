# Project plan

Corrected on 25 October 2026 under [task #95](https://github.com/iteam7/gateway7/issues/95), using the current tracker and the [SPRINT-04 retrospective](https://github.com/iteam7/gateway7/blob/main/reports/week-04/sprint-retrospective.md).
The correction records the work's current placement and the missing planning evidence; it does not reconstruct earlier team commitments.
Due dates follow [Assignment 4, Part 1](https://github.com/inno-itpd/itpd/blob/main/assignments/assignment-4.md#part-1-plan-the-sprint-refine-the-backlog-and-set-the-fields) and the [course syllabus](https://github.com/inno-itpd/itpd/blob/main/course/syllabus.md#3-weekly-curriculum--milestones): Weeks 4–9 are due on Saturday at 23:59, with no soft deadline.
The corrected SPRINT-04–09 dates below match the GitHub milestone due dates, updated and checked on 25 October.
The monitoring cadence and the unplanned sprint goals remain proposals for team review.

## Milestones

### MLS-03

- **Due:** 2026-10-17
- **Sprints:** [SPRINT-03](#sprint-03)
- **Advances:** [TOS-01](threshold-of-success.md#tos-01), [TOS-02](threshold-of-success.md#tos-02), [TOS-04](threshold-of-success.md#tos-04)

A client sends a chat request through a phone-masking plugin and receives an actual model's answer, with company plugins installable without changing the gateway core.
The candidate is [US-01](https://github.com/iteam7/gateway7/issues/30), [US-02](https://github.com/iteam7/gateway7/issues/31) and [US-03](https://github.com/iteam7/gateway7/issues/32), approved for building by [DEC-012](decisions.md#dec-012).
The deterministic upstream allowed by [DEC-011](decisions.md#dec-011) supports initial plugin checks; it does not replace US-01 AC-05 or the Customer's story verdicts.
The published release below is delivery evidence, not proof that the milestone's acceptance gates have all passed.

## Sprints

The backlog links open the GitHub milestones checked on 25 October, including the empty future milestones awaiting selection; these milestones remain open.
The available repository evidence supplies no pre-work story-point estimates or Customer acceptance verdicts for US-01–US-09.
The new estimates confirmed by azamatbayramov on 25 October concern remaining future verification and rework; they do not reconstruct earlier estimates or velocity.
Closed story issues therefore do not establish accepted completion or a measurable velocity under the [Definition of Done](definition-of-done.md#story).
The open candidates for the next two sprints have been returned to the unscheduled product backlog; legacy milestone placement does not establish that refinement or sprint planning happened.

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

Provisional goal: a reviewer can run the gateway through the documented delivery path and assess its chat and middleware behavior against the carried quality, architecture and story criteria.

- **Due:** 2026-10-31
- **Sprint Backlog:** [the issues assigned to SPRINT-05](https://github.com/iteam7/gateway7/milestone/3)
- **Planned Velocity:** N/A — missing; the available records supply no start-of-sprint planning result or confirmed estimates for the scheduled stories.

This is the current forecast for review, pending the team's goal and scope confirmation.
Actual Velocity is added when the sprint closes, using confirmed estimates and accepted-story evidence; the ongoing sprint has no final result yet.
All eight Assignment 4 carryover tasks created on 25 October remain assigned to SPRINT-05, as required by [task #95](https://github.com/iteam7/gateway7/issues/95); their placement is preserved while the planning and field gaps are corrected.
The [SPRINT-04 actions](https://github.com/iteam7/gateway7/blob/main/reports/week-04/sprint-retrospective.md#actions) call for planning, a Customer review before 31 October and the remaining Windows work.
Their completion needs evidence in the tracker and the current week's review records; the carried action does not itself move an issue or record a Customer verdict.

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
- **Refinement:** the two existing candidates for the SPRINT-06/07 horizon are in the [unscheduled product backlog](https://github.com/iteam7/gateway7/issues?q=is%3Aissue+is%3Aopen+no%3Amilestone), with their remaining scope, runnable acceptance criteria, dependencies and native `Story Points` confirmed by azamatbayramov on 25 October under [task #95](https://github.com/iteam7/gateway7/issues/95).
  Neither exceeds `13` points, so this pass needs no split; selection and capacity are assessed at actual sprint planning, not inferred from the two estimates.
  Refinement produces no separate document: the issue records hold its evidence.
  The public single-select field has options `1`, `2`, `3`, `5`, `8`, `13` and is temporarily pinned to untyped issues; [task #94](https://github.com/iteam7/gateway7/issues/94) completes the User Story type and its field pin without discarding these values.
- **Scheduling gate:** select refined work during actual sprint planning, set its milestone, two distinct native Responsible/Accountable values and the same two assignees, and set task Priority; the backlog link here points to that milestone.
  Future work remains without a milestone, role values or assignees until selected; the two open candidates for the next two sprints now meet that scheduling boundary.
  The eight current SPRINT-05 carryover tasks stay visible in that sprint while these corrections are reviewed.
- **Velocity check:** sum the selected stories' confirmed estimates by hand at planning, then sum only completed, Customer-accepted stories at sprint close and record any actual rescheduling.
  A missing historical planned total remains labelled missing; absent estimates or acceptance evidence do not imply zero velocity.
- **Tracker reconciliation:** milestone due dates, the eight SPRINT-05 carryover tasks and the two unscheduled future candidates' native estimates were checked on 25 October.
  The Accountable reviewer verifies this plan against that tracker state before accepting task #95; the remaining issue-type migration belongs to task #94.
- **Release check:** verify the tag on `main`, changelog, Customer decisions and remaining work before closing a sprint; reschedule unresolved issues explicitly and protect published tags from movement and deletion.
