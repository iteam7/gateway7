# Week 7 submission evidence addendum

On 20 November 2026, Team 7's public Gateway7 records were reconciled against the [Week 7 assignment](https://github.com/inno-itpd/itpd/blob/d7bcb1b24c142df8377da11ac5a1b4854e317fba/assignments/assignment-7.md#assignment-report-in-the-repository) for [#272](https://github.com/iteam7/gateway7/issues/272). This Week 8 addendum preserves the [archived Week 7 report](../week-07/README.md). The Week 7 deadline was 15 November 2026 at 23:59. The public evidence identifies a release and report. The submitted commit, private wrapper, instructor access and Moodle receipt remain unverified.

## Summary

The test was designed for backend developers who use an LLM API and a terminal and would evaluate a gateway for a small team. The plan targets at least three completed sessions with eligible adults, aiming for five. Sessions use staging from the university network, a synthetic provider and a reset seed. The intended screen and audio recordings need verified team-owned storage and instructor access. The custodian keeps raw text in the [private usability-data repository](https://github.com/iteam7/gateway7-usability-data). Automated link checking excludes this authenticated link under [the documented exception](../../.lycheeignore).

The [pilot and design review](../../docs/usability-tests/ut-01/README.md#pilot-and-customer-review) were reported successful. [DEC-022](../../docs/decisions.md#dec-022) records the decision to proceed with UT-01 in SPRINT-08. The supplied product-demo transcript excludes the separate design-review discussion and remains outside the public repository because publication permission is unverified. The existence or private delivery of a separate design-review transcript is unverified. No story-by-story Customer verdict appears in the supplied [review evidence](../week-07/meeting-report.md#previous-open-questions), and the minimum usable product candidate remains [US-01, US-02 and US-03](../../docs/decisions.md#dec-012).

The [analytics plan](../../docs/analytics.md) defines successful gateway tasks per week as the count of successful terminal task events after excluding smoke and usability-test traffic. The [Week 6 scope and readings](../week-06/README.md#dashboard-and-candidate-evidence) do not establish a measured value from regular production traffic. That requires successful eligible traffic and a verified production query. The [observability plan](../../docs/observability.md) owns the separate operating signals. See the [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan) for the rows that are not `Passes`.

## Usability test

UT-01 asks participants to send a first request and identify the masked data, recover after a denied model request, and run an offline middleware check. The test uses pre/post questions, one SEQ per task and SUS after the three tasks. [QR-06 QRT-01](../../docs/quality-requirements/qr/QR-06.md#qrt-01) requires a median main-task SEQ of at least five of seven across at least three counted sessions. The review and teammate pilot supply no counted-session results.

The [staging instrumentation](../../docs/analytics.md#the-usability-funnel) carries a server-owned participant code and request ID for the online tasks and excludes test traffic from product charts. The observer records the offline command's exit status locally. [PR #280](https://github.com/iteam7/gateway7/pull/280) merged the source and tests. The separate [staging verification and counted run](https://github.com/iteam7/gateway7/issues/300) still need evidence. Before the first counted session, the team must verify the intended staging run, linkage and filtering and [collect durable consent](../../docs/usability-tests/ut-01/consent.md) after the [access gates](../../docs/usability-tests/ut-01/README.md#access-and-arrangement-gates) pass. The Week 8 [results and triage task](https://github.com/iteam7/gateway7/issues/301) owns the sanitized results and the verdict.

## Coverage

| Deliverable | Public evidence or status |
| --- | --- |
| Sprint plan | [docs/project-plan.md#sprint-07](../../docs/project-plan.md#sprint-07) |
| UT-01 test record | [docs/usability-tests/ut-01/README.md](../../docs/usability-tests/ut-01/README.md) |
| Surveys and post-test | [docs/usability-tests/ut-01/surveys.md](../../docs/usability-tests/ut-01/surveys.md) |
| Tasks and protocol | [docs/usability-tests/ut-01/README.md#the-tasks](../../docs/usability-tests/ut-01/README.md#the-tasks) and [docs/usability-tests/ut-01/sessions/README.md](../../docs/usability-tests/ut-01/sessions/README.md) |
| Test instrumentation | [docs/usability-tests/ut-01/README.md#instrumentation](../../docs/usability-tests/ut-01/README.md#instrumentation) and [docs/analytics.md#the-events](../../docs/analytics.md#the-events) |
| Consent template | [docs/usability-tests/ut-01/consent.md](../../docs/usability-tests/ut-01/consent.md) |
| Private usability-data repository | [Authenticated text store](https://github.com/iteam7/gateway7-usability-data). Instructor read access is unverified. |
| Recordings folder | Private. Team ownership and instructor playback are unverified. |
| QR-06 and its test | [docs/quality-requirements/qr/QR-06.md](../../docs/quality-requirements/qr/QR-06.md) and [docs/quality-requirements/qr/QR-06.md#qrt-01](../../docs/quality-requirements/qr/QR-06.md#qrt-01) |
| Recruitment target and session plan | [docs/usability-tests/ut-01/README.md#participant-profile](../../docs/usability-tests/ut-01/README.md#participant-profile) and [docs/usability-tests/ut-01/README.md#schedule](../../docs/usability-tests/ut-01/README.md#schedule) |
| Week 8 handoff | [reports/week-07/README.md#usability-test](../week-07/README.md#usability-test) and [reports/week-07/README.md#week-8-handoff](../week-07/README.md#week-8-handoff) |
| Glossary | [docs/glossary.md](../../docs/glossary.md) |
| Risk register | [docs/risks.md](../../docs/risks.md) |
| Week 6 action points | [reports/week-07/meeting-report.md#previous-action-points](../week-07/meeting-report.md#previous-action-points) |
| Week 6 open questions | [reports/week-07/meeting-report.md#previous-open-questions](../week-07/meeting-report.md#previous-open-questions) |
| Sprint Review | [reports/week-07/meeting-report.md](../week-07/meeting-report.md) |
| Meeting script | [reports/week-07/meeting-script.md](../week-07/meeting-script.md) |
| Meeting transcript | The supplied product-demo transcript is private because publication permission is unverified. A separate design-review transcript is unverified. |
| REL-07 | [v0.4.0 release and tag](https://github.com/iteam7/gateway7/releases/tag/v0.4.0), [CHANGELOG.md#040---2026-11-14](../../CHANGELOG.md#040---2026-11-14) and [docs/project-plan.md#rel-07](../../docs/project-plan.md#rel-07) |
| Sprint retrospective | [reports/week-07/sprint-retrospective.md](../week-07/sprint-retrospective.md) |
| AI usage | [reports/week-07/ai-usage.md](../week-07/ai-usage.md) and [the Week 8 addendum disclosure](ai-usage.md#2026-11-20--task-272-week-7-submission-evidence-addendum) |

## Contributions and repository evidence

| GitHub username | Published evidence |
| --- | --- |
| azamatbayramov | Presented the gateway to Customer in [the recorded product demo](../week-07/meeting-report.md#metadata). |
| DeniBorsh | Authored the [UT-01 design](https://github.com/iteam7/gateway7/pull/275) and [pilot and Customer review record](https://github.com/iteam7/gateway7/pull/286) pull requests. |
| ExFuseMe | Authored the [REL-07 release and closeout](https://github.com/iteam7/gateway7/pull/287). |
| iceberkut | Authored the [consent and private-data preparation](https://github.com/iteam7/gateway7/pull/279) and [staging participant-code instrumentation](https://github.com/iteam7/gateway7/pull/280). |

[PR #287](https://github.com/iteam7/gateway7/pull/287) merged into main and closed [#271](https://github.com/iteam7/gateway7/issues/271). On 20 November, the latest green [link check](https://github.com/iteam7/gateway7/actions/runs/44746088723), [Markdown](https://github.com/iteam7/gateway7/actions/runs/44746088801), [workflow and actionlint](https://github.com/iteam7/gateway7/actions/runs/44746088759) and [Python](https://github.com/iteam7/gateway7/actions/runs/44746088835) checks ran on [the inspected main commit](https://github.com/iteam7/gateway7/commit/7b9832b51cdb1809325b190ace6f8b49ee138c2c).

## Deviations

The [archived report](../week-07/README.md#deviations) records that REL-06 was not released. The [plan](../../docs/project-plan.md#sprint-07) records that the counted sessions, results and verdict went to SPRINT-08 after the design, pilot and review work. QR-06 remains assigned to SPRINT-08, where the counted evidence is due. No additional SPRINT-07 testing-plan row move, failed recruitment outcome, refusal or instructor access failure was established from the sources reviewed. The SPRINT-07 tracker milestone is still open even though REL-07 was published.

## Submission status

The [archived report is available at the inspected full SHA](https://github.com/iteam7/gateway7/blob/7b9832b51cdb1809325b190ace6f8b49ee138c2c/reports/week-07/README.md). That is a verified source link for this audit. No evidence identifies it or another SHA as the actual Moodle submission checkpoint.

If the team has a Week 7 Moodle receipt, reconcile it privately with its PDF report permalink and the matching product ZIP. Check instructor access and the permitted review-recording or transcript evidence using the [Week 7 wrapper instructions](https://github.com/inno-itpd/itpd/blob/d7bcb1b24c142df8377da11ac5a1b4854e317fba/assignments/assignment-7.md#assignment-report-on-moodle). Any late submission must reflect the status Moodle actually permits and records. No private package or upload is confirmed by this addendum.

## Privacy

This addendum uses public evidence and includes no private-only material or participant identity. The privacy of any actual submission snapshot still needs verification.
