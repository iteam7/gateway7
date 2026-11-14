# Week 07 report — Gateway7

## Scope and findings

This report indexes the Week 7 usability-test design and the work in progress around it.
The design, the instrumentation, the consent handling and the Customer review are recorded, and `REL-07` `v0.4.0` is released; no usability result is claimed, and the results are due with Submission 8 on 21 November 2026.

## Usability test

The `UT-01` design is in [the record](../../docs/usability-tests/ut-01/README.md), with [the surveys](../../docs/usability-tests/ut-01/surveys.md), [the consent template](../../docs/usability-tests/ut-01/consent.md), [the session template](../../docs/usability-tests/ut-01/sessions/README.md) and [the results stub](../../docs/usability-tests/ut-01/results.md).
It carries the goal, the research questions, the participant profile, the recruitment target, the tasks, the surveys, the protocol, the instrumentation, the analysis plan and the evidence map.

The private usability-data repository and the consent handling are prepared under [#269](https://github.com/iteam7/gateway7/issues/269); the repository is private and its access instructions stay in the Moodle submission, and the team-owned recordings folder is still pending.
The test's instrumentation is merged under [#268](https://github.com/iteam7/gateway7/issues/268): the product metric recipes exclude `source=usability-test`, the staging events carry a server-owned participant code, and a session is read through its own filter and time window.

The non-counted teammate pilot and the Customer design review are recorded in [the meeting report](meeting-report.md) and [the record's pilot section](../../docs/usability-tests/ut-01/README.md#pilot-and-customer-review), with [DEC-022](../../docs/decisions.md#dec-022) agreeing the SPRINT-08 execution.

No counted session has run, no participant data is committed, and this report claims no usability result.

## Coverage

| Deliverable | Artifact |
| --- | --- |
| Sprint plan | [SPRINT-07](../../docs/project-plan.md#sprint-07) |
| `UT-01` test record | [docs/usability-tests/ut-01/README.md](../../docs/usability-tests/ut-01/README.md) |
| Surveys and post-test | [surveys.md](../../docs/usability-tests/ut-01/surveys.md) |
| Tasks and protocol | [the record](../../docs/usability-tests/ut-01/README.md#the-tasks) and [the session template](../../docs/usability-tests/ut-01/sessions/README.md) |
| Consent template | [consent.md](../../docs/usability-tests/ut-01/consent.md) |
| Private usability-data repository | the private `iteam7/gateway7-usability-data` repository; access stays in the Moodle submission |
| Test instrumentation | [the usability funnel](../../docs/analytics.md#the-usability-funnel) |
| Customer review and pilot | [meeting-report.md](meeting-report.md) |
| `QR-06` and its test | [QR-06](../../docs/quality-requirements/qr/QR-06.md) |
| `REL-07` | [v0.4.0](https://github.com/iteam7/gateway7/releases/tag/v0.4.0) and [the plan block](../../docs/project-plan.md#rel-07) |
| Sprint retrospective | [sprint-retrospective.md](sprint-retrospective.md) |
| AI usage | [ai-usage.md](ai-usage.md) |

## Deviations

`REL-06` was not released.
[The Week 6 report](../week-06/README.md) records that deviation, and `REL-07` is planned as the next appropriate version rather than a re-created `REL-06`.

## Privacy

No private-only material and no participant identity were committed to this repository.

## Week 8 handoff

The design, the recruitment target, the private repository, the recordings folder, the `QR/QRT` row and the `results.md` stub are handed to the run week once the #269 access checks are complete.
