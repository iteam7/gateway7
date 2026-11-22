# Week 8 Customer Review script — UT-01 results

## Context

This is the sprint's Sprint Review and the week's Customer meeting, prepared for [#304](https://github.com/iteam7/gateway7/issues/304).
It is preparation, not evidence that the meeting happened: the feedback, the permission answers, the decisions and the action points are recorded in [the meeting report](meeting-report.md) after the meeting.

The subject is the sanitized `UT-01` evidence: three counted sessions, the results, the two findings and their triage, and the `QR-06` verdict.
The configuration evaluation is not presented at this meeting.

Before the meeting, name the moderator/timekeeper, the note taker and the observer by GitHub username, confirm the slot privately, and check that the production instance, the analytics dashboard and the observability dashboard are reachable from the university network.

## Agenda

1. **Permissions, before recording (3 minutes).** Show: nothing.
   Ask questions 1–3 separately and record each answer.
   Start recording only after permission; an earlier meeting's permission does not carry over.
2. **Working product (6 minutes).** Show: the deployed production instance from the university network, the analytics dashboard and the observability dashboard.
   Ask question 4.
   State the tested revision and what the dashboards show; never present an unverified deployment as verified.
3. **UT-01 results and verdict (12 minutes).** Show: [the results](../../docs/usability-tests/ut-01/results.md), the three [sanitized session notes](../../docs/usability-tests/ut-01/sessions/README.md) and the [`QR-06` row](../../docs/project-plan.md#quality-requirement-testing-plan).
   State the numbers plainly: three counted sessions, main task unaided 3/3, median SEQ 6 of 7, `QR-06 QRT-01` passes the predeclared bar of 5.
   Name the two `Minor` findings, the deferral of both recommendations, and the declared `P-02` room and device deviation.
   Say that the sample is three people and describes those sessions, not the wider population.
   Ask questions 5–7.
4. **Threshold and next steps (8 minutes).** Show: [the threshold of success](../../docs/threshold-of-success.md) and the deferred recommendations.
   State that `TOS-01` and `TOS-02` are still open and that no usability threshold goal exists to settle.
   Ask which deferred recommendation, if any, the Customer wants carried into SPRINT-09, and whether anything in the results needs a same-week correction.
   Ask questions 8–9 before the read-back.
5. **Read back decisions and action points (3 minutes).** Show: the note taker's provisional list.
   Read each decision, each action point, its owner and its exact due date aloud.
   Seek at least two actions due after Week 8, at least one of them in Week 9.
   If agreement is absent, keep the open question instead of inventing an action.
   Keep credentials, private addresses and participant identity out of the public notes.

Total: 30 minutes.
Each question is asked in exactly one agenda part.

## Questions

1. **[Not recorded]** May we record this meeting?
2. **[Not recorded]** May we publish a sanitized transcript in the public repository?
3. **[Not recorded]** If publication is refused, may we share the transcript privately with the course instructors?
4. **[Open]** Does the production instance and its two dashboards match what the Week 8 results describe, and what still has to be verified before the team calls a deployment done?
5. **[Open]** The first-request task succeeded unaided three times and the recovery task failed twice at the time limit: does that match the Customer's own experience of the developer workflow, and which of the two findings matters more to a real team?
6. **[Closed]** `QR-06 QRT-01` passes with a main-task median SEQ of 6 of 7 across three counted sessions; does the Customer accept that this result is about learnability on a first request and not about the whole product?
7. **[Open]** One counted session ran in a university dormitory on the participant's own laptop, declared as a deviation: does the Customer consider three sessions, including that one, enough for this week's evidence, or does the team need a further in-person session?
8. **[Open]** Which deferred recommendation should be carried into SPRINT-09: the pointer from the denial to the allowlist configuration, the offline-check guidance, or neither, and why?
9. **[Open]** Should anything in the results, the triage or the report be corrected before `REL-08` and the submission, given that both findings are `Minor` and no product change is claimed?
10. **[Closed]** Does this read-back accurately state today's decisions, the same-week rework, the remaining gaps and each agreed action's owner and due date?

## Previous action points

The Week 7 report's `## Action points` are read here with their outcome; the note taker records the actual result rather than assuming it.

| Action | Owner | Due | Outcome |
| --- | --- | --- | --- |
| Record and show a walkthrough of adding a plugin. | `azamatbayramov` | 2026-11-21, Week 8 | to record |
| Arrange the counted UT-01 sessions and deliver the results and QR-06 verdict with the Week 8 submission. | `DeniBorsh` | 2026-11-21, Week 8 | three sessions ran, the results are merged, and `QR-06` passes |

## Previous open questions

| Question | Answer |
| --- | --- |
| Does the plugin-add walkthrough resolve the remaining concern about how a developer installs and diagnoses a plugin? | to ask |
| What plugin-chain capacity and blocking behavior should the gateway support? | to ask |

## Roles

- Moderator/timekeeper: **to confirm**; asks the questions and reserves the final three minutes for the read-back.
- Note taker: **to confirm**; records the permission answers, the feedback, the decisions and the agreed owners and dates.
- Observer: **to confirm**; records omitted questions, untested claims and disagreements, and flags identifying content before publication.

These are review roles, not the `UT-01` facilitator, observer and custodian appointments.
Issue assignees do not establish either allocation.
No attendance, permission answer or decision is claimed by this script.
