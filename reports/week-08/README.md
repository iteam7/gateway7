# Week 08 report — Gateway7

## Summary

As of 22 November 2026, the public record contains three sanitized notes for counted UT-01 sessions.
The results report a 6/7 median SEQ for the main task, so QR-06 QRT-01 passes its predeclared 5/7 bar.
Two of the three participants did not recover from a model denial within the time limit; the triage records two minor findings and no committed product change.

The Customer Review did not take place, so this week has no meeting report, no `DEC` entry from it and no review recording, and `REL-08` was not cut.
Both are declared as deviations below rather than filled with a reconstructed meeting or an untagged release.

The configuration review covered 14 active inventory items and four local goals.
Its first proposal would make the release and submission instructions reusable each week, trading the inline Week 4 handoff for current instructions while keeping the checks and links to the historical evidence.

## Usability test

[UT-01 results](../../docs/usability-tests/ut-01/results.md) summarize the three counted, sanitized sessions in [the session index](../../docs/usability-tests/ut-01/sessions/README.md).
All three completed the main task without help, with median time 4:45 and median SEQ 6/7; the SUS mean is 85.83 and median is 87.5 (`n=3`).
Two participants failed the denied-model recovery task, and one needed a hint on the offline check.
The results record two minor findings and explicitly leaves the recommendations uncommitted pending team/customer review.

