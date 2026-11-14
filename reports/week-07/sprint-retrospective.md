# Sprint 07 retrospective

## What Went Well

- The `UT-01` design was merged and confirmed in [#275](https://github.com/iteam7/gateway7/pull/275), including `QR-06` and its manual test.
- The Customer review and the teammate pilot were recorded in [#270](https://github.com/iteam7/gateway7/issues/270) and [#286](https://github.com/iteam7/gateway7/pull/286), with [DEC-022](../../docs/decisions.md#dec-022) agreeing the SPRINT-08 execution.
- The instrumentation was implemented and merged in [#276](https://github.com/iteam7/gateway7/pull/276) and [#280](https://github.com/iteam7/gateway7/pull/280): the product metrics exclude `source=usability-test`, and staging events carry a server-owned participant code.

## What Did Not

- The design was first produced on the wrong owner and its draft pull request had to be withdrawn.
  Root cause: the Responsible and Accountable split was not checked before the work started.
- `REL-06` was never released, so the Week 7 release is `v0.4.0` rather than a `REL-06`/`REL-07` pair.
  Root cause: the Week 6 staging and production deployments were not promoted and verified.
- No counted usability session ran in Week 7.
  Root cause: the sessions are Week 8 work, and the staging store and participant link are not verified yet.

## Actions

| Action | Owner | Impact | Reason | Carried |
| --- | --- | --- | --- | --- |
| Run the counted sessions and record the results and `QR-06` verdict before Submission 8. | iceberkut | High | The results and verdict are due with Submission 8. | No |
| Verify the staging event store and the participant link before the first counted session. | ExFuseMe | High | The code is merged; the store and link are unverified. | No |
| Close Sprint 06 and reschedule #77 and #78 with their real state. | iceberkut | Medium | The stale milestone hides unfinished work. | No |
| Keep one editor for the Week 7 report and merge it before the submission snapshot. | ExFuseMe | Medium | The report pull request is still open. | No |

## Carried Actions

The [SPRINT-06 actions](../week-06/sprint-retrospective.md#actions) are quoted here with their outcome.

| Action | Outcome |
| --- | --- |
| Record selected stories, estimates and roles before implementation. | Not done: the SPRINT-07 goal remained proposed, and the selected work is a dated tracker audit rather than an agreed plan. |
| Finish the assessment of [task #77](https://github.com/iteam7/gateway7/issues/77) and [draft PR #78](https://github.com/iteam7/gateway7/pull/78), and retain the Windows/Linux check results. | Not done: both remain open. |
| Before a demonstration, check the real provider and OpenCode, and retain the tested commit SHA and results. | Not done: the 13 November demonstration recorded a failed provider attempt. |
| Organize collection of the shared report through one editor. | Not done: the Week 7 report is still an open pull request. |
