# AI usage — Week 02

## Tools

OpenAI Codex, with a Formater agent for PRE and POST review.

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

## What we did with the output

TODO: the team must record which output it accepted, changed, or rejected after review.
