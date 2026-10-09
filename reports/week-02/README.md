# Week 02 report

**Draft — not ready for submission.** Several required rows below are still `TODO`: another team member owns `docs/decisions.md`, `docs/assumptions.md`, the story issues, `reports/week-02/prototypes.md`, `reports/week-02/meeting-script.md`, and `reports/week-02/meeting-report.md`. This file must not be submitted, merged as final, or exported to PDF/ZIP until every `TODO` below is replaced with a real artifact.

## Project

Modular LLM Gateway, team 7.

## Summary

TODO: once the customer meeting in [Part 10](https://github.com/inno-itpd/itpd/blob/main/assignments/assignment-2.md#part-10-validate-with-the-customer) has happened, state here what the team found out it was wrong about, citing the `DEC-nnn` that recorded it.

So far: [`docs/product-vision.md`](../../docs/product-vision.md) states the goal, stakeholders, constraints, and boundary, with a [system context diagram](../../docs/architecture/context.svg).

## Coverage

| Deliverable | Artifact |
| --- | --- |
| Kickoff action points | TODO: `## Previous action points` in `reports/week-02/meeting-report.md` (not written yet) |
| Kickoff open questions | TODO: `## Previous open questions` in `reports/week-02/meeting-report.md` (not written yet) |
| Product vision | [`docs/product-vision.md`](../../docs/product-vision.md) |
| System context diagram | [`docs/architecture/context.svg`](../../docs/architecture/context.svg), embedded in the product vision |
| Assumptions | TODO: `docs/assumptions.md` (owner: another team member, not written yet) |
| Decisions | TODO: `docs/decisions.md` (owner: another team member, not written yet) |
| Story issues | TODO: the `US-nn` issues, filtered by the `user-story` label (none opened yet) |
| Issue forms | [`.github/ISSUE_TEMPLATE/user-story.yml`](../../.github/ISSUE_TEMPLATE/user-story.yml), [`task.yml`](../../.github/ISSUE_TEMPLATE/task.yml), [`config.yml`](../../.github/ISSUE_TEMPLATE/config.yml) |
| Labels | [Repository labels](https://github.com/iteam7/gateway7/labels), with `user-story`, `task`, and the `moscow:*` labels |
| Pull request template | [`.github/pull_request_template.md`](../../.github/pull_request_template.md) |
| Prototypes | TODO: `reports/week-02/prototypes.md` (not written yet) |
| Meeting script | TODO: `reports/week-02/meeting-script.md` (not written yet) |
| Customer validation | TODO: `reports/week-02/meeting-report.md`, and `meeting-transcript.md` when there is one (not written yet) |
| AI usage | [`reports/week-02/ai-usage.md`](ai-usage.md) |

## Minimum Usable Product Candidate

Core task: a developer sends a chat request that contains a customer's phone number and gets the model's answer, while the provider receives the number masked by the company's own plugin.

- `US-01`: Get a model's answer without holding a provider key
- `US-02`: Mask phone numbers before a request leaves the company
- `US-03`: Add a company plugin without changing the gateway's code

Customer's verdict: pending the Week 2 validation meeting.

## What changed because of the customer

TODO: one line naming what changed because of what the customer said about the prototype — a `US-nn`, a boundary item, a constraint, or an `ASM-nn` — and the `DEC-nnn` behind the change.

## Contribution

TODO: table mapping each team member's GitHub username to their commits, issues, pull requests, and reviews this week.

## Repository evidence

TODO: one merged pull request that closed its task issue, the latest green link-check run, and the latest green Markdown-check run on `main`.

## Deviations

- The branch `stories-and-mup` was pushed before its task issue existed, so its name does not follow the Week 2 `<issue-number>-<short-description>` rule.
  The pull request was requested before anyone had opened a task issue for this work.
  The task issue will be opened from the task form and named in the pull request with `Closes #<n>` before merge, so the change is still tied to exactly one task issue.
- For [issue #22](https://github.com/iteam7/gateway7/issues/22), the story-form and task-form catch-up changes were combined in one pull request instead of separate catch-up pull requests, and the task issue was created through the GitHub API rather than the issue form.
  The changes were combined at the contributor's request, and the API-created issue still carries every task field, a checklist of acceptance criteria, and the `task` label; see [AI usage](ai-usage.md#workflow-deviations-for-issue-22).

## Privacy

TODO: confirm and state that no private-only material was committed to the repository.
