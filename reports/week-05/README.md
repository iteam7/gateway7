# Week 05 report

## Project and status

Gateway7 is Team 7's Modular LLM Gateway: company policy middleware checks developers' model requests and answers while provider credentials stay on the server.
Prepared on 30 October 2026 for [Assignment 5](https://github.com/inno-itpd/itpd/blob/0173b82dfb82e515457a1074970c116760490c79/assignments/assignment-5.md), due 31 October at 23:59.
This is an evidence checkpoint; REL-05, sprint closeout and the final Moodle submission are outstanding.

## Summary

The increment adds proxy transports, simpler OpenAI startup, middleware diagnostics and guarded OpenCode function-tool turns, alongside the deployment runbook, feature guide and automated quality checks.
The [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan) records the verified CI results and keeps the scripted Windows/Linux and deployed staging checks unverified where their required evidence is missing.
All five required workflows passed on [main commit b0b91399](https://github.com/iteam7/gateway7/commit/b0b91399f5c9c0eb5d285adbfce7d5f875c6192e).
All five product checks apply to this Python stack: formatting, linting, type checking, automated tests and build; none is marked not applicable.

[PR #147](https://github.com/iteam7/gateway7/pull/147) records separate staging and production deployments on the university VM at commit `26dab3122dbc2f4247533d0c57cdb0f83e5073cf`, with health and synthetic-provider chat checks on both.
The latest increment still needs promotion and verification on one final commit; the older deployment does not establish its state.
The [plan](../../docs/project-plan.md#milestones) adds MLS-05 for observable plugin behavior and MLS-07 for repeatable plugin checks and usage visibility, with separate sprint runs.
The late SPRINT-05 forecast is 8 SP; the original sprint commitment remains unavailable.
Actual velocity, explicit unfinished-work moves and milestone closure await genuine review and closeout records.
[REL-05](../../docs/project-plan.md#rel-05) has not been cut; the [release preparation](release-preparation.md) names its remaining gates.

## Customer validation

The [30 October meeting report](meeting-report.md) records the local demonstration, positive monitoring and startup feedback, early harness integration guidance and the promised blocking-plugin investigation.
The meeting did not identify and settle individual story verdicts: no implemented US is reported as accepted or rejected, and no acceptance DEC is inferred from general praise.
[DEC-017, DEC-018 and DEC-019](meeting-report.md#decisions) record integration and validation direction instead.
The next demonstration will group the exact stories and criteria into three or four substantial use cases and request real verdicts.
Identified QRT results were not presented in the supplied meeting record; the later CI evidence is recorded at its actual level and date.

The minimum usable product candidate remains [US-01](https://github.com/iteam7/gateway7/issues/30), [US-02](https://github.com/iteam7/gateway7/issues/31) and [US-03](https://github.com/iteam7/gateway7/issues/32), selected under [DEC-012](../../docs/decisions.md#dec-012).
US-01 AC-05 still names Claude/Gemini; the OpenAI demonstration did not agree a change to that criterion.
Closed story issues supply no missing Customer verdict.

## Coverage

| Deliverable | Artifact and current state |
| --- | --- |
| Sprint plan and milestones | [docs/project-plan.md#sprint-05](../../docs/project-plan.md#sprint-05) and [docs/project-plan.md#milestones](../../docs/project-plan.md#milestones): current scope and two product milestones; original commitment and actual velocity remain unresolved. |
| New stories | [User Story issue list](https://github.com/iteam7/gateway7/issues?q=is%3Aissue%20type%3A%22User%20Story%22), [US-12](https://github.com/iteam7/gateway7/issues/140) in [SPRINT-05](https://github.com/iteam7/gateway7/milestone/3), and unscheduled [US-13](https://github.com/iteam7/gateway7/issues/141); post-merge specification-link check remains with [task #139](https://github.com/iteam7/gateway7/issues/139). |
| Quality requirement tests | [docs/quality-requirements/README.md](../../docs/quality-requirements/README.md): every active High requirement has a QRT in its linked requirement file. |
| Testing plan | [docs/project-plan.md#quality-requirement-testing-plan](../../docs/project-plan.md#quality-requirement-testing-plan). |
| Automated tests and CI | [.github/workflows/](../../.github/workflows/): green main [Python/Compose](https://github.com/iteam7/gateway7/actions/runs/41069175092), [actionlint](https://github.com/iteam7/gateway7/actions/runs/41069174949), [Markdown](https://github.com/iteam7/gateway7/actions/runs/41069175006), [links](https://github.com/iteam7/gateway7/actions/runs/41069174973) and [documentation](https://github.com/iteam7/gateway7/actions/runs/41069174946). |
| Deployment | [docs/deployment.md](../../docs/deployment.md) and [PR #147 verification](https://github.com/iteam7/gateway7/pull/147); final-candidate staging/QRT/production evidence remains open. |
| Feature documentation | [docs/features.md](../../docs/features.md). |
| Week 4 action points | [reports/week-05/meeting-report.md#previous-action-points](meeting-report.md#previous-action-points): no Week 4 meeting occurred; the report follows the real Week 3 carryover. |
| Week 4 open questions | [reports/week-05/meeting-report.md#previous-open-questions](meeting-report.md#previous-open-questions): answered and unresolved carryover are distinguished. |
| Meeting script | [reports/week-05/meeting-script.md](meeting-script.md): preserved pre-meeting preparation, including its unfilled arrangements and stale assumptions. |
| Meeting transcript | No public transcript: publication and private instructor-sharing permissions are unconfirmed; see [reports/week-05/meeting-report.md#metadata](meeting-report.md#metadata). |
| Customer validation | [reports/week-05/meeting-report.md](meeting-report.md): factual feedback and direction recorded; individual story verdicts remain outstanding. |
| REL-05 | [docs/project-plan.md#rel-05](../../docs/project-plan.md#rel-05) remains unfilled; [reports/week-05/release-preparation.md](release-preparation.md) carries the unpublished body draft and remaining gates. |
| Sprint retrospective | [reports/week-05/sprint-retrospective.md](sprint-retrospective.md): evidence-based preparation with all Week 4 carried actions, awaiting the team's real retrospective and confirmation. |
| AI usage | [reports/week-05/ai-usage.md](ai-usage.md): tools and handling recorded; human accepted/changed/rejected assessments remain pending. |

## Contributions

These links identify delivered work; they do not assess an individual's performance.

| GitHub member | Repository evidence |
| --- | --- |
| azamatbayramov | [Proxy transport #144](https://github.com/iteam7/gateway7/pull/144), [live smoke #146](https://github.com/iteam7/gateway7/pull/146), [OpenAI environment setup #149](https://github.com/iteam7/gateway7/pull/149), [middleware diagnostics #131](https://github.com/iteam7/gateway7/pull/131), [guarded OpenCode turns #156](https://github.com/iteam7/gateway7/pull/156), and the Customer demonstration. |
| ExFuseMe | [Deployment runbook and verification #147](https://github.com/iteam7/gateway7/pull/147), [actionlint and Definition of Done #150](https://github.com/iteam7/gateway7/pull/150). |
| DeniBorsh | [Quality tests #151](https://github.com/iteam7/gateway7/pull/151), [features and testing-plan structure #152](https://github.com/iteam7/gateway7/pull/152). |
| iceberkut | [Sprint plan and milestones #154](https://github.com/iteam7/gateway7/pull/154), [new-story refinement and usage specification #155](https://github.com/iteam7/gateway7/pull/155). |

Merged [PR #151](https://github.com/iteam7/gateway7/pull/151) closed [task #136](https://github.com/iteam7/gateway7/issues/136); its implementation and the later main CI are distinct from the results recorded in this checkpoint.
The task's closure does not establish the unverified scripted or staging results.

## Deviations

- Planning was updated on 30 October after implementation; its remaining-scope forecast cannot reconstruct the missing start-of-sprint commitment.
- No Week 4 Customer meeting occurred; the Week 5 report follows the actual Week 3 actions and keeps the Week 4 retrospective's separate carried actions.
- The 30 October demonstration ran locally because the presenter was outside the university network; VM unavailability and an exemption from production review are not established.
- No individual story verdicts or identified QRT review were captured; request the missing decisions instead of backdating acceptance or checks.
- Transcript publication and private instructor-sharing permissions remain unconfirmed; no transcript source is committed.
- The scripted cross-platform and deployed checks retain their unverified results until their declared procedures are evidenced.
- The real retrospective, human AI assessments, final deployment, release, issue rescheduling and private submission remain open; the preparation records do not claim them completed or deferred to an agreed sprint.

## Privacy

No private-only material was committed to the repository.
