# Week 05 Customer Review script

## Context

Prepared on 25 October 2026; no date, time or Customer attendance has been agreed yet (TODO: record the real arrangement once the team schedules it; SPRINT-05 is due on 31 October).
Gateway7 lets corporate IT route developers' model requests through company policy plugins without changing the gateway core.
The team believes the pilot from [PR #90](https://github.com/iteam7/gateway7/pull/90) implements US-01–US-09 against a synthetic upstream, but no story has a Customer verdict and US-01 / AC-05 has never run against a real provider.
**The Week 4 review did not take place**: there is no Week 4 meeting report, so the [Week 3 action points](../week-03/meeting-report.md#action-points) and [open questions](../week-03/meeting-report.md#open-questions) are still unanswered and are put to the Customer here.
The [evidence matrix](../../docs/demo.md#acceptance-checklist) separates automated (mock) checks from criteria that need a dry-run, a live provider or a Customer verdict; nothing marked as still needed is presented as passed.
Before the call, the Accountable reviewer dry-runs `uv run --locked pytest -q` and `uv run --locked python -m demo.run` and the matrix's dry-run rows (TODO: record date and result).

Target: decide which of US-01–US-09 the Customer accepts against their unchanged acceptance criteria, and what the deployed SPRINT-05 increment must show next.
Planned duration: 30 minutes; ask for 60 and, if granted, double the story parts 3–5.

## Agenda

1. Permissions (3 minutes).
   Show: nothing; ask questions 1–4 before recording.
2. Missing Week 4 review and Week 3 carry-over (4 minutes).
   Show: the [Week 3 action points](../week-03/meeting-report.md#action-points) and [open questions](../week-03/meeting-report.md#open-questions), and the [Python workflow](https://github.com/iteam7/gateway7/actions/workflows/python.yml) for the carried infrastructure action.
   State that the Week 4 review did not happen; ask questions 6–8.
   The Week 3 question on follow-up owners and dates is the team's own and is settled in the read-back.
3. US-01–US-03: the candidate from DEC-012 (7 minutes).
   Show: `uv run --locked python -m demo.run` and `config/demo.yaml`; walk US-01 AC-01–AC-04, US-02 AC-01–AC-03 and US-03 AC-01–AC-03 one at a time against the [matrix](../../docs/demo.md#acceptance-checklist).
   State that US-01 / AC-05 is not met and US-01 stays open; ask questions 9–10.
4. US-04–US-06: policy actions, response check and plugin failures (5 minutes).
   Show: the [interactive pilot](../../docs/demo.md#interactive-pilot-and-monitoring) for US-04 AC-01, then the demo's composition and failure traces for US-06 AC-01–AC-04; show US-04 AC-02 and US-05 AC-01–AC-02 only if the dry-run produced them with the exact fixtures.
   State the known gaps as not met: the client errors in US-04 AC-01 and US-06 AC-01 do not name the plugin, and US-04 AC-03 startup output does not name `explode`.
   Ask questions 5 and 11.
5. US-07–US-09: client access, offline check and plugin authoring (4 minutes).
   Show: wrong token, forbidden model and the [offline plugin test](../../docs/authoring.md) for US-07 AC-01–AC-02 and US-08 AC-01–AC-02; show US-09 AC-02–AC-03 only with dry-run or non-author evidence.
   State that US-09 AC-01 is not met: the instructions contain no `[example-plugin]` example.
   Ask question 12.
6. Quality requirements and architecture against the drivers (3 minutes).
   Show: the proposed requirements in [PR #101](https://github.com/iteam7/gateway7/pull/101) and containers in [PR #99](https://github.com/iteam7/gateway7/pull/99), presented as unmerged proposals.
   Ask question 13.
7. Next increment (2 minutes).
   Show: [SPRINT-05](../../docs/project-plan.md#sprint-05).
   Ask question 14.
8. Read back (2 minutes).
   Show: the note taker's verdicts per story with failed `AC-nn`, open questions, and at least two actions with owners and Week 6 dates.
   Ask question 15.

## Questions

1. _(closed)_ May we record this meeting?
2. _(closed)_ May we publish a sanitized transcript in the public repository?
3. _(closed)_ If public publication is refused, may we share the transcript privately with instructors?
4. _(closed)_ For the 16 October meeting, may we publish its sanitized transcript in the repository, or share it only privately with instructors?
5. _(open, priority)_ After seeing three plugins compose and fail with traces, what do you still need to diagnose a failed or hanging plugin under DEC-014 and DEC-015?
6. _(closed)_ Do the checks in the Python workflow complete the infrastructure action carried from Week 1; if not, what is missing?
7. _(open)_ Which plugin chain and request load from your environment should define the capacity check?
8. _(closed)_ Should deployment provider keys come from server configuration or from an external secret manager?
9. _(open, priority)_ Which authorized Claude or Gemini account may we use for US-01 / AC-05, and who covers the cost of that call?
10. _(closed)_ Do you accept or reject US-02 and US-03 against their AC as demonstrated; if rejected, which AC failed?
11. _(closed)_ Do you accept or reject US-04, US-05 and US-06 against their AC as demonstrated; if rejected, which AC failed?
12. _(closed)_ Do you accept or reject US-07, US-08 and US-09 against their AC as demonstrated; if rejected, which AC failed?
13. _(open, priority)_ Which proposed quality scenario sets a threshold you would not accept in operation, and what should it be?
14. _(open)_ On the deployed SPRINT-05 instance, what must a reviewer be able to do first?
15. _(open)_ What is incorrect or missing in our read-back of verdicts, owners and dates?

## Roles

- Moderator: TODO, assign a GitHub username before the call.
- Note taker: TODO, assign a GitHub username before the call; record each story verdict and failed `AC-nn`.
- Observer: TODO, assign a GitHub username before the call; note skipped checks and unasked questions.

## Key improvements

Before: "Is it fine if we show AC-05 with the fake upstream?"
After: "Which authorized Claude or Gemini account may we use for US-01 / AC-05, and who covers the cost of that call?"
Principle: ask for the missing evidence itself instead of permission to substitute it, so the answer unblocks the criterion rather than weakening it.
