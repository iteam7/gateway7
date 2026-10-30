# Sprint 05 retrospective

- **Discussion:** Team 7 discussion reported by azamatbayramov on 2026-10-31 as held that day.
- **Confirmation:** the contributor confirmed the prepared observations, root causes and next actions in the [completion follow-up](meeting-follow-up.md#participants-and-team-records).
- **Sprint status:** Customer-accepted, currently estimated SPRINT-05 scope is `8 SP`; administrative closeout still needs the tracker carryover and verified release.

This file records the reported team discussion and its confirmed changes in working practice.
The original selected backlog and point total are still unrecorded; the late forecast is not substituted for them.

## What Went Well

| What went well |
| --- |
| Customer praised the monitoring and Docker Compose startup in the 30 October demonstration, making outcomes and local startup easier to understand. |
| All five required workflows passed on [main commit a15b1cd](https://github.com/iteam7/gateway7/commit/a15b1cd14618ee7b5ac423f4aed5ed2f496f405d), including [Python/Compose](https://github.com/iteam7/gateway7/actions/runs/41130602373) and [actionlint](https://github.com/iteam7/gateway7/actions/runs/41130602500). |
| The team produced [deployment instructions](../../docs/deployment.md), [feature documentation](../../docs/features.md) and implemented quality tests in [PR #151](https://github.com/iteam7/gateway7/pull/151), giving release work concrete checks to reference. |
| [PR #154](https://github.com/iteam7/gateway7/pull/154) and [PR #155](https://github.com/iteam7/gateway7/pull/155) supplied non-overlapping product milestones and refined future stories while preserving the distinction between original planning and the later recorded forecast. |

## What Did Not

The team confirmed these observations and causes; the later contributor confirmation supplies the story verdicts omitted from the initial meeting account.

| Problem | Root cause |
| --- | --- |
| OpenCode could not connect in the Customer demonstration because the gateway lacked the streaming contract it required. | The real harness connection was tried after the earlier component implementation, so its protocol requirements were discovered late. |
| The initial meeting account did not map the demonstration to named story verdicts. | The walkthrough narrated the system without keeping visible US/AC wording and a verdict checkpoint; later participant confirmation was needed to record which stories Customer accepted. |
| Sprint closeout lacks the original selected scope and complete declared QRT results. | The planning ceremony was reported, but its initial commitment was not preserved in the plan; test evidence was also transferred after implementation rather than alongside each check. |

## Actions

The contributor confirmed the owners, priorities and continuation of these actions for Week 6.
Planning is due before SPRINT-06 implementation; Review preparation and integration evidence must precede the next Review.
The three meeting follow-ups have a confirmed 6 November coordination date in the [follow-up plan](meeting-follow-up.md#confirmed-follow-up-plan).

| Action | Owner | Impact | Reason | Carried |
| --- | --- | --- | --- | --- |
| Hold planning at the start of SPRINT-06, recording the backlog milestone, both roles, matching assignees and planned velocity before implementation starts. | azamatbayramov | High | The earlier ceremony was reported but its original selected scope and point total cannot be recovered from the current plan; the next record must be complete when the commitment is made. | Yes |
| Use three or four substantial demonstration flows with visible stories/criteria, actual verdict DECs and issue comments at the next Customer Review. | azamatbayramov | High | Six story verdicts are now confirmed, but the earlier presentation and report did not make their acceptance mapping immediately visible. | No |
| Finish the remaining Windows checks and [PR #78](https://github.com/iteam7/gateway7/pull/78), keeping the already fixed deadline issue separate from the remaining CI work. | DeniBorsh | Medium | The carried Windows CI action remains open in [task #77](https://github.com/iteam7/gateway7/issues/77); the fix in [task #84](https://github.com/iteam7/gateway7/issues/84) does not establish the full Windows gate. | Yes |
| Put a real-harness smoke and collection of the tested commit, QRT result and deployment evidence into preparation for the next Customer Review. | azamatbayramov | High | Early integration checks and evidence collection would expose compatibility and verification gaps before the feature walkthrough. | Yes |

## Carried Actions

The Week 4 retrospective existed as a chat-based record even though the Week 4 Customer meeting did not happen.
Every action it marked `Carried: Yes` is accounted for below.

| Action | Outcome |
| --- | --- |
| [reports/week-04/sprint-retrospective.md#actions](../week-04/sprint-retrospective.md#actions): "Hold planning at the start of SPRINT-05, setting its backlog milestone, both roles, assignees and planned velocity." | **Not done:** the contributor confirms that planning happened, but the required original selection/point total and complete start-of-sprint record remain unavailable; the record-completeness action continues above. |
| [reports/week-04/sprint-retrospective.md#actions](../week-04/sprint-retrospective.md#actions): "Hold the Customer review before 31 October and walk each story's acceptance criteria one at a time, recording a DEC-nnn per verdict." | **Done:** the Review took place on 30 October and the contributor's 31 October confirmation now records the six accepted stories in [DEC-020](../../docs/decisions.md#dec-020); the presentation-format deviation remains in the original report, with the next Review's format an improvement above. |
| [reports/week-04/sprint-retrospective.md#actions](../week-04/sprint-retrospective.md#actions): "Fix the two Windows test failures added in PR #90 and merge PR #78 before 31 October." | **Not done:** [PR #78](https://github.com/iteam7/gateway7/pull/78) remains draft and unmerged; its remaining work continues above without reimplementing the merged deadline fix. |
