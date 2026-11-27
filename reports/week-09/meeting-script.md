# Sprint 9 review script

## Context

The Sprint 9 review is the in-person Customer meeting where the deployed increment is checked against the three user acceptance tests, the quality plan results are read out, the threshold goals the evidence can settle are settled, and the Customer says what the handoff must contain.
The Week 8 Customer Review did not take place, so its deferred UT-01 recommendations and the missing `REL-08` remain open and are raised here rather than in a meeting report that does not exist.
This is preparation, not evidence: the permission answers, the verdicts, the decisions and the action points are recorded in the meeting report after the meeting.

Before the meeting, name the moderator/timekeeper, the note taker and the observer by GitHub username, confirm the slot privately, and record the commit deployed to the university VM.

## Agenda

1. **Permissions, before recording (3 minutes).** Show: nothing.
   Ask questions 1–3 separately and record each answer.
   Start recording only after permission; an earlier meeting's permission does not carry over.
2. **Deployed build and UAT-01 (8 minutes).** Show: the deployed production instance reached from the university network and [UAT-01](../../docs/user-acceptance-tests.md#uat-01).
   The Customer sends the request, reads the answer and says what the masking shows.
   Ask question 4.
3. **UAT-02 (6 minutes).** Show: [UAT-02](../../docs/user-acceptance-tests.md#uat-02).
   The Customer sends the blocked message and reads the refusal.
   Ask question 5.
4. **UAT-03 (6 minutes).** Show: [UAT-03](../../docs/user-acceptance-tests.md#uat-03).
   The Customer sends both model requests and compares the refusal with the allowed answer.
   Ask question 6.
5. **Quality plan results (6 minutes).** Show: [the testing plan](../../docs/project-plan.md#quality-requirement-testing-plan) and the rows that are not `Passes`.
   Read each failed or unverified row and its planned sprint; do not restate the table.
   Ask question 7.
6. **Threshold goals (6 minutes).** Show: [the threshold of success](../../docs/threshold-of-success.md) with `TOS-01` and `TOS-02` still `Open`.
   Read each goal's existing measure and what the team can observe before the handoff.
   Ask question 8.
7. **Handoff expectations (7 minutes).** Show: the handoff rows the team drafted — deployment instructions, limitations, the Issues page and the private access values.
   Ask question 9.
8. **Read back decisions and action points (3 minutes).** Show: the note taker's provisional list.
   Read each decision, each action point, its owner and its exact due date aloud.
   Ask question 10.

Total: 45 minutes.
Each question is asked in exactly one agenda part.

## Questions

1. **[Not recorded]** May we record this meeting?
2. **[Not recorded]** May we publish a sanitized transcript in the public repository?
3. **[Not recorded]** If publication is refused, may we share the transcript privately with the course instructors?
4. **[Open]** Does the deployed build show the masking and redaction UAT-01 describes, and is the answer one a developer can interpret without asking the team?
5. **[Open]** UAT-02: is stopping a request that carries a blocked term the behavior the Customer expects, or should such a request be logged and answered instead?
6. **[Open]** UAT-03: is the model refusal clear enough to act on, and does the allowed-model answer arrive as expected?
7. **[Closed]** The Week 8 Customer Review did not happen: do the sanitized UT-01 results and their two deferred recommendations still reflect what the Customer wants carried into the handoff?
8. **[Open]** `TOS-01` and `TOS-02` are `Open`: what does the Customer accept as the measure that settles each before the handoff, and does any goal move or drop?
9. **[Open]** Which items must the handoff package contain beyond deployment instructions, the limitations, the Issues page and the private access values?
10. **[Closed]** Does this read-back state today's decisions, each action point with its owner and due date, and the remaining open questions exactly?

## Roles

- Moderator/timekeeper: **to confirm**; asks the questions, keeps each part inside its timebox and reserves the last three minutes for the read-back.
- Note taker: **to confirm**; records the permission answers, each UAT result with its runner, the decisions and the agreed owners and dates.
- Observer: **to confirm**; records omitted questions, untested claims, disagreements and identifying content before publication.

These are review roles, not the `UT-01` facilitator, observer and custodian appointments.
No attendance, permission answer, verdict or decision is claimed by this script.

## Key improvements

- **Before:** "Is the product good?" **After:** "UAT-02: is stopping a request that carries a blocked term the behavior you expect, or should such a request be logged and answered?" **Principle:** ask about a choice the answer changes, not for a judgement the team cannot act on.
- **Before:** "What do you want in the handoff?" **After:** "Which items must the handoff package contain beyond deployment instructions, the limitations, the Issues page and the private access values?" **Principle:** name the concrete items so the answer settles the package instead of restating it.
