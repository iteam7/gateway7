# AI usage — Week 02

## Tools

OpenAI Codex, with a Formater agent for PRE and POST review.
Claude Code (Claude Opus 5.5), with its Formater agent for PRE and POST review.

## What we used them for

Prepared the repository workflow for Assignment 2 in [issue #20](https://github.com/iteam7/gateway7/issues/20):
User story and Task issue forms, disabled blank issues, the required issue labels,
the pull request acceptance-criteria prompt, and Markdown linting on pull requests
and pushes to main.
Checked the current draft course requirements and the pinned action release.
Validated the issue-form structure and Markdown checks.
Any edits to Week 01 Markdown in this change are formatting-only.

Updated the contribution workflow in [issue #22](https://github.com/iteam7/gateway7/issues/22)
after checking the published Assignment 2 requirements on 7 October:
separated story value propositions, origins, and assumptions; added task story links
and required task acceptance criteria; clarified task closure and reviewer checks
in the pull request template; removed the agent-log Markdown exclusion.
Validated both issue forms and checked all tracked Markdown files with
the workflow's bundled markdownlint-cli2 version (0.23.2).

The first pull request link-check run identified three existing links to course
requirements files that had been removed.
Repointed the source-of-rules links in `AGENTS.md` to the current general and research
requirements, and the Week 1 implementation-scope reference in `gap-analysis.md`
to Assignment 1's research-only scope.
Checked the replacement files and heading against the current course repository;
the research findings and identifiers are unchanged, and no link-check exclusions
or accepted status codes were added.

Drafted the Week 2 user stories with Claude Code from the Week 1 value propositions,
gap analysis, and kickoff decisions, before the product vision existed:
the story statements, acceptance criteria, MoSCoW priorities with reasons, and the
minimum usable product candidate with its core task.
The Formater agent checked the drafts against the course's user story and
minimum usable product requirements.
Claude Code also wrote the `## Deviations` section of the Week 02 report.

## Workflow deviations for issue #22

At the contributor's explicit request, the story-form and task-form catch-up changes,
the related pull request guidance, and the Markdown configuration correction are
combined in one pull request instead of the separate catch-up pull requests
Assignment 2 specifies.
The task issue was created through the GitHub connector API, which bypasses the form,
rather than through the issue form; its body contains the required task fields,
its acceptance criteria are a checklist, and it carries the `task` label.
These deviations must also be recorded in the Week 02 public report when it is prepared.
The obsolete course-link repairs are included in the same pull request to restore
the required link check.

Standardized the opening status/freshness line in [issue #46](https://github.com/iteam7/gateway7/issues/46)
across `docs/research/alternatives.md`, `comparison.md`, `gap-analysis.md`, and `value-proposition.md`
to one `**Status (<date>):**` pattern; the four files had each used a different format.
Claude Code also manually re-verified every relative link and heading anchor in `docs/research/*.md`
against the current headings in `reports/week-01/meeting-report.md` and `meeting-notes.md`; none were broken,
so no link content changed, only the status-line formatting.

## What we did with the output

TODO: the team must record which output it accepted, changed, or rejected after review.

## Prototype and customer-validation preparation

OpenAI Codex assisted azamatbayramov with prototype preparation and the validation documentation contribution.
It checked the current course rules, existing story issues and kickoff report, drafted the architecture-focused follow-up script and factual meeting report, and integrated the artifact links into the Week 02 report.
The disposable simulator and its tests remain outside this repository change.
A minimal DOM harness executed its inline JavaScript: 21 functional checks passed on 10 October; browser rendering and screenshots were not verified.

After the user supplied the meeting transcript, Codex read the full evidence and separated gateway7 feedback from two other teams' proposals. It prepared bounded factual paraphrases and three decision records, without publishing the transcript or inferring public-publication permission.

The following assessment records the actual iteration and contributor choices for this contribution; it does not claim a manual line-by-line audit or approval of other team members' work:

- **Retained in the contribution:** the six-field prototype structure, source-linked carry-forward tables, transcript-supported feedback and decisions, and clearly marked missing acceptance evidence after checking the current course requirements and repository.
- **Changed:** replaced the narrow phone-masking emphasis with core architecture, request/response hooks, plugin registration/configuration and restart tracing in response to contributor-reported feedback; corrected candidate story links to issues 30, 31 and 32; after transcript review, distinguished the originally shown masking screen from the later simulator and recorded the requested deterministic-upstream demonstration.
- **Rejected:** presenting a private prototype as grader-accessible, claiming simulator tests satisfy real gateway story criteria, treating illustrative Python as a language decision, or inventing customer acceptance, meeting dates, attendance, consent, decision identifiers, or agreed actions; attributing another team's language choice to gateway7, or treating the simulator as delivery of the promised technical/code-structure prototype.
- **Contributor choices:** azamatbayramov selected the architectural prototype rather than the initial narrow masking screen, requested English and removal of unnecessary explanatory blocks, chose the standalone HTML from the delivered archive as evidence, and requested completion of this contribution as a non-draft PR. He separately reported Customer approval of the candidate, confirmed he will bring both presentation items, and chose to keep the transcript private. These are recorded choices, not a claim that he manually verified every generated sentence. The broader team assessment above is outside this contribution and remains for the team.

The task issue for this contribution was created through the GitHub connector API rather than the task form, as recorded in [task #43](https://github.com/iteam7/gateway7/issues/43) and the [report deviations](README.md#deviations).
The contributor explicitly chose not to publish the original or sanitized transcript; only bounded factual paraphrases and decision records are included.
