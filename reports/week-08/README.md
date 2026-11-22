# Week 08 report — Gateway7

## Summary

As of 22 November 2026, the public record contains three sanitized notes for counted UT-01 sessions.
The results report a 6/7 median SEQ for the main task, so QR-06 QRT-01 passes its predeclared 5/7 bar.
Two of the three participants did not recover from a model denial within the time limit; the triage records two minor findings and no committed product change.

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
The [private usability-data repository](https://github.com/iteam7/gateway7-usability-data) is the text evidence store.
Instructor and recordings-folder access still need confirmation under [#269](https://github.com/iteam7/gateway7/issues/269).

## Configuration management

The [configuration plan](../../docs/configuration-plan.md) and [evaluation](cm-evaluation.md) record 14 active CFG items and four local goals.
The evaluation reviewed the frozen [3d4fac7fc2df677a59a8261e3d60682b51813669 baseline](https://github.com/iteam7/gateway7/commit/3d4fac7fc2df677a59a8261e3d60682b51813669) on 18 November.
The [first change](cm-evaluation.md#the-first-change) proposes making the maintained release and submission instructions reusable by taking the current assignment, task, reviewed evidence, and verified main commit as inputs.
It would keep the release, review, privacy and snapshot checks and links to the historical Week 4 evidence, giving up the inline handoff to reduce manual substitutions.
Team endorsement and implementation remain pending.

## Threshold review

[TOS-01](../../docs/threshold-of-success.md#tos-01) and [TOS-02](../../docs/threshold-of-success.md#tos-02) are open in the maintained threshold.
Any change to their status needs the evidence and decisions from the [Sprint Review](https://github.com/iteam7/gateway7/issues/304), which has no published outcome yet.

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
| REL-08 | [Release plan](../../docs/project-plan.md#rel-08) and [closeout task #304](https://github.com/iteam7/gateway7/issues/304). Tag and released changelog section pending. |
| Sprint retrospective | Pending [#304](https://github.com/iteam7/gateway7/issues/304). |
| AI usage | [Week 8 AI usage](ai-usage.md) |
| Week 7 action points | [Source actions](../week-07/meeting-report.md#action-points). The Week 8 follow-up is pending #304. |
| Week 7 open questions | [Source questions](../week-07/meeting-report.md#open-questions). The Week 8 follow-up is pending #304. |
| Sprint Review | Pending [#304](https://github.com/iteam7/gateway7/issues/304). |
| Meeting script | Pending [#304](https://github.com/iteam7/gateway7/issues/304). |
| Meeting transcript | Pending the Sprint Review. No public transcript or reason for withholding one has been verified. |
| Week 9 handoff | [Week 9 handoff](#week-9-handoff) |

## Contribution and repository evidence

[PR #306](https://github.com/iteam7/gateway7/pull/306) integrated the configuration inventory, glossary, and risk register into main and closed [#302](https://github.com/iteam7/gateway7/issues/302).
[PR #307](https://github.com/iteam7/gateway7/pull/307) added the evaluation through #306.
[PR #298](https://github.com/iteam7/gateway7/pull/298) integrated the installed-plugin authoring guide and workflow.
It preceded the results and is distinct from a usability finding fix.
The three sessions and the results are recorded in [UT-01](../../docs/usability-tests/ut-01/results.md); any later change must follow the findings' team/customer triage rather than being inferred from these notes.

The green runs checked on 20 November for [main commit 7b9832b51cdb1809325b190ace6f8b49ee138c2c](https://github.com/iteam7/gateway7/commit/7b9832b51cdb1809325b190ace6f8b49ee138c2c) were [link check](https://github.com/iteam7/gateway7/actions/runs/44746088723), [Markdown check](https://github.com/iteam7/gateway7/actions/runs/44746088801), [workflow check](https://github.com/iteam7/gateway7/actions/runs/44746088759), and [Python checks](https://github.com/iteam7/gateway7/actions/runs/44746088835).
These runs are an interim checkpoint.
The final submission uses the checks applicable to the actual submitted main commit.

## Deviations

P-02 used a personal laptop in a university dormitory rather than the planned team laptop and campus room; the university-network requirement was met.
The private filtered telemetry export remains private; the public results report only the supplied sanitized reconciliation summary.
The [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan) records QR-06 QRT-01 as **Passes**; QR-05 QRT-01 remains **Not verified**.
The two minor recommendations have no task issue, recorded schedule, or committed release fix.

## Privacy

This draft uses public repository and GitHub evidence and contains no participant identity or private-only material.
The report, linked evidence, and exact submission ZIP still need the final privacy check.

## Week 9 handoff

- Start with the [UT-01 results](../../docs/usability-tests/ut-01/results.md), the [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan), and the eventual [review and release records](https://github.com/iteam7/gateway7/issues/304).
  Verify access to the [private text repository](https://github.com/iteam7/gateway7-usability-data) and the team-owned recordings folder for the handoff.
  The folder details belong in the private submission.
- Use the [configuration plan](../../docs/configuration-plan.md) and the evaluation's four goal sections for [verification](cm-evaluation.md#verify-a-change-without-missing-a-required-gate), [reader and agent instructions](cm-evaluation.md#give-readers-and-agents-a-reusable-current-workflow), [build reproducibility](cm-evaluation.md#reproduce-the-intended-build-without-coupling-unrelated-dependencies), and [release promotion](cm-evaluation.md#promote-a-verified-version-without-mixing-environment-state).
  Those sections record the tradeoffs.
  [The First Change](cm-evaluation.md#the-first-change) gives the starting proposal.
- For the seven-minute deck, use the [authoring guide](../../docs/plugin-agent-guide.md), the verified UT-01 evidence when available, and the configuration baseline and evaluation.
  The [REL-08 plan](../../docs/project-plan.md#rel-08), [changelog](../../CHANGELOG.md#unreleased), and [SPRINT-09 plan](../../docs/project-plan.md#sprint-09) carry the publication, final repository, and reflection handoff.
  The REL-08 tag, final main commit, and reflection remain pending.
  Freeze the report permalink and matching product ZIP only after the public evidence is merged and checked.