[The results' instrumentation comparison](../../docs/usability-tests/ut-01/results.md#instrumentation-comparison) records the supplied sanitized reconciliation: all three online session event pairs matched, with zero missing events, duplicates or production matches.
The filtered export remains private; no raw rows, request IDs or event timestamps are included in this report.
Task 3 is offline and has no telemetry by design; telemetry also cannot establish human task completion, assistance, duration or understanding, which were recorded by observation.

[QR-06 QRT-01](../../docs/quality-requirements/qr/QR-06.md#qrt-01) **Passes** in the [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan).
The two findings and their triage are in [the results record](../../docs/usability-tests/ut-01/results.md#findings-and-triage); no fix is committed or claimed for `REL-08`.
The private evidence link has been retired. See the [sanitized UT-01 results](../../docs/usability-tests/ut-01/results.md) for the public record.

## Configuration management

The [configuration plan](../../docs/configuration-plan.md) and [evaluation](cm-evaluation.md) record 14 active CFG items and four local goals.
The evaluation reviewed the frozen [3d4fac7fc2df677a59a8261e3d60682b51813669 baseline](https://github.com/iteam7/gateway7/commit/3d4fac7fc2df677a59a8261e3d60682b51813669) on 18 November.
The [first change](cm-evaluation.md#the-first-change) proposes making the maintained release and submission instructions reusable by taking the current assignment, task, reviewed evidence, and verified main commit as inputs.
It would keep the release, review, privacy and snapshot checks and links to the historical Week 4 evidence, giving up the inline handoff to reduce manual substitutions.
Team endorsement and implementation remain pending.

## Threshold review

[TOS-01](../../docs/threshold-of-success.md#tos-01) and [TOS-02](../../docs/threshold-of-success.md#tos-02) remain `Open` in the maintained threshold.
The Review that would have settled them did not take place, so no goal is marked `Achieved` or `Missed` and no new outcome is claimed.
The threshold has no usability goal, so the `UT-01` result does not settle one either.

## Coverage

| Deliverable | Where |
| --- | --- |
| Sprint plan | [SPRINT-08](../../docs/project-plan.md#sprint-08) and [planning task #299](https://github.com/iteam7/gateway7/issues/299) |
| Usability results | [UT-01 results](../../docs/usability-tests/ut-01/results.md) |
| Sanitized session notes | [Session index](../../docs/usability-tests/ut-01/sessions/README.md) |
| QR and its test | [QR-06](../../docs/quality-requirements/qr/QR-06.md) and [QRT-01](../../docs/quality-requirements/qr/QR-06.md#qrt-01) |
| Findings and triage | [Findings](../../docs/usability-tests/ut-01/results.md#findings-and-triage); recommendations have no linked task issue or recorded schedule |
| Threshold review | [Threshold review](#threshold-review) |
| Configuration management | [Configuration management](#configuration-management) |
| Glossary | [Repository configuration](../../docs/glossary.md#repository-configuration) |
| Risk register | [Risk register](../../docs/risks.md) |
| REL-08 | Not cut: [the plan block](../../docs/project-plan.md#rel-08) is empty, no `v0.5.0` tag exists, and the changelog has no released section. Declared in [Deviations](#deviations). |
| Sprint retrospective | Not recorded. Declared in [Deviations](#deviations). |
| AI usage | [Week 8 AI usage](ai-usage.md) |
| Week 7 action points | [Source actions](../week-07/meeting-report.md#action-points). Not reconciled: the Review did not take place, so the plugin-walkthrough action has no Week 8 outcome to record. |
| Week 7 open questions | [Source questions](../week-07/meeting-report.md#open-questions). Not put to the Customer: the Review did not take place. |
| Sprint Review | Did not take place. Declared in [Deviations](#deviations). |
| Meeting script | [Week 8 Review script](meeting-script.md) is prepared; it was not used, because the meeting did not take place. |
| Meeting transcript | None, because no meeting was held. No refusal by the Customer is claimed. |
| Week 9 handoff | [Week 9 handoff](#week-9-handoff) |

## Contribution and repository evidence

[PR #306](https://github.com/iteam7/gateway7/pull/306) integrated the configuration inventory, glossary, and risk register into main and closed [#302](https://github.com/iteam7/gateway7/issues/302).
[PR #307](https://github.com/iteam7/gateway7/pull/307) added the evaluation through #306.
[PR #298](https://github.com/iteam7/gateway7/pull/298) integrated the installed-plugin authoring guide and workflow.
It preceded the results and is distinct from a usability finding fix.
The three sessions and the results are recorded in [UT-01](../../docs/usability-tests/ut-01/results.md); any later change must follow the findings' team/customer triage rather than being inferred from these notes.

The green runs checked on 22 November for [main commit eaaa0ee14fc1c81ac71e94b5b8b06d77b425a4b9](https://github.com/iteam7/gateway7/commit/eaaa0ee14fc1c81ac71e94b5b8b06d77b425a4b9) are [link check](https://github.com/iteam7/gateway7/actions/runs/45052332126), [Markdown check](https://github.com/iteam7/gateway7/actions/runs/45052332283), [workflow check](https://github.com/iteam7/gateway7/actions/runs/45052332171), [Python checks](https://github.com/iteam7/gateway7/actions/runs/45052332094), [documentation site](https://github.com/iteam7/gateway7/actions/runs/45052332068), and [quality requirements](https://github.com/iteam7/gateway7/actions/runs/45052332152).
The [installed-plugin authoring run](https://github.com/iteam7/gateway7/actions/runs/45052332185) passed on retry for the same commit: its first attempt failed the Windows `Ctrl-C should cleanly stop the dev supervisor` assertion, which [open PR #274](https://github.com/iteam7/gateway7/pull/274) is meant to address.
That intermittent failure is recorded here rather than presented as a passing check on the first run.

The sessions, the results and the report entered `main` through [PR #324](https://github.com/iteam7/gateway7/pull/324), which closed [#319](https://github.com/iteam7/gateway7/issues/319), and the results task itself was closed without a separate pull request.
The configuration work entered through [PR #306](https://github.com/iteam7/gateway7/pull/306) and [PR #307](https://github.com/iteam7/gateway7/pull/307); the planning, access, analytics and Week 7 reconciliation text entered through [PR #310](https://github.com/iteam7/gateway7/pull/310), [PR #313](https://github.com/iteam7/gateway7/pull/313), [PR #314](https://github.com/iteam7/gateway7/pull/314), [PR #315](https://github.com/iteam7/gateway7/pull/315), [PR #316](https://github.com/iteam7/gateway7/pull/316), [PR #311](https://github.com/iteam7/gateway7/pull/311) and [PR #317](https://github.com/iteam7/gateway7/pull/317).

## Deviations

- **No Customer Review.** The Sprint Review did not take place, so there is no meeting report, no `DEC` entry from it, no review recording and no transcript. The [script](meeting-script.md) was prepared and was not used. The Week 7 action points and open questions were not put to the Customer.
- **No `REL-08`.** No `v0.5.0` tag was created, the plan's `REL-08` block stays empty, and the changelog has no released section. The package version is prepared at `0.5.0`, which does not publish a release.
- **No retrospective.** `reports/week-08/sprint-retrospective.md` was not written, because the team did not record one.
- **Session environment.** P-02 used a personal laptop in a university dormitory rather than the planned team laptop and campus room; the university-network requirement was met.
- **Private instrumentation evidence.** The filtered telemetry export stays private; the public results report only the supplied sanitized reconciliation summary.
- **Deferred recommendations.** The two minor findings have no task issue, no recorded schedule and no fix claimed for a release.
- **Late submission.** The assignment deadline was 21 November 2026 at 23:59. The report and its evidence were finalized on 22 November, so the submission is late and the Moodle handoff is a separate, still-open step.

The [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan) records QR-06 QRT-01 as **Passes** and QR-05 QRT-01 as **Not verified**, whose planned sprint has already passed; that row still needs a verdict or a reschedule with a reason.

## Privacy

No private-only material and no participant identity were committed to this repository.
The session notes carry participant codes only; raw notes, consent records, identity mapping, the filtered export and the recordings stay in their private homes, which this report does not name.
No deployment address, dashboard address, credential or cloud-folder link appears in this report or in the files it links.

## Week 9 handoff

- Start with the [UT-01 results](../../docs/usability-tests/ut-01/results.md) and the [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan); the Review and release records the older drafts point at do not exist, as [Deviations](#deviations) declares.
- Use the [configuration plan](../../docs/configuration-plan.md) and the evaluation's four goal sections for [verification](cm-evaluation.md#verify-a-change-without-missing-a-required-gate), [reader and agent instructions](cm-evaluation.md#give-readers-and-agents-a-reusable-current-workflow), [build reproducibility](cm-evaluation.md#reproduce-the-intended-build-without-coupling-unrelated-dependencies), and [release promotion](cm-evaluation.md#promote-a-verified-version-without-mixing-environment-state).
  Those sections record the tradeoffs.
  [The First Change](cm-evaluation.md#the-first-change) gives the starting proposal.
- For the seven-minute deck, use the [authoring guide](../../docs/plugin-agent-guide.md), the verified UT-01 evidence when available, and the configuration baseline and evaluation.
  The [REL-08 plan](../../docs/project-plan.md#rel-08), [changelog](../../CHANGELOG.md#unreleased), and [SPRINT-09 plan](../../docs/project-plan.md#sprint-09) carry the publication, final repository, and reflection handoff.
- SPRINT-09 starts from three unfinished items rather than from a clean close: cut `REL-08`, close the `SPRINT-08` milestone, and record the retrospective, all without a Customer Review, which the deviations above declare.
  The package version is already `0.5.0`, so the release commit can be tagged once the team decides the version is final.
- Freeze the report permalink and the matching product ZIP only after the public evidence is merged and checked; a ZIP taken from a branch is not a submission snapshot.
