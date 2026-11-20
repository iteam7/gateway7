# Week 08 report — Gateway7

## Summary

As of 20 November 2026, the public record contains no sanitized notes for counted UT-01 sessions.
The counted-session total and any exclusions still need confirmation from the team.
The available evidence supports no completion or ease aggregate, observation-to-telemetry comparison, QR-06 verdict, or finding-driven product decision.

The configuration review covered 14 active inventory items and four local goals.
Its first proposal would make the release and submission instructions reusable each week, trading the inline Week 4 handoff for current instructions while keeping the checks and links to the historical evidence.

## Usability test

[UT-01 results](../../docs/usability-tests/ut-01/results.md) await [sanitized session notes](../../docs/usability-tests/ut-01/sessions/README.md).
No session outcomes, completion or time measures, SEQ or SUS scores, or qualitative findings are available in those files.
The team needs to reconcile the eligible sessions against the private records.
If fewer than three qualify, the report will describe the verified observations without aggregates.

The [staging funnel](../../docs/analytics.md#the-usability-funnel) describes the planned participant-code and request-ID comparison for the two online tasks.
The offline middleware task uses the command exit status and facilitator observation.
The Week 7 teammate pilot is documented separately from [Week 8 pre-session verification and execution](https://github.com/iteam7/gateway7/issues/300).
Usability-test events are excluded from product analytics, but this design alone supplies no measured comparison.

[QR-06 QRT-01](../../docs/quality-requirements/qr/QR-06.md#qrt-01) is **Not verified** in the [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan).
The conclusions, findings, triage, and product response depend on [the results task](https://github.com/iteam7/gateway7/issues/301).
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
| Usability results | [UT-01 results](../../docs/usability-tests/ut-01/results.md), pending #301 |
| Sanitized session notes | [Session index](../../docs/usability-tests/ut-01/sessions/README.md), pending #300 |
| QR and its test | [QR-06](../../docs/quality-requirements/qr/QR-06.md) and [QRT-01](../../docs/quality-requirements/qr/QR-06.md#qrt-01) |
| Findings and their issues | [Findings](../../docs/usability-tests/ut-01/results.md#findings) and [triage](../../docs/usability-tests/ut-01/results.md#triage), pending #301 |
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
Session, results, and any resulting fix PRs are still pending verification.

The green runs checked on 20 November for [main commit 7b9832b51cdb1809325b190ace6f8b49ee138c2c](https://github.com/iteam7/gateway7/commit/7b9832b51cdb1809325b190ace6f8b49ee138c2c) were [link check](https://github.com/iteam7/gateway7/actions/runs/44746088723), [Markdown check](https://github.com/iteam7/gateway7/actions/runs/44746088801), [workflow check](https://github.com/iteam7/gateway7/actions/runs/44746088759), and [Python checks](https://github.com/iteam7/gateway7/actions/runs/44746088835).
These runs are an interim checkpoint.
The final submission uses the checks applicable to the actual submitted main commit.

## Deviations

Counted sessions and any exclusions or shortfall still need confirmation from the sanitized session evidence.
No move to SPRINT-09 or finding-driven fix missing REL-08 is substantiated yet.
The [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan) shows QR-05 QRT-01 and QR-06 QRT-01 as **Not verified** at this checkpoint.
Record final dispositions and reasons when the sprint closes.

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
