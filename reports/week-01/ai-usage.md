# AI usage — Week 01

## Tools

Claude Code (Claude Opus 5.5), CLI.
OpenCode (GPT-6 Sol), CLI.

## What we used them for

Generated the initial repository skeleton from the Assignment 1 requirements:
`.gitignore`, `.github/pull_request_template.md`, `.github/workflows/lychee.yml`,
`.github/dependabot.yml`, `.lycheeignore`, root `README.md`, and empty templates
for `docs/research/*` and `reports/week-01/*`.

Generated the AI agent setup for the repository:
`AGENTS.md` (shared rules for all AI tools: roles, workflow, checklist, log format),
`CLAUDE.md` (imports `AGENTS.md`), and the Claude Code subagents
`.claude/agents/formater.md`, `.claude/agents/orchestrator.md`, `.claude/agents/techlead.md`.
Added `.claude/settings.local.json` and `.agents-log.md` to `.gitignore`.

Used OpenCode to inspect the failed Lychee run and correct the broken course-rules
link in `AGENTS.md`; checked the destination against the current course rules.

Used Claude Code on `reports/week-01/candidate-list.md`: on 2026-10-02 it opened
each of the 11 official sources and checked the relevance line and decision
against it (three lines were corrected: Agent Router, NeMo Guardrails, APISIX),
grouped the candidates into four categories with one selected per category,
wrote an explicit rejection reason for each of the 7 rejected candidates, and
checked that all links resolve.

## What we did with the output

TODO — what we accepted unchanged, what we edited, what we rejected and why.
The workflow and templates were checked against the course requirements by hand.

## What was not used

No AI output was used as a research finding.
