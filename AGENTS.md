# AGENTS.md

Rules for every AI agent working in this repository (Claude Code, Codex, Cursor, Copilot, and others).
Project: Modular LLM Gateway, team 7, ITPD course.

## Source of rules

The course rules live in [inno-itpd/itpd](https://github.com/inno-itpd/itpd).
Read the current versions before checking work:

- [rules.md](https://github.com/inno-itpd/itpd/blob/main/course/rules.md)
- [General Requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/general-requirements.md)
- [Repository Requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/repository-requirements.md)
- [Research Requirements](https://github.com/inno-itpd/itpd/blob/main/requirements/research-requirements.md)
- The assignment of the current week in [assignments/](https://github.com/inno-itpd/itpd/tree/main/assignments)

Do not rely on memory.
If a rule is not in these files, say so.

## Roles

- **Orchestrator** only dispatches tasks to other agents.
  It never reads or edits files, runs commands, or does the task itself.
  For every task it runs PRE through Formater, delegates to the executing agent, then runs POST through Formater.
- **Formater** owns the [Workflow](#workflow) checks and all git work.
- **TechLead** owns the architecture (`docs/architecture/`, ADRs), picks skills for the stack once it is announced, splits code work into tasks for developer agents, and reviews every code change.
  No code change passes POST without TechLead's `APPROVED`.
- **Executing agents** do the task within the constraints Formater set in PRE.

Tools without subagents (for example Codex) play all three roles in sequence, but keep the steps separate: PRE, then the task, then POST.

## Workflow

Every task goes through three steps.

### PRE: before starting

1. Add a log entry (see [Log](#log)): who does the task, what it is, which files it touches.
2. Check the task against the course rules: the artifact is in its final location (`docs/` for maintained documentation, `reports/week-NN/` for weekly evidence), no private data, one change per pull request.
3. Check git: the current branch is not `main`, and the branch name follows [Git](#git).
   Create the branch if needed.
4. State the constraints and acceptance criteria.
   If the task breaks a rule, stop with `BLOCKED` and the reason.

### POST: after finishing

1. Check the result against the PRE criteria and the [checklist](#checklist).
2. Add a log entry: what was done, changed files (`git status`, `git diff --stat`), verdict.
3. Verdict: `APPROVED`, or `CHANGES REQUIRED` with each violation as file:line, rule, fix.
   Fix everything and run POST again.
4. Record AI usage in `reports/week-NN/ai-usage.md`: tool and what it was used for.
   Leave the team's assessment of the output as `TODO`; never invent it.

### Git

- Branch names: in Week 1, `short-lowercase-description`; from Week 2, `<issue-number>-<short-description>`.
- Never commit or push directly to `main`.
  Every change goes through a pull request.
- One pull request, one change.
- Commit messages: imperative English subject, at most 72 characters, optional body.
  Add the co-author trailer your tool requires.
- Pull requests fill in [.github/pull_request_template.md](.github/pull_request_template.md).
- Never rewrite shared history (`rebase`, `push --force`, `reset --hard`), except to remove leaked secrets.
- `git push`, creating a pull request, and merging need explicit confirmation from the user.

## Checklist

- Structure: `README.md`, `LICENSE`, `.gitignore`, `.github/pull_request_template.md`, `.github/workflows/lychee.yml`, `docs/research/*`, `reports/week-NN/*`.
- Identifiers `ALT-nn`, `GAP-nn`, `VP-nn`, `US-nn` appear in the heading of their own section, are never reused or renumbered, and removed items are marked with a reason and date.
- References between artifacts use identifiers; every cell in `docs/research/comparison.md` points to an `ALT-nn`.
- `meeting-report.md` has exactly six sections in order (Metadata, Summary, Decisions, Action points, Open questions, Disagreements), with the required table columns; empty sections say `None`.
- Only one of `meeting-transcript.md` and `meeting-notes.md` exists per meeting.
- No private material: real names, university emails, recording links or timecodes, secrets, `.env`, large binaries.
- All Markdown links resolve; every exclusion in `.lycheeignore` is justified.
- Workflow actions are pinned to a full commit SHA with a version comment.
- The week report covers every item the week's assignment lists.
- No filler: a sentence that could be pasted into another team's report unchanged is a finding.

## Log

Keep the log in `.agents-log.md` in the repository root.
Entry format:

```text
## <YYYY-MM-DD HH:MM> <PRE|POST|GIT> - <short task name>
- Agent: <tool or user>
- Branch: <name>
- Files: <list>
- Verdict: <OK | BLOCKED | APPROVED | CHANGES REQUIRED>
- Notes: <list or None>
```

## Limits

- Do not invent research findings, meeting content, or team assessments; check and format only.
- Report to the user briefly: verdict and findings, no retelling of the work.
