# Week 05 AI usage

## Tools and work

Codex extended [task #89](https://github.com/iteam7/gateway7/issues/89) on 25 October 2026 at azamatbayramov's request to prepare one deployable Gateway7 pilot in one pull request.
The work builds on the async middleware migration recorded in the [Week 4 AI report](../week-04/ai-usage.md).
Developer agents worked on provider adapters, reference middleware, CLI/runtime metrics, and Docker Compose with Prometheus and Grafana.
A separate AI TechLead reviewed their changes and updated the architecture; Formater checked the repository workflow, documentation and publication.
The review required explicit process cleanup when SIGTERM arrives during startup or serving, correct attribution of invalid next-handler metric failures, and treating excessive usage values as unknown before they reach counters.
The Compose smoke was strengthened to verify phone/email masking, response redaction, provider-call counts and the Grafana datasource query path.
The AI review does not supply the required approval from another team member or a Customer verdict.

For [task #91](https://github.com/iteam7/gateway7/issues/91) on 25 October 2026, Claude Code (Claude Opus 5.5) drafted the four quality requirements, their priority matrix and ten functional requirements at DeniBorsh's request.
It took each behavior from the documentation and tests already on `main`, checked the error codes and statuses against `gateway7/errors.py`, and used the container names `gateway`, `prometheus` and `grafana` from the architecture proposal in [task #92](https://github.com/iteam7/gateway7/issues/92).
The priorities are the drafter's proposal for the Accountable reviewer; no Customer ranking, measured performance result or new requirement origin is claimed.

Later on 25 October, azamatbayramov selected the compatible inbound API, gateway client tokens with model access, middleware generation and offline fixture testing as the next implementation work.
Codex extended the same task and pull request, preserving the earlier pilot and its verification evidence.
The extension adds SDK-facing protocol checks, authentication/authorization boundaries and the generated-plugin workflow to the review scope.
Review kept authorized model selection outside plugin-visible payloads and preserved provider usage/finish metadata, rejected undeclared plugin fields and unsupported API options, and disabled implicit trailing-slash redirects.
The generated-package installation check uses the reviewed Gateway7 wheel and installs the plugin with `--no-deps`, so it cannot substitute an unrelated package resolution for the reviewed runtime.
The review also required interrupted offline checks to return a failure after cleaning up their worker, instead of being treated as an orderly successful server shutdown.

On 25 October, for [task #93](https://github.com/iteam7/gateway7/issues/93), Claude Code drafted `docs/glossary.md` and rewrote the root `AGENTS.md` with layout, checks, conventions and do-not-edit sections while keeping the team's agent roles and PRE/POST workflow.
Its Formater agent checked the draft against the course glossary and agent-instruction requirements, compared every path and command in `AGENTS.md` with the repository and the CI workflows, and traced each glossary definition to the linked artifact and the gateway code.

On 25 October, for [task #96](https://github.com/iteam7/gateway7/issues/96), Claude Code drafted the [next Customer Review script](meeting-script.md) and extended the [demo evidence matrix](../../docs/demo.md#acceptance-checklist) to US-01–US-09.
It mapped each acceptance criterion to the existing demo runner, tests and smoke scripts by name, and marked criteria without an exact check as needing a dry-run instead of treating related tests as evidence.
It did not run the demonstration; the Accountable reviewer's dry-run, the meeting date and the role assignments remain with the team.

## Handling and checks

The adapters are checked with synthetic HTTP transports against the documented provider protocols.
These tests can establish payload conversion, usage handling and failure behavior; they do not establish access to a live model or successful provider billing/account setup.
Reference policy tests cover transformations, benign messages, request history, configuration failures and whether blocked requests reach the provider.
CLI and metric checks exercise installed commands, startup errors, readiness and bounded metric labels without prompt text or credentials.
For the initial pilot, the [Ubuntu Compose CI check](https://github.com/iteam7/gateway7/actions/runs/40192076568/job/121165000016) built the non-root image, started the actual gateway/Prometheus/Grafana stack, validated Prometheus configuration and passed the HTTP policy, metric, scrape, dashboard and datasource-query smoke.
The local environment had no Docker or Podman; container verification therefore ran in CI rather than being inferred from YAML parsing.
The initial pilot had 359 passing tests and a separate installed-wheel check.
The extension's fresh-wheel check generated a plugin, installed it as a normal package outside the checkout and exercised it through authenticated SDK HTTP calls.
It checked the offline pass, mismatch and invalid-setup exit codes, and verified that a forbidden model caused no additional provider call.
The check exposed inherited proxy settings affecting local SDK requests; the example client and smoke use an explicit HTTP client that ignores those settings.
The final results for the compatible API, access control and developer workflow extension are recorded in the same pull request.
No live-provider call, Customer acceptance, story closure, release or deployment to a shared environment is claimed.

For [task #97](https://github.com/iteam7/gateway7/issues/97) on 25 October 2026, Claude Code (Claude Opus 5.5) asked DeniBorsh closed questions about `SPRINT-04` and wrote the retrospective from his answers and the repository's record.
It declined to write a retrospective for a discussion that had not happened; every row, the 25 October chat discussion and each action owner come from DeniBorsh's answers.

## Team evaluation

TODO: Team members must record what they accepted, changed or rejected after reviewing the providers, middleware, CLI, deployment/observability, compatible API, access control and plugin-authoring workflow, and after reviewing the glossary and `AGENTS.md` for task #93 and the review script and evidence matrix for task #96.

## Deviations to carry into the weekly report

- The user explicitly requested the provider, middleware, CLI, deployment and observability work in one MR; task #89 and PR #90 therefore cover the whole pilot and retain the earlier middleware migration.
- Task #89 was originally created through the GitHub API. Its Task type, human Responsible/Accountable pair, matching assignees, milestone and Priority remain for the team to set; no role or schedule was inferred.
- At the source check for task #89, `main` had no `FR-nnn` or `ADR-nnn` records for this work. The task retained this missing specification trace as a declared gap rather than inventing accepted course requirements; the later task #92 work below records the requirements integration.
- At the source check on 25 October, Assignment 4 was the latest published assignment. This file records the implementation assistance only and does not claim completion of the Week 5 report or any unpublished assignment.

## Architecture documentation for task #92

On 25 October, azamatbayramov asked Codex to carry out [task #92](https://github.com/iteam7/gateway7/issues/92).
Formater read the current course requirements, checked the issues and remote repository, and prepared a separate working copy whose tracked files matched the merged implementation.
The AI TechLead wrote the container architecture and three ADR drafts; a diagram agent produced an SVG and a Python standard-library generator, then the TechLead reviewed the image and implementation claims.
The work adds the product-vision backlink and documentation navigation without changing the gateway runtime.

The review kept the three deployed applications distinct from Python modules, described the synthetic upstream as a demo-only child process, and retained the existing incoming report anchors and dated team clarification.
The ADRs compare options against the implemented system without inventing a historical options meeting.
In the initial draft, they remained Proposed because [task #91](https://github.com/iteam7/gateway7/issues/91) had not yet supplied the required FR/QR records; the Drivers and ADR fields identified that dependency instead of linking nonexistent specifications.
At that point, the missing requirement mapping and human acceptance left task #92 AC-03 and part of AC-04 unfinished.
No Week 4 meeting, Customer verdict or team acceptance of the new ADR text is claimed.

The committed SVG matched its generator, and regeneration was byte-identical when invoked outside the repository.
The image was visually inspected; XML parsing, Python compilation and Ruff checks passed for the generator.
Markdown lint passed all 56 files; strict MkDocs and the site checker passed 27 maintained pages and 2076 links/assets, including local anchors and report exclusion.
Formater checked the diff and the real remote base before publication; external link checking and the other PR workflow results belong to the pull request evidence.
The source checkout and the remote-only binary report artifacts are preserved; the local snapshot history is not pushed.
The initial pull request was a draft referring to #92, with no closing keyword while its dependency and acceptance criteria were incomplete.

### Completion after the requirements merged

Later on 25 October, after the requirements and glossary pull requests reached `main`, azamatbayramov asked Codex to finish task #92 in the existing [PR #99](https://github.com/iteam7/gateway7/pull/99).
Formater verified the remote heads, imported the reviewed main snapshot and preserved the other contributors' documentation and AI-report entries during the merge.
The TechLead connected the four Drivers holders, replaced the pending ADR fields with real FR/QR links, checked each consequence against its quality scenario and added only ADR backlinks to the eight affected FR records.
The requirement behaviors, acceptance criteria and priorities were not changed.
The navigation keeps both the new requirements/glossary pages and the architecture pages, and the documentation index links the new artifacts.

The records now describe Accepted choices already in force through [PR #90](https://github.com/iteam7/gateway7/pull/90), whose final implementation [DeniBorsh approved](https://github.com/iteam7/gateway7/pull/90#pullrequestreview-5643522171) before merging it.
The course defines Accepted as the choice in force; this retrospective record does not claim that the earlier implementation review approved the later ADR wording.
The ADRs keep explicit limits for trusted in-process plugins, the public synthetic demo token, local monitoring access, Windows repetition and the quality scenarios' separate response measures.
Linking a QR does not establish that its measured checks passed, and no new live-provider run or Customer acceptance was supplied by this documentation work.

Markdown lint passed all 75 files; strict MkDocs and the site checker passed 44 maintained pages and 4133 links/assets, including local anchors and report exclusion.
The updated pull request records the new-head workflow results separately from the initial draft's checks.
The remaining human step is the Accountable member's review of these records and verification of task #92's acceptance criteria; the AI leaves the issue checkboxes and team assessment unchanged.

### Team evaluation for the architecture work

TODO: Team members must record what they accepted, changed or rejected after reviewing the architecture, diagram and ADR records.
The AI review and automated checks do not replace that assessment or the Accountable member's approval.

## Sprint-plan reconciliation for task #95

On 25 October, azamatbayramov asked Codex to carry out [task #95](https://github.com/iteam7/gateway7/issues/95).
Formater read the current course planning, estimation and issue-tracking rules, checked the current main snapshot and prepared a separate working copy without changing the existing task's Responsible/Accountable assignment.
The TechLead and a documentation agent reconciled the plan with the milestone assignments, issue field values and the team's recorded [SPRINT-04 retrospective](../week-04/sprint-retrospective.md).
The plan now gives the required Saturday dates and milestone backlog links, explicitly labels empty future milestones as awaiting selection, distinguishes the eight current carryover tasks from unfinished work still in earlier milestones, and labels missing planning or velocity evidence without inventing zero totals.
The current Week 5 meeting-script draft receives only the corresponding 30-to-31-October deadline correction.

The initial issue API read returned no assigned native Story Points value for any of US-01–US-09; that observation alone did not establish whether the organization had defined the field.
At the user's request to work on refinement, the TechLead appended proposals to [US-07](https://github.com/iteam7/gateway7/issues/36) and [US-08](https://github.com/iteam7/gateway7/issues/37), preserving the existing story text and metadata.
Azamatbayramov then explicitly confirmed 3 SP and 5 SP on 25 October for remaining future verification, resulting fixes and demonstration, not the already completed implementation, historical estimates or a velocity calculation.
This is the user's confirmation in the task conversation, not a claim that every team member voted or that the Customer accepted either story.

The connected GitHub tools did not provide milestone-date or native-field updates, so Formater used the signed-in browser interface for those necessary operations.
All six SPRINT-04–09 milestone dates were corrected and read back; the two future stories were left open with no milestone, Responsible/Accountable values or assignees.
After two reads of the organization settings confirmed that Story Points did not exist, Formater created one Public single-select field with options `1`, `2`, `3`, `5`, `8`, `13`, then assigned US-07 `3` and US-08 `5`.
The field is pinned to issues without a type because these two stories currently have no native type; [task #94](https://github.com/iteam7/gateway7/issues/94) still needs to add its pin to User Story when that type is created, preserving the assigned estimates.
The browser and issue API confirmed both values and the cleared assignments, while all eight Assignment 4 carryover tasks retained their SPRINT-05 milestone and existing assignees.
The TechLead recorded the dated confirmation on the two story bodies without changing their acceptance criteria; refinement evidence stays on the issues rather than in a second backlog document.
The missing historical planning records, the unavailable estimate totals and the absent Week 4 Customer review remain declared gaps rather than reconstructed ceremonies or verdicts.

Markdown lint passed all 75 files; strict MkDocs and the site checker passed 44 maintained pages and 4148 links/assets, including local anchors and report exclusion.
Formater checked the final diff and preserved the full remote tree's existing binary report artifacts during publication.
No new runtime behavior or live-provider verification is claimed by this planning change.

### Team evaluation for the planning correction

TODO: Team members must record what they accepted, changed or rejected after reviewing the corrected plan and the future-work estimates.
The task criteria remain unchecked until verified by its Accountable reviewer; the tracker migration's remaining type and pinning work stays with task #94.

## Tracker migration for task #94

On 25 and 26 October, iceberkut asked Claude Code (Claude Opus 5.5) to do the part of task #94 that a repository maintainer can do.
The Formater agent ran PRE and POST and kept the work in a separate worktree, so the uncommitted project-plan changes in the main checkout stayed untouched.

- The task form now applies the native `Task` type and requires a `Requirements` field; the story form gains an optional `Specified by` field and prefills the acceptance criteria with an unticked `AC-01` checkbox; both stop applying the `task` and `user-story` labels.
- Stories US-01 to US-09 (#30 to #38) got checkbox criteria with their `AC-nn` unchanged and a `### Specified by` list taken from the `Traces to` lines of FR-001 to FR-008 and the ADRs those records name. US-10 and US-11 are Won't Have and were left out.
- Open tasks #77 and #84 got `### Requirements`; #84 names ADR-002 for its deadline rule, and #77 says it is repository upkeep.
- The native `Task` type was set on all 38 task issues, including the four blank pre-form issues.

The AI ticked no acceptance criterion, including on the closed stories #32, #35 and #38, because no issue held a verified tick to carry over.
US-06 (#35) names only ADR-002, because no FR on `main` traces to it; whether it needs its own FR is for the team.
The AI did not create the missing `User Story` type or `MoSCoW` field, change the existing `Story Points` and `Priority` fields (`Priority` is still visible to organization members only and has an extra `Urgent` option), set any Priority, Responsible or Accountable value, or delete labels: an organization member cannot create or change types and fields, and the values are team decisions.

### Team evaluation for the tracker migration

TODO: The Accountable member records whether the `Specified by` mapping and the form changes were accepted, changed or rejected.

## Legacy label retirement for task #106

On 26 October, after azamatbayramov created the `User Story` type and the `MoSCoW` field, iceberkut asked Claude Code (Claude Opus 5.5) to finish the migration left open by #94.
Claude Code set the `User Story` type on #30 to #40 and copied each story's `moscow:*` label into the `MoSCoW` field, then read every value back; the existing `Responsible`, `Accountable` and `Story Points` values stayed unchanged.
At the user's request Claude Code opened #106 with `gh issue create` rather than from the form, using the form's sections and setting the `Task` type by hand.
The story form now applies the `User Story` type, and `docs/README.md` and `docs/product-vision.md` find stories by type instead of by label; the Week 2 and Week 3 reports keep their original label links because finished weeks are not edited.
The six legacy labels were deleted only after every issue carried its type and every story its `MoSCoW` value.

### Team evaluation for the label retirement

TODO: The Accountable member records whether the story typing, the `MoSCoW` values and the label retirement were accepted.

## Release and submission preparation for task #98

On 25 October, azamatbayramov asked Codex to prepare a pull request for [task #98](https://github.com/iteam7/gateway7/issues/98).
Formater read the current assignment and release/report rules, verified the remote main snapshot and prepared a separate branch without changing previously merged work.
The TechLead checked the 19 required coverage rows against the repository, fresh issue types/field values, merged PR authorship/reviews and successful workflows on `main`, then refreshed the report to `0ee5f57f9b4cf01d4a1ac46b5bb34d15048b9686` after PR #107 merged during preparation.
A documentation agent independently read the requirement, architecture, retrospective and meeting-preparation artifacts to identify factual limits and stale statements.

Codex wrote the late Week 4 README as an evidence index and added the release/submission handoff to `CONTRIBUTING.md`.
The report distinguishes the four quality scenarios and three Accepted implementation decisions from proof that every scenario or Customer criterion passed, and separates the late 25 October carryover from work completed before the deadline.
The readback also distinguishes completed tracker configuration and story migration from remaining native role/Priority values and assignee consistency.
The follow-up preserves PR #107's changes and removes the now-resolved story-form type gap from the report.
Earlier AI-report entries and the Week 4 retrospective were preserved as their dated evidence rather than rewritten to match the newer state.

No Week 4 Customer Review occurred, so Codex did not create a meeting report, transcript, verdict decision, release or final submission snapshot.
The current baseline lacks the new README; it is identified as the inspected source, not falsely used as the final report permalink or PDF/ZIP commit.
The existing REL-04 heading and released changelog sections are unchanged, and the PR refers to task #98 without closing its incomplete release/package criteria.
The private roster and previous private reports were unnecessary for this public preparation and were not copied into the repository.
The pull request records the Markdown, documentation and link-check results; no runtime tests or live-provider calls are claimed for this documentation-only change.

### Team evaluation for the release preparation

TODO: Team members must record what they accepted, changed or rejected after reviewing the Week 4 report and release/submission handoff.
The Accountable reviewer still verifies the task criteria and the final private package after its real prerequisites are met.
