# Week 02 report

## Minimum Usable Product Candidate

Core task: a developer sends a chat request that contains a customer's phone number and gets the model's answer, while the provider receives the number masked by the company's own plugin.

- `US-01`: Get a model's answer without holding a provider key
- `US-02`: Mask phone numbers before a request leaves the company
- `US-03`: Add a company plugin without changing the gateway's code

Customer's verdict: pending the Week 2 validation meeting.

## Deviations

- The branch `stories-and-mup` was pushed before its task issue existed, so its name does not follow the Week 2 `<issue-number>-<short-description>` rule.
  The pull request was requested before anyone had opened a task issue for this work.
  The task issue will be opened from the task form and named in the pull request with `Closes #<n>` before merge, so the change is still tied to exactly one task issue.
- For [issue #22](https://github.com/iteam7/gateway7/issues/22), the story-form and task-form catch-up changes were combined in one pull request instead of separate catch-up pull requests, and the task issue was created through the GitHub API rather than the issue form.
  The changes were combined at the contributor's request, and the API-created issue still carries every task field, a checklist of acceptance criteria, and the `task` label; see [AI usage](ai-usage.md#workflow-deviations-for-issue-22).
