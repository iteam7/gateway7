# Sprint 05 retrospective preparation

Prepared on 30 October 2026 from repository evidence and the [Customer meeting report](meeting-report.md), under [task #132](https://github.com/iteam7/gateway7/issues/132).
This is preparation for the team's retrospective, not a claim that the team has held or approved it.
`SPRINT-05` has not closed and its actual velocity is not established; the team must confirm the observations, causes and proposed actions at closeout before this becomes the final sprint record.

## What Went Well

| What went well |
| --- |
| Customer explicitly praised the monitoring and Docker Compose startup in the 30 October demonstration, which made outcomes and local startup easier to understand. |
| All five required workflows passed on [main commit b0b91399](https://github.com/iteam7/gateway7/commit/b0b91399f5c9c0eb5d285adbfce7d5f875c6192e), including [Python/Compose](https://github.com/iteam7/gateway7/actions/runs/41069175092) and [actionlint](https://github.com/iteam7/gateway7/actions/runs/41069174949). |
| The team produced [deployment instructions](../../docs/deployment.md), [feature documentation](../../docs/features.md) and implemented quality tests in [PR #151](https://github.com/iteam7/gateway7/pull/151), giving the release work concrete checks to reference. |
| [PR #154](https://github.com/iteam7/gateway7/pull/154) and [PR #155](https://github.com/iteam7/gateway7/pull/155) supplied non-overlapping product milestones and refined future stories while explicitly preserving the missing historical planning evidence. |

## What Did Not

These causes are evidence-based proposals for team review, not findings attributed to an unrecorded retrospective discussion.

| Problem | Root cause |
| --- | --- |
| OpenCode could not connect in the Customer demonstration because the gateway lacked the streaming contract it required. | The real harness connection was tried after the earlier component implementation, so its protocol requirements were discovered late; Customer identified this integration risk in the meeting. |
| The meeting produced useful feedback but no named story acceptance/rejection record. | The demonstration narrated the system without keeping the relevant issue wording and criteria in front of Customer, so there was no explicit verdict checkpoint. |
| Sprint closeout cannot yet establish velocity or final QRT results. | The start-of-sprint commitment is missing, the 30 October forecast is a later selection, and test-run evidence had not been transferred into the testing plan at this preparation checkpoint. |

## Actions

The first three rows retain the owners of unfinished Week 4 actions; revised scope and the fourth row are proposals for team confirmation.
`Carried: Yes` proposes tracking the action in the next retrospective; it does not claim the team already agreed to it.

| Action | Owner | Impact | Reason | Carried |
| --- | --- | --- | --- | --- |
| Hold planning at the start of SPRINT-06, setting the backlog milestone, both roles, matching assignees and planned velocity before implementation starts. | azamatbayramov | High | The carried SPRINT-05 planning action missed its start-of-sprint timing; a late forecast cannot reconstruct that commitment. | Yes |
| Complete the carried Customer review action with visible stories/criteria, actual verdict DECs and issue comments, using three or four substantial demonstration flows. | azamatbayramov | High | The 30 October meeting happened, but its narrative walkthrough did not produce the promised story verdict records. | Yes |
| Finish the remaining Windows checks and [PR #78](https://github.com/iteam7/gateway7/pull/78), keeping the already fixed deadline issue separate from the remaining CI work. | DeniBorsh | Medium | The carried Windows CI action remains open in [task #77](https://github.com/iteam7/gateway7/issues/77); the existing fix in [task #84](https://github.com/iteam7/gateway7/issues/84) is not evidence that the full Windows gate is green. | Yes |
| Put a real-harness smoke and collection of the tested commit, QRT result and deployment evidence into the preparation for the next Customer review. | azamatbayramov | High | The harness incompatibility and missing recorded test results were discovered separately from the feature walkthrough; checking the actual integration and its evidence earlier would expose both gaps. | Yes |

## Carried Actions

The Week 4 retrospective existed as a chat-based record even though the Week 4 Customer meeting did not happen.
Every action it marked `Carried: Yes` is accounted for below; no Week 4 Customer meeting is invented.

| Action | Outcome |
| --- | --- |
| [reports/week-04/sprint-retrospective.md#actions](../week-04/sprint-retrospective.md#actions): "Hold planning at the start of SPRINT-05, setting its backlog milestone, both roles, assignees and planned velocity." | **Not done:** the [SPRINT-05 plan](../../docs/project-plan.md#sprint-05) records a 30 October remaining-scope forecast and explicitly says the original commitment is unavailable; the next-sprint planning action is re-listed above. |
| [reports/week-04/sprint-retrospective.md#actions](../week-04/sprint-retrospective.md#actions): "Hold the Customer review before 31 October and walk each story's acceptance criteria one at a time, recording a DEC-nnn per verdict." | **Not done:** the meeting took place on 30 October, but no named story verdict was recorded; the remaining acceptance work is re-listed above. |
| [reports/week-04/sprint-retrospective.md#actions](../week-04/sprint-retrospective.md#actions): "Fix the two Windows test failures added in PR #90 and merge PR #78 before 31 October." | **Not done:** [PR #78](https://github.com/iteam7/gateway7/pull/78) remains draft and unmerged at this checkpoint; its remaining work is re-listed above without reimplementing the already merged deadline fix. |
