# Week 05 report

## Project and status

Gateway7 is Team 7's Modular LLM Gateway: company policy middleware checks developers' model requests and answers while provider credentials stay on the server.
Updated on 31 October 2026 for [Assignment 5](https://github.com/inno-itpd/itpd/blob/0173b82dfb82e515457a1074970c116760490c79/assignments/assignment-5.md), due 31 October at 23:59.
The contributor has confirmed six accepted stories, the team retrospective, human review of AI output and successful OpenAI core checks on the matching staging and production commit.
[v0.3.0](https://github.com/iteam7/gateway7/releases/tag/v0.3.0) was published on 31 October at the contributor-confirmed production commit.
The final private PDF and ZIP must identify one common merged report SHA; release publication is not a claim that Moodle upload or the remaining deployment work has been completed.

## Summary

The increment adds proxy transports, simpler OpenAI startup, middleware diagnostics and guarded OpenCode function-tool turns, alongside the deployment runbook, feature guide and automated quality checks.
The [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan) records two passing CI QRTs at main commit `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`.
The latest workflows on main commit `6d3555247bfe8007a9963b14394434643dde0652` all passed: [Python/Compose](https://github.com/iteam7/gateway7/actions/runs/41193629449), [actionlint](https://github.com/iteam7/gateway7/actions/runs/41193629559), [Markdown](https://github.com/iteam7/gateway7/actions/runs/41193629474), [links](https://github.com/iteam7/gateway7/actions/runs/41193629487), [documentation](https://github.com/iteam7/gateway7/actions/runs/41193629440) and [native reliability](https://github.com/iteam7/gateway7/actions/runs/41193629459).
Formatting, linting, type checking, automated tests and build all apply to this Python stack.
After PR #162 merged, [native Windows/Linux reliability CI](quality-checks.md#qr-01-native-ci-execution-on-31-october) passed all four failure cases 50 times per operating system at main commit `6d3555247bfe8007a9963b14394434643dde0652`, with zero upstream requests.
QR-01 QRT-01 now runs at CI level with the original pass criterion, bringing the testing plan to three passing CI QRTs; the earlier [Linux-only run](quality-checks.md#qr-01-linux-execution) remains a separate historical record.
The contributor also explicitly reports `PASS QR-03 QRT-02` on staging and confirms that the run used the same deployed `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d` revision.
Its [operator record](quality-checks.md#staging-check) distinguishes that reported result from captured CI output; all four QRT rows now have passing results at their stated levels.

The [later 31 October confirmation](meeting-follow-up.md#later-deployment-and-private-submission-confirmation) identifies `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d` in both OpenAI environments and reports successful health, readiness and chat checks.
The [core-check record](quality-checks.md#reported-vm-core-verification) distinguishes those contributor-reported results from automated QRTs and the older synthetic-provider [PR #147](https://github.com/iteam7/gateway7/pull/147).
The deployment currently requires SSH and port forwarding; direct HTTP access from the university network remains an unmet requirement, recorded below as a deviation rather than an unavailable-VM exception.
The [plan](../../docs/project-plan.md#milestones) contains MLS-05 and MLS-07 with separate sprint runs.
The known estimated selected SPRINT-05 scope is `8 SP`, US-05 `3` + US-12 `5`, and both stories are accepted under DEC-020.
The contributor confirms that initial planning happened, but the original selection and point total remain unrecorded; the late forecast is not that historical commitment.
The remaining open SPRINT-05 tasks, [#138](https://github.com/iteam7/gateway7/issues/138) and [#139](https://github.com/iteam7/gateway7/issues/139), were moved to SPRINT-06 on 31 October with their fields preserved.
SPRINT-05 has zero open issues but remains open because automated approval review prevented its close action; this separate administrative checkpoint does not undo the published release.
[REL-05](../../docs/project-plan.md#rel-05) records the published tag and checked requirements; the [publication checkpoint](release-preparation.md#publication-checkpoint) records its fixed runtime target and the resolved initial approval-review event.

## Customer validation

The [30 October meeting report](meeting-report.md) remains unchanged as the account written from the supplied recording.
The [31 October participant confirmation](meeting-follow-up.md#customer-verdicts) supplies the named acceptance missing from that initial account: **US-01, US-02, US-03, US-04, US-05 and US-12**, recorded together in [DEC-020](../../docs/decisions.md#dec-020).
No verdict is inferred for US-06, which the contributor did not name.
[DEC-021](../../docs/decisions.md#dec-021) records that OpenAI was shown and acceptable to Customer for US-01; the exact unclarified error criteria remain visible in the follow-up.
The minimum usable product candidate, US-01–US-03 selected under [DEC-012](../../docs/decisions.md#dec-012), now has reported implemented-story acceptance under DEC-020.

Customer praised monitoring and Compose, requested early integration and suggested three or four substantial use cases for the next demonstration.
The blocking-plugin investigation is tracked in [#157](https://github.com/iteam7/gateway7/issues/157).
The contributor confirmed three Week 6 follow-ups, with owners and 6 November dates, in [the follow-up plan](meeting-follow-up.md#confirmed-follow-up-plan).
Identified QRT results were not presented in the supplied meeting record; checks performed later are recorded at their actual level and date in [quality evidence](quality-checks.md).

## Coverage

| Deliverable | Artifact and current state |
| --- | --- |
| Sprint plan and milestones | [docs/project-plan.md#sprint-05](../../docs/project-plan.md#sprint-05) and [docs/project-plan.md#milestones](../../docs/project-plan.md#milestones): two product milestones, reported planning and the known `8 SP` accepted selected scope; the original numerical commitment is missing; tasks #138/#139 were moved to SPRINT-06, and the empty SPRINT-05 milestone remains open after the close-action review refusal. |
| New stories | [US-12](https://github.com/iteam7/gateway7/issues/140), selected into [SPRINT-05](https://github.com/iteam7/gateway7/milestone/3) and now reported accepted; [US-13](https://github.com/iteam7/gateway7/issues/141), refined and unscheduled, owns [docs/functional-requirements/fr/FR-012.md](../../docs/functional-requirements/fr/FR-012.md); [#139](https://github.com/iteam7/gateway7/issues/139) checks its issue-link completion. |
| Quality requirement tests | [docs/quality-requirements/README.md](../../docs/quality-requirements/README.md): every active High requirement has its declared test in the linked requirement file. |
| Testing plan | [docs/project-plan.md#quality-requirement-testing-plan](../../docs/project-plan.md#quality-requirement-testing-plan) and [reports/week-05/quality-checks.md](quality-checks.md): three CI passes including native Windows/Linux reliability, plus the operator-reported staging PASS at the explicitly confirmed deployed revision. |
| Automated tests and CI | [.github/workflows/](../../.github/workflows/): all six current workflows passed on the main commit linked in the summary. |
| Deployment | [docs/deployment.md](../../docs/deployment.md), the [reports/week-05/meeting-follow-up.md#later-deployment-and-private-submission-confirmation](meeting-follow-up.md#later-deployment-and-private-submission-confirmation) and [reports/week-05/quality-checks.md#reported-vm-core-verification](quality-checks.md#reported-vm-core-verification); SSH-only access still fails the direct campus-HTTP requirement. |
| Feature documentation | [docs/features.md](../../docs/features.md). |
| Week 4 action points | [reports/week-05/meeting-report.md#previous-action-points](meeting-report.md#previous-action-points) follow the real Week 3 carryover because no Week 4 Customer meeting took place; the [reports/week-05/meeting-follow-up.md#confirmed-follow-up-plan](meeting-follow-up.md#confirmed-follow-up-plan) supply next actions. |
| Week 4 open questions | [reports/week-05/meeting-report.md#previous-open-questions](meeting-report.md#previous-open-questions) and [reports/week-05/meeting-follow-up.md#requirement-clarification](meeting-follow-up.md#requirement-clarification) distinguish the resolved story/provider questions from unanswered capacity, secrets and execution questions. |
| Meeting script | [reports/week-05/meeting-script.md](meeting-script.md), preserved with its original unfilled arrangements rather than rewritten after the meeting. |
| Meeting transcript | Private-only PDF appendix under the [reports/week-05/meeting-follow-up.md#later-deployment-and-private-submission-confirmation](meeting-follow-up.md#later-deployment-and-private-submission-confirmation); no public transcript or private access information is committed. |
| Customer validation | [reports/week-05/meeting-report.md](meeting-report.md) plus [reports/week-05/meeting-follow-up.md#customer-verdicts](meeting-follow-up.md#customer-verdicts), [docs/decisions.md#dec-020](../../docs/decisions.md#dec-020) and [docs/decisions.md#dec-021](../../docs/decisions.md#dec-021). |
| REL-05 | [docs/project-plan.md#rel-05](../../docs/project-plan.md#rel-05) records the published v0.3.0 tag, release date and QR-01/QR-02/QR-03 sprint-wide checked index, including the explicitly later reliability run; [CHANGELOG.md#030---2026-10-31](../../CHANGELOG.md#030---2026-10-31) and [reports/week-05/release-preparation.md#publication-checkpoint](release-preparation.md#publication-checkpoint) retain the release-cut record. |
| Sprint retrospective | [reports/week-05/sprint-retrospective.md](sprint-retrospective.md): team discussion and observations confirmed on 31 October, four next actions and outcomes for all Week 4 carried actions. |
| AI usage | [reports/week-05/ai-usage.md#team-assessment-recorded-on-31-october](ai-usage.md#team-assessment-recorded-on-31-october): contributor confirms listed tools were used, and human reading/correction supports accepted-with-changes assessments for the previous work. |

## Contributions

These links identify delivered work; they do not assess an individual's performance.

| GitHub member | Repository evidence |
| --- | --- |
| azamatbayramov | [Proxy transport #144](https://github.com/iteam7/gateway7/pull/144), [live smoke #146](https://github.com/iteam7/gateway7/pull/146), [OpenAI environment setup #149](https://github.com/iteam7/gateway7/pull/149), [middleware diagnostics #131](https://github.com/iteam7/gateway7/pull/131), [guarded OpenCode turns #156](https://github.com/iteam7/gateway7/pull/156), and the Customer demonstration. |
| ExFuseMe | [Deployment runbook and verification #147](https://github.com/iteam7/gateway7/pull/147), [actionlint and Definition of Done #150](https://github.com/iteam7/gateway7/pull/150). |
| DeniBorsh | [Quality tests #151](https://github.com/iteam7/gateway7/pull/151), [features and testing-plan structure #152](https://github.com/iteam7/gateway7/pull/152). |
| iceberkut | [Sprint plan and milestones #154](https://github.com/iteam7/gateway7/pull/154), [new-story refinement and usage specification #155](https://github.com/iteam7/gateway7/pull/155). |

Merged [PR #151](https://github.com/iteam7/gateway7/pull/151) closed [task #136](https://github.com/iteam7/gateway7/issues/136); its implementation and the later main CI are distinct from the results recorded in this checkpoint.
The later [PR #162](https://github.com/iteam7/gateway7/pull/162) and actual main run supply the native Windows/Linux reliability evidence; the staging result is explicitly operator-reported at the separately confirmed deployed revision.

## Deviations

- Initial planning is reported as held, but the original selected stories and point total have not been supplied; the later forecast is not substituted for them.
- No Week 4 Customer meeting occurred; the Week 5 report follows actual earlier actions and the separate Week 4 retrospective.
- The 30 October Customer demonstration ran locally because the presenter was outside the university network; VM unavailability and a production-review exemption are not established.
- Named story acceptance is recorded from the participant's 31 October confirmation rather than attributed to explicit words in the supplied transcript; no identified QRT result is backdated as shown in that meeting.
- The contributor selected a private PDF transcript appendix rather than public publication; this later instruction is recorded separately from the original meeting account and does not fabricate a Customer permission quote.
- Native Windows/Linux reliability was checked after the release cut and is not backdated to the Customer meeting or publication.
- The matching deployed commit and core checks are confirmed by the contributor, rather than by independent remote inspection or saved command output.
- Direct HTTP access from the university network is unavailable; SSH forwarding is the current access method, not fulfilment of that course requirement.
- An initial automated approval review blocked publication over the different runtime and documentation revisions; explicit informed contributor authorisation resolved that blocker, and the actual v0.3.0 publication is recorded in the release checkpoint.
- Tracker carryover is complete for the two remaining SPRINT-05 tasks, #138 and #139. Automated approval review prevented closing the empty milestone, which remains open pending specific confirmation; no closure is claimed.

## Privacy

Private team details and links recovered from the previous submission PDF are kept outside GitHub for the private submission only.
No private-only material was committed to the repository.
