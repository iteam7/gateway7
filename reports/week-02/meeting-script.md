# Week 02 validation script

## Context

**Follow-up planning script, revised 10 October 2026 after reviewing the supplied meeting transcript; not a reconstruction of the script used in that meeting.**
Initial preparation began on 8 October; the architectural redesign followed contributor-reported feedback on 9 October.
These are preparation dates, not verified meeting chronology.
Assign the roles and supply a usable prototype view before running this session.

Problem space: a corporate IT team needs a gateway where company-authored plugins control requests and responses without changing the gateway core.
The [kickoff report](../week-01/meeting-report.md) establishes the plugin-host direction and restart-based installation.
The [prototype record](prototypes.md) distinguishes the masking behavior shown in the meeting from the architecture simulator prepared afterwards.
The [meeting report](meeting-report.md) establishes revision requested, restart allowed and a deterministic upstream acceptable; the detailed interface remains to be validated. Candidate approval was reported separately by azamatbayramov and is recorded in [DEC-012](../../docs/decisions.md#dec-012).

Target: determine whether the proposed plugin lifecycle, product boundary, and three-story MUP candidate let a company add a policy plugin and complete one controlled request through a test upstream, and identify what must change.

## Agenda

1. Permission questions (2 minutes).
   Show: nothing; ask questions 1–3 before recording.
2. Previous action points and open questions (5 minutes).
   Show: [current action points](meeting-report.md#action-points) and [open questions](meeting-report.md#open-questions); ask question 4.
3. Architecture prototype (10 minutes, highest uncertainty).
   Show: the simulator described in [prototypes.md](prototypes.md), once an accessible view is available.
   Step through request and response hooks, register the sample plugin, compare draft and running configuration, restart, and inspect the new trace; ask questions 5–6.
4. Product boundary (4 minutes).
   Show: [product boundary](../../docs/product-vision.md#boundary) and [constraints](../../docs/product-vision.md#constraints); ask question 7.
5. Minimum usable product candidate (7 minutes).
   Show: [the candidate](README.md#minimum-usable-product-candidate).
   Proposed revised initial-demo task: start the system, add two simple plugins, restart if needed, send a request to a deterministic test upstream, and inspect the plugins' effects.
   The story bundle below has contributor-reported candidate approval in [DEC-012](../../docs/decisions.md#dec-012); use this follow-up to validate implementation details and the mapping to the deterministic initial demonstration, not to claim completed-story acceptance.
   Candidate only: [US-01](https://github.com/iteam7/gateway7/issues/30), [US-02](https://github.com/iteam7/gateway7/issues/31), [US-03](https://github.com/iteam7/gateway7/issues/32).
   Keep [all user stories and their MoSCoW labels](https://github.com/iteam7/gateway7/issues?q=label%3Auser-story) available so the Customer can move stories into or out of the candidate or change priorities; ask questions 8–9.
   Review individual acceptance criteria only if time remains.
6. Read back decisions and action points (2 minutes).
   Show: the note taker's actual decisions, candidate verdict, unresolved questions, and proposed owners/due dates inside Week 3; ask question 10.

## Questions

1. _(closed)_ May we record this meeting?
2. _(closed)_ May we publish a sanitized transcript in the public repository?
3. _(closed)_ If public publication is refused, may we share the transcript privately with instructors?
4. _(open)_ Which outcomes can we now confirm for the current actions and unresolved questions, including the next-presentation commitment, and what evidence supports each answer?
5. _(open, priority)_ Walk through adding a company plugin in this proposal: where would you expect to change a file, register it, configure it, and restart, and which step is missing or wrong?
6. _(open, priority)_ Looking at the request/response trace and block/error examples, which execution rule would prevent this architecture from working in your setting?
7. _(open)_ Which excluded responsibility or constraint in the boundary would prevent your team from completing the core task, and what should replace that boundary?
8. _(open, priority)_ How should US-01, US-02, and US-03 change to cover the requested two-plugin, deterministic-upstream demonstration, and what essential step is still missing?
9. _(closed)_ Does this implementation plan preserve the approved candidate while using a deterministic upstream for the initial demonstration?
10. _(open)_ What is incorrect or missing in our read-back of the decisions, exact candidate verdict, owners, and Week 3 due dates?

## Roles

- Moderator: TODO, assign a GitHub username before the session.
- Note taker: TODO, assign a GitHub username before the session.
- Observer/timekeeper: TODO, assign a GitHub username before the session; record skipped questions and unexplored objections.
- Attendance: invite the whole team; record actual attendance afterwards, not from this plan.

## Key improvements

Before: "Does the phone-masking prototype look right?"
After: "Walk through adding a company plugin in this proposal: where would you expect to change a file, register it, configure it, and restart, and which step is missing or wrong?"
The rewrite follows the reported architecture feedback and can expose an incorrect core/plugin boundary rather than solicit approval of a narrow masking screen.
