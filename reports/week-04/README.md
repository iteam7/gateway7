# Week 04 report

## Project and scope

Gateway7, Team 7: a corporate IT team routes application chat requests through company middleware that can mask, block or allow requests and responses before forwarding to one configured LLM provider.
This is the late Assignment 4 report, prepared on 25 October 2026 after the 24 October 23:59 hard deadline.
It distinguishes the Week 4 record from the carryover implemented on 25 October and checks repository evidence at `main` commit [`0ee5f57f9b4cf01d4a1ac46b5bb34d15048b9686`](https://github.com/iteam7/gateway7/commit/0ee5f57f9b4cf01d4a1ac46b5bb34d15048b9686).
That baseline does not yet contain this report and is not the final submission commit.

## Summary

The merged increment provides an async middleware gateway, selectable OpenAI/Claude/Gemini adapters, client tokens and model access, a supported non-streaming OpenAI-compatible API, plugin generation and offline fixtures, and a Docker Compose stack with Prometheus and Grafana.
The late documentation adds four quality scenarios, ten functional requirements, the three-container view, three Accepted ADRs and a nine-term glossary; Accepted records describe implemented choices, not Customer approval or proof that every quality measure passed.
The tracker forms and existing story specifications were migrated, and the plan now records the corrected Saturday dates and two unscheduled, estimated future-work candidates.

**REL-04 is not published: there is no REL-04 tag or released changelog section.**
The latest published tag remains [v0.1.1](https://github.com/iteam7/gateway7/releases/tag/v0.1.1); it is not relabelled as REL-04.
No Week 4 Customer Review occurred, so the required post-review release sequence cannot yet be completed.
Tasks #91–#98 were created as Assignment 4 carryover in SPRINT-05 on 25 October; this was not a recorded Week 4 planning or Customer scope decision.
Unfinished SPRINT-04 work remains in its original milestone, including [US-04](https://github.com/iteam7/gateway7/issues/33), [#77](https://github.com/iteam7/gateway7/issues/77) and [#84](https://github.com/iteam7/gateway7/issues/84); no retrospective rescheduling or zero velocity is inferred.

## Candidate and Customer outcome

The minimum usable product candidate remains [US-01](https://github.com/iteam7/gateway7/issues/30), [US-02](https://github.com/iteam7/gateway7/issues/31) and [US-03](https://github.com/iteam7/gateway7/issues/32), selected in [DEC-012](../../docs/decisions.md#dec-012).
None was shown in a Week 4 meeting, accepted, rejected or removed by a Week 4 Customer verdict; consequently there is no such verdict's `DEC-nnn` to cite.
GitHub closure of US-03, US-06 and US-09 is separate from the missing Customer acceptance.
The existing [technical evidence matrix](../../docs/demo.md#acceptance-checklist) identifies synthetic checks, exact-fixture gaps and checks still needed; the actual Claude/Gemini call for US-01 AC-05 remains unverified.
US-04/US-06 safe-error wording and US-09's missing `[example-plugin]` example are recorded criterion gaps, not passed checks.
The next review must also settle the unchanged Week 3 questions on workload, secret storage, execution diagnostics, ownership and transcript permissions.

## Coverage

Statuses describe evidence available on 25 October, with live issue metadata checked at 22:28 UTC, not completion before the deadline or a Customer verdict.

| Deliverable | Artifact and observed status |
| --- | --- |
| Sprint plan and estimates | [docs/project-plan.md#sprint-04](../../docs/project-plan.md#sprint-04): corrected due date and backlog link; historical Planned/Actual Velocity remain N/A because usable planning estimates and accepted-completion evidence are missing. The plan does not reconstruct a planning ceremony. |
| Product backlog refinement | [Sprints table grouped by Milestone](https://github.com/orgs/iteam7/projects/1/views/3) and [unscheduled issues](https://github.com/iteam7/gateway7/issues?q=is%3Aissue+is%3Aopen+no%3Amilestone): US-07 and US-08 carry 3 and 5 native Story Points, confirmed by azamatbayramov for remaining future work, with no milestone, roles or assignees. These estimates establish neither historical velocity nor two sprints of committed capacity. |
| Issue catch-up | [User Story issues](https://github.com/iteam7/gateway7/issues?q=is%3Aissue+type%3A%22User+Story%22) and [Task issues](https://github.com/iteam7/gateway7/issues?q=is%3Aissue+type%3ATask): US-01–11 have native User Story/MoSCoW values, the checked stories/tasks no longer carry legacy labels, US-01–09 have checkbox criteria and specification links, and open tasks have Requirements. [PR #107](https://github.com/iteam7/gateway7/pull/107) also sets the story form's native type. Partial: #91–98 have no native role/Priority values, and several scheduled issues have only one of their two role holders assigned. |
| Quality requirements | [docs/quality-requirements/README.md](../../docs/quality-requirements/README.md) indexes four Active records under [docs/quality-requirements/qr/](../../docs/quality-requirements/qr/), covering four distinct characteristics; QR-02 is Maintainability/Testability with High business importance. The scenarios' response measures are requirements, not newly measured results. |
| Functional requirements | [docs/functional-requirements/README.md](../../docs/functional-requirements/README.md) indexes ten Active records in [docs/functional-requirements/fr/](../../docs/functional-requirements/fr/), with behavior, container names, origin/ADR links and technical criteria. |
| Container view | [docs/architecture/README.md#container-view](../../docs/architecture/README.md#container-view), [docs/architecture/container.svg](../../docs/architecture/container.svg), [docs/architecture/container.py](../../docs/architecture/container.py) and [docs/architecture/README.md#container-responsibilities](../../docs/architecture/README.md#container-responsibilities): gateway, Prometheus and Grafana, external LLM systems, responsibilities and state ownership are documented. |
| Architecture and drivers | [docs/architecture/README.md](../../docs/architecture/README.md): four Drivers holder links, the vision backlink, container view, ADR index and diagram legend are present. |
| Architectural decisions | [docs/architecture/README.md#architectural-decisions](../../docs/architecture/README.md#architectural-decisions) indexes [docs/architecture/adr/ADR-001.md](../../docs/architecture/adr/ADR-001.md), [docs/architecture/adr/ADR-002.md](../../docs/architecture/adr/ADR-002.md) and [docs/architecture/adr/ADR-003.md](../../docs/architecture/adr/ADR-003.md), all Accepted; [docs/architecture/adr/TEMPLATE.md](../../docs/architecture/adr/TEMPLATE.md) preserves the record shape. Each record names alternatives, addressed FR/QR and consequences. |
| Glossary | [docs/glossary.md](../../docs/glossary.md): nine terms under domain headings, with definitions and links. |
| Team AGENTS.md | [AGENTS.md](../../AGENTS.md): repository layout, checks, conventions, off-limits files, roles and the course SKILL router are recorded. |
| Issue fields in the project view | [Sprints table](https://github.com/orgs/iteam7/projects/1/views/3): Responsible, Accountable, MoSCoW, Story Points and Priority appear beside Assignees and Milestone; the new fields are Public single-select fields. User Story has MoSCoW/SP/R/A pins, Task has Priority/R/A pins, and issues without a type have no pins. Field configuration does not fill the remaining issue values. |
| Documentation site | [Published Gateway7 documentation](https://iteam7.github.io/gateway7/): navigation includes quality requirements, functional requirements, architecture/ADRs and glossary; the successful main deployment is linked below. Weekly evidence remains in the repository. |
| Week 3 action points | No `reports/week-04/meeting-report.md` exists because no review occurred. [reports/week-03/meeting-report.md#action-points](../week-03/meeting-report.md#action-points) remains the source; [reports/week-05/meeting-script.md#agenda](../week-05/meeting-script.md#agenda) carries the three-plugin, runner-diagnosis and infrastructure questions to the next review. Implementation and CI evidence exist, but no Customer closing outcome is recorded. |
| Week 3 open questions | No Week 4 `Previous open questions` outcome was produced. [reports/week-03/meeting-report.md#open-questions](../week-03/meeting-report.md#open-questions) and [reports/week-05/meeting-script.md#questions](../week-05/meeting-script.md#questions) preserve the questions; no answers are invented. |
| Meeting script | `reports/week-04/meeting-script.md` is absent. [reports/week-05/meeting-script.md](../week-05/meeting-script.md) prepares the next review; date, roles and dry-run evidence remain TODO, and its description of PR #99/#101 as unmerged must be refreshed before use. It is not a retrospective Week 4 script. |
| Customer validation | No Week 4 meeting report, recording or transcript exists for a review that did not occur; no per-story acceptance/rejection was established. [reports/week-05/meeting-script.md#context](../week-05/meeting-script.md#context) records this absence and the next validation target. |
| REL-04 | Blocked by the missing review and ensuing rework: [CHANGELOG.md](../../CHANGELOG.md) retains Unreleased, [docs/project-plan.md#rel-04](../../docs/project-plan.md#rel-04) remains an empty heading, and no release link is fabricated. The ordered handoff is in [CONTRIBUTING.md#release-and-submission-handoff](../../CONTRIBUTING.md#release-and-submission-handoff). |
| Sprint retrospective | [reports/week-04/sprint-retrospective.md](sprint-retrospective.md): a dated 25 October team-chat retrospective with four positive observations, two root-cause findings, three owned actions and the first-retrospective declaration. It does not establish a measured sprint velocity. |
| AI usage | [reports/week-04/ai-usage.md](ai-usage.md) preserves the middleware work record; [reports/week-05/ai-usage.md](../week-05/ai-usage.md) records the later pilot and Assignment 4 carryover. Team evaluation remains TODO in both; AI review is not human assessment. |

## Contribution

These are public authorship and review records, not an assessment of individual performance or claims about unrecorded work.
The listed carryover PRs merged on 25 October after the Week 4 deadline.

| Member | Recorded work |
| --- | --- |
| azamatbayramov | Authored the gateway pilot [PR #90](https://github.com/iteam7/gateway7/pull/90), architecture/ADRs [PR #99](https://github.com/iteam7/gateway7/pull/99) and plan/refinement [PR #104](https://github.com/iteam7/gateway7/pull/104); [approved the tracker forms](https://github.com/iteam7/gateway7/pull/105#pullrequestreview-5645511066). |
| DeniBorsh | Authored quality/functional requirements [PR #101](https://github.com/iteam7/gateway7/pull/101) and the retrospective [PR #102](https://github.com/iteam7/gateway7/pull/102); [approved the pilot implementation](https://github.com/iteam7/gateway7/pull/90#pullrequestreview-5643522171). |
| ExFuseMe | Authored glossary/agent guidance [PR #100](https://github.com/iteam7/gateway7/pull/100) and next-review preparation/evidence matrix [PR #103](https://github.com/iteam7/gateway7/pull/103); [approved the requirements](https://github.com/iteam7/gateway7/pull/101#pullrequestreview-5644722970). |
| iceberkut | Authored the tracker-form migration [PR #105](https://github.com/iteam7/gateway7/pull/105) and story-type/label follow-up [PR #107](https://github.com/iteam7/gateway7/pull/107); [approved the final architecture change](https://github.com/iteam7/gateway7/pull/99#pullrequestreview-5645116142). |

## Repository evidence

[PR #99](https://github.com/iteam7/gateway7/pull/99) merged the architecture and closed [task #92](https://github.com/iteam7/gateway7/issues/92); its linked review is evidence of human PR review, not Customer acceptance.
At the checked baseline `0ee5f57f9b4cf01d4a1ac46b5bb34d15048b9686`, the latest completed main workflows all succeeded:

| Check | Run |
| --- | --- |
| Link check | [40240344973](https://github.com/iteam7/gateway7/actions/runs/40240344973) |
| Markdown check | [40240345030](https://github.com/iteam7/gateway7/actions/runs/40240345030) |
| Documentation site | [40240344977](https://github.com/iteam7/gateway7/actions/runs/40240344977) |
| Python checks | [40240344987](https://github.com/iteam7/gateway7/actions/runs/40240344987) |

These runs precede this report's PR; its own checks and the later submission commit must be verified separately.
The link-check exclusion file contains no excluded URL pattern.
The workflow accepts HTTP 429 and 503 as an availability workaround, so a green run is not proof that every external link returned HTTP 200; the submission owner must open the final permalink and private links.

## Release and submission status

[Task #98](https://github.com/iteam7/gateway7/issues/98) remains open for the release and private package; this PR supplies the public report and a concrete handoff, without claiming the whole task's acceptance criteria passed.
Responsible azamatbayramov prepares the package; Accountable DeniBorsh verifies the resulting artifacts and remaining blockers.
Follow the linked release/submission handoff only after the real Customer Review and required rework, then merge the release-linking documentation and choose one full `main` SHA containing this report and every linked repository artifact.
The final report permalink, private two-page PDF and repository ZIP must identify that same verified commit.
No final PDF, ZIP or Moodle submission is claimed here; an earlier private submission cannot be confirmed from GitHub alone.

## Deviations

- This new report and the main documentation carryover are late additions on 25 October, not backdated Week 4 deliverables. The existing Week 4 AI report and retrospective are preserved rather than rewritten.
- Week 4 had no Customer Review. The missing script/report/transcript, unanswered Week 3 items and absent story verdicts remain unmet requirements; preparing a future review does not substitute for the event.
- The public report is prepared before REL-04 to expose the actual gaps. This reverses the normal final-report-after-release order for this interim record; it neither authorizes a premature release nor claims Assignment 4 is complete. Final release links must be added in the required order after a real tag exists.
- Historical planning estimates and accepted-completion evidence are unavailable, so SPRINT-04 velocity is N/A rather than an invented total. The newly confirmed 3/5 SP estimate is for future remaining work only.
- QR-02 names Gateway7's HTTP entry point, middleware runner, authentication and provider adapters. The product has no frontend or payment module; this follows the canonical critical-module rule but differs from Assignment 4's example-specific wording and still needs instructor clarification.
- The tracker setup and migrated issue bodies do not establish every issue's completed metadata or verified criteria. The carryover tasks lack native role/Priority values, and several scheduled issues' assignees do not match both role fields. The original task/PR closures are not treated as evidence that those omissions passed review.
- The private wrapper cannot truthfully cite refusal to record or a written Week 4 review: neither occurred. If the team submits an incomplete late package, it must state that no meeting took place and disclose the unmet requirement, rather than inventing one of the assignment's expected recording cases.

## Privacy

No private-only material was committed to the repository by this report change.
The real-name/university-email roster, recording links, private transcripts and submission PDF/ZIP stay outside the public repository; the Accountable reviewer must confirm the complete snapshot before private submission.
