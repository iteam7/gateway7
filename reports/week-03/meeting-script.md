# Week 03 customer-validation script

## Context

Prepared on 15 October for the contributor's planned 16 October 2026 customer call, Moscow time; the exact start time is not recorded here.
Gateway7 lets corporate IT add trusted policy plugins without changing the gateway core.
The Customer already permitted restart-based installation and a deterministic initial upstream ([DEC-010](../../docs/decisions.md#dec-010), [DEC-011](../../docs/decisions.md#dec-011)); Python is now selected by [DEC-013](../../docs/decisions.md#dec-013).
The [approved candidate](README.md#minimum-usable-product-candidate) remains US-01–03; an offline demonstration does not meet US-01 / AC-05.

Target: determine whether the running plugin workflow and demonstrated acceptance criteria meet the Customer's needs, and agree the remaining work toward the complete candidate.
Planned duration: 30 minutes; demonstration commands and expected evidence are in [docs/demo.md](../../docs/demo.md).
Assign the roles below and rehearse the commands before the call.

## Agenda

1. Permissions (2 minutes).
   Show: nothing; ask questions 1–3 before recording.
2. Previous commitments and architecture (4 minutes).
   Show: the [Week 2 actions and open questions](../week-02/meeting-report.md#action-points), the [seven-stage customer view](../../docs/architecture/README.md#customer-view), and the [Python decision](../../docs/decisions.md#dec-013).
   State that the architecture and technical prototype are now available to present; presentation itself is not a completed past action.
   Explain trusted modules, request/response lists and restart, then ask question 4.
3. US-01: gateway transport (4 minutes).
   Show: [US-01](https://github.com/iteam7/gateway7/issues/30) and the running [demo](../../docs/demo.md#rehearsal-and-live-demonstration).
   Inspect AC-01 fake answer, AC-02 verified configured key, AC-03 missing-setting startup failure, and AC-04 no-key-leak checks one at a time.
   Identify AC-05 as pending an actual Claude/Gemini `pong` call; ask question 5 without presenting US-01 as done.
4. US-02: policy over the conversation (4 minutes).
   Show: [US-02](https://github.com/iteam7/gateway7/issues/31), its three exact phone formats, the earlier-message record and the unchanged order/date record in the demo.
   Walk AC-01, AC-02 and AC-03, then ask questions 6–7.
5. US-03: company plugin installation (5 minutes).
   Show: [US-03](https://github.com/iteam7/gateway7/issues/32), the [plugin instructions](../../docs/plugins.md), and the demo's sample-file/configuration-only change evidence.
   Walk AC-01 sample marker after restart, AC-02 named missing plugin at startup, and AC-03 A-before-B order; also show disable/restart and the independent response order.
   Ask questions 8–9.
6. Remaining candidate and next work (8 minutes).
   Show: [criterion status](../../docs/demo.md#acceptance-checklist), [Week 3 coverage](README.md#coverage), and the [story backlog](https://github.com/iteam7/gateway7/issues?q=label%3Auser-story).
   Carry forward capacity measurement and secret-manager scope as open; do not ask again whether Python or restart is permitted.
   US-01 remains in the candidate unless the Customer explicitly changes scope; record any moved story as a new decision.
   Ask questions 10–11 and agree at least two concrete Week 4 actions with actual owners and due dates.
7. Read back (3 minutes).
   Show: the note taker's actual acceptance/rejection decisions, any failed AC identifiers, unresolved questions and agreed actions.
   Ask question 12; record the outcomes after the call rather than editing this script into a report.

## Questions

1. _(closed)_ May we record this meeting?
2. _(closed)_ May we publish a sanitized transcript in the public repository?
3. _(closed)_ If public publication is refused, may we share the transcript privately with instructors?
4. _(open, priority)_ When your team adds a policy module using this interface, which step or boundary would prevent it from working in your environment?
5. _(open)_ With the transport checks demonstrated and AC-05 still pending, what evidence is missing beyond the actual provider `pong` call before you can judge US-01?
6. _(open)_ Which phone formats or false-positive cases from your workflow must we add beyond the current synthetic US-02 fixtures?
7. _(closed)_ Do you accept or reject US-02 against AC-01–03 as demonstrated; if rejected, which criteria failed?
8. _(open, priority)_ What did you expect during the file/configuration/restart workflow that the demonstration did not show?
9. _(closed)_ Do you accept or reject US-03 against AC-01–03 as demonstrated; if rejected, which criteria failed?
10. _(open, priority)_ What must be completed first to judge the remaining candidate, and what should we build immediately after it?
11. _(open)_ Which expected plugin workload and deployment secret source should define the next capacity and configuration checks?
12. _(open)_ What is incorrect or missing in our read-back of story verdicts, remaining criteria, owners and Week 4 due dates?

## Roles

- Moderator: TODO, assign a GitHub username before the call.
- Note taker: TODO, assign a GitHub username before the call; record each story verdict and failed AC identifier.
- Observer/timekeeper: TODO, assign a GitHub username before the call; note skipped checks and objections.
- azamatbayramov has the evidenced presentation commitment from [Week 2](../week-02/meeting-report.md#action-points); that does not assign the three facilitation roles above.

## Key improvements

Before: "Does the architecture look good?"
After: "When your team adds a policy module using this interface, which step or boundary would prevent it from working in your environment?"
Principle: ask for an operational obstacle that can change the contract or installation workflow, rather than broad approval of a diagram.
