# Project plan

This plan records the existing candidate and release on 18 October 2026; it does not establish that sprint assignments were made before the Week 3 deadline.
Due dates follow the [course syllabus](https://github.com/inno-itpd/itpd/blob/main/course/syllabus.md#3-weekly-curriculum--milestones): Week 3 ends on Saturday, and Weeks 4–9 on Friday.
The monitoring cadence below is proposed for team review; later sprint goals remain provisional until planned.

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

### SPRINT-03

A clean checkout runs the candidate's chat flow, phone masking and configurable company plugin, with the real-provider criterion and each Customer verdict recorded against its story.

- **Due:** 2026-10-17

#### REL-03

Released as [v0.1.0](https://github.com/iteam7/gateway7/releases/tag/v0.1.0) on 2026-10-18.

### SPRINT-04

A company engineer can run three interacting plugins and follow the instructions to add another without core edits, while the team explains and demonstrates the selected execution and failure behavior.

- **Due:** 2026-10-23

The increment advances [TOS-03](threshold-of-success.md#tos-03) and responds to [DEC-014](decisions.md#dec-014) and [DEC-015](decisions.md#dec-015): justify the runner's design, make plugin failures diagnosable, and demonstrate composition beyond one masking plugin.
It includes an architecture-to-quality test plan and explicit Customer validation of the existing candidate; no story acceptance was recorded at the 16 October meeting.
This is proposed Week 4 scheduling of the requested follow-ups, not a Customer-agreed deadline or a silent move of unfinished stories out of [MLS-03](#mls-03).

#### REL-04

### SPRINT-05

Provisional goal: a reviewer completes the gateway's core chat flow on a deployed instance built and checked through the documented delivery pipeline.

- **Due:** 2026-10-30

#### REL-05

### SPRINT-06

Provisional goal: the team can assess gateway usage and failures from operational measurements without recording raw prompts, responses or provider secrets.

- **Due:** 2026-11-06

#### REL-06

### SPRINT-07

Provisional goal: a non-author can follow a repeatable usability protocol for installing a company plugin and completing the gateway's core request flow.

- **Due:** 2026-11-13

#### REL-07

### SPRINT-08

Provisional goal: a reviewer can reproduce a released gateway configuration and verify its dependency, secret and release controls from the documented baseline.

- **Due:** 2026-11-20

#### REL-08

### SPRINT-09

Provisional goal: the final gateway release demonstrates the agreed core task, with usability findings, Customer decisions and evidence for every threshold outcome ready for the final presentation.

- **Due:** 2026-11-27

#### REL-09

## Progress Monitoring

- **Review:** proposed team review every Thursday at 18:00 Europe/Moscow, before the soft deadline and separate from the Customer meeting; confirm this cadence in the PR review before treating it as a team agreement.
- **Checked by:** each scheduled issue's Responsible member presents implementation evidence, its distinct Accountable member checks the acceptance criteria, and the whole team compares the sprint goal with completed work and unresolved gates.
- **Review inputs:** read the [threshold of success](threshold-of-success.md) and [risk register](risks.md), review each trigger and response, and record outcomes in the artifact they change; a threshold change or candidate removal requires the Customer's recorded decision.
- **Visible at:** the [Sprints table view](https://github.com/orgs/iteam7/projects/1/views/3) and [GitHub sprint milestones](https://github.com/iteam7/gateway7/milestones), with the table's reported configuration described in [CONTRIBUTING.md](https://github.com/iteam7/gateway7/blob/main/CONTRIBUTING.md#project-views-and-scheduling).
- **Scheduling gate:** the team must put each scheduled task in its sprint milestone, set two distinct Responsible/Accountable values and the same two assignees, then add the sprint's `Sprint Backlog` link here; creating this file does not populate GitHub metadata or retrospectively establish SPRINT-03 planning.
- **Release check:** verify the tag on `main`, changelog, Customer decisions and remaining work before closing a sprint; reschedule unresolved issues explicitly and protect published tags from movement and deletion.
