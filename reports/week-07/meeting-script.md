# Week 7 Customer design-review script

## Context

Gateway7 lets developers send LLM requests through company policy plugins; this review must settle whether UT-01 tests a representative user's core workflow and agree the Week 8 execution plan, using demonstrated readiness rather than planned checks.
This is preparation for [#270](https://github.com/iteam7/gateway7/issues/270), not evidence of a scheduled or held meeting.
The [UT-01 design](../../docs/usability-tests/ut-01/README.md) documents the backend-developer profile, fixed scenarios, session roles, QR-06 measure/bar and SPRINT-08 run plan.
The non-counted pilot and Customer design review were reported as completed successfully; detailed observations and review feedback are absent from the supplied meeting transcript.
The 13 November product-demo transcript does not contain that UT-01 discussion or the individual permission answers.
Arrange a 30-minute live review with Customer; request 60 minutes if available.
Confirm the slot and roles privately before use.
The whole team attends.

## Agenda

1. **Permissions, before recording (3 minutes).** Show: nothing.
   Ask questions 1–3 separately and record each answer.
   Start recording only after permission; an earlier meeting's permission does not carry over.
2. **Working product and prior follow-ups (6 minutes).** Show: the production core request flow from the university network using its private submission address, and the [Week 6 report](https://github.com/iteam7/gateway7/blob/main/reports/week-06/README.md) and [confirmed retrospective actions](https://github.com/iteam7/gateway7/blob/main/reports/week-06/sprint-retrospective.md#actions).
   Ask question 4.
   Distinguish the tested deployed commit and actual outcomes from the unpromoted preview; never fill a failed demonstration with a claimed pass.
3. **UT-01 design and evidence gates (10 minutes).** Show: the [UT-01 record](../../docs/usability-tests/ut-01/README.md), [consent](../../docs/usability-tests/ut-01/consent.md), [session instructions](../../docs/usability-tests/ut-01/sessions/README.md), the [surveys](../../docs/usability-tests/ut-01/surveys.md) and [QR-06/QRT-01](../../docs/quality-requirements/qr/QR-06.md).
   Demonstrate the reset synthetic staging flow and actual instrumentation/store checks; show private access only through the private route.
   Ask questions 5–7.
   If a dependency is absent, state its current gap rather than presenting it as ready.
   A teammate pilot is non-counted and supplies no usability result or QR verdict.
4. **Execution window and unresolved decisions (8 minutes).** Show: [SPRINT-07–08 planning](../../docs/project-plan.md#sprint-07) and the [consent and private-data requirements](../../docs/usability-tests/ut-01/README.md#consent-and-data).
   Ask questions 8–10 before the closing read-back.
   Record actual agreements; proposals below are not assigned actions or agreed dates.
5. **Read back decisions and actions (3 minutes).** Show: the note taker's provisional decision/action list.
   Ask question 11.
   Read each owner and exact due date aloud; seek at least two genuinely agreed post-Week-7 actions, including one in Week 8.
   If agreement is absent, retain the open question instead of inventing an action.
   State the same-week design corrections to apply before release.
   Keep recording URLs, timecodes, credentials and real addresses out of public notes.

Total: 30 minutes.
Each question is asked in exactly one agenda part.
Preserve this script after the meeting; record actual feedback, permission answers and outcomes in the meeting report, with DEC entries only for actual decisions and a transcript when applicable.
The Week 6 report states that the formal analytics Customer Review did not occur; the supplied recordings are evidence of other product discussions, not a substitute for that review.
They do not establish a Week 6 assessment of all four dashboards, the SLI and test results, or the success threshold.
Use the source-backed follow-ups below in question 4, and carry earlier open questions from their actual [Week 5 report](https://github.com/iteam7/gateway7/blob/main/reports/week-05/meeting-report.md#open-questions).

## Earlier Customer feedback to reconcile

These are sanitized summaries of the supplied meeting recordings, not a Week 6 review report, permission record, Customer verdict, or agreed Week 7 action list.
No recording links, transcript text, participant data, personal names, or timecodes are included.

| Date | Source-backed feedback | What later evidence establishes | Review prompt |
| --- | --- | --- | --- |
| 23 October 2026 | Customer asked for clear install/run documentation, an easy way for a developer to add a plugin, and an explanation of how the gateway adds value beyond a hand-wired function chain; Customer also asked how a slow or failing plugin would be handled without stopping the gateway and how failures would be logged. | The supplied recordings do not establish that these requests were completed. | Ask which of these remains a blocker and request the exact behavior or evidence that would resolve it. |
| 6 November 2026 | Customer liked readable tests, asked for a clear testing goal, and suggested grouping scenarios under a user story with its context and issue link. The team said it would try this and show it next time. | No owner or due date was stated, and the later supplied recordings do not establish whether the test organization was changed. | Ask whether the grouped, explained scenarios were completed and where they can be reviewed; otherwise keep the follow-up open. |
| 7 November 2026 | Customer asked why the plugin system is better than a manually maintained function chain and how plugins are added, run, and diagnosed. The team said it would revisit how plugins are added and handled. | The 13 November recording shows a working OpenCode connection, an admin dashboard, and masking/blocking plugin examples. Customer still asked for a demonstration of adding a plugin. | Confirm whether the add-plugin demonstration and architectural explanation are now ready; do not infer completion from the other demonstrations. |

The supplied recordings do not establish the individual publication-permission answers or exact due dates for the earlier follow-ups.
The later owner-confirmed UT-01 decision and actions are recorded in the meeting report; keep the plugin-add demonstration open until Customer sees it.

## Questions

1. **[Not recorded]** May we record this meeting?
2. **[Not recorded]** May we publish a sanitized transcript in the public repository?
3. **[Not recorded]** If publication is refused, may we share the transcript privately with the course instructors?
4. **[Open]** From the production behavior just demonstrated and the unresolved earlier follow-ups, which concrete behavior still prevents you from accepting the core workflow, and what evidence would resolve it?
5. **[Open, priority]** Where does the proposed participant profile or fixed main/adjacent scenario sequence differ from the developer's real API/plugin workflow, and what must change before recruitment?
6. **[Open]** Do the predeclared outcomes, help/time rules, SEQ/SUS instruments, analysis statistic and QR-06 bar answer the research questions, or which specific criterion should change before counted data?
7. **[Open, priority]** Which demonstrated participant-code/event-linkage or private-access gap must be resolved before the first counted session, and what check would establish it?
   Explain coverage limits: server success is not human task completion, and server duration is not full time on task.
8. **[Open]** How should the team arrange at least three completed representative adult sessions, aiming for five, within the proposed SPRINT-07/08 window while preserving university-network access, reset synthetic staging data, durable consent and mandatory recording?
9. **[Closed, priority]** Can we agree the results submission in SPRINT-08, due 21 November 2026, with session work assigned to the sprint of the last counted session and a separate instrumentation verification before the first counted session, completed no later than the start of SPRINT-09 on 22 November?
   If not, record the changed arrangement and reason.
10. **[Open]** Which remaining earlier questions—blocking-plugin behavior/capacity, integration readiness, secret-storage choice and per-meeting transcript permissions—can be resolved now, and which must stay open with an agreed next check?
   Use the actual source questions rather than treating this list as evidence of a new commitment.
11. **[Closed]** Does this read-back accurately state today's decisions, same-week rework, remaining gaps and each agreed action's owner/due date, including the Week 8 execution arrangement?

## Roles

- Moderator/timekeeper: **TODO: team-confirmed GitHub username**; ask the questions and reserve the final three minutes for read-back.
- Note taker: **TODO: team-confirmed GitHub username**; capture exact permission answers, feedback, decisions and agreed action owners/dates.
- Observer: **TODO: team-confirmed GitHub username**; record omitted questions, untested readiness claims and disagreements, and flag identifying content before publication.

These are review roles, not the UT-01 session facilitator/observer/custodian appointments.
Issue assignees do not establish either allocation.
No roles or attendance are claimed confirmed by this script.

## Key improvements

Before: “Is our usability test good?” After: question 5 asks which participant/scenario mismatch must change before recruitment.
Principle: seek falsifiable criticism of the proposed workflow rather than a broad approval that cannot guide rework.

Before: “Can we test next week?” After: question 9 separates the results deadline, actual session-sprint boundary and pre-session verification gate.
Principle: obtain a concrete execution agreement without treating a calendar suggestion as verified readiness.
