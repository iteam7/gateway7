# Week 02 report

**Draft — not ready for submission.** The prototype and meeting preparation below are reviewable drafts; an exact candidate verdict, a publicly inspectable prototype view, agreed action ownership/deadlines, and the remaining team-owned requirements are still pending. This file must not be submitted, merged as final, or exported to PDF/ZIP until those gaps are resolved.

## Project

Modular LLM Gateway, team 7.

## Summary

The meeting showed that our phone-masking demonstration tested the easy behavior rather than the uncertain plugin-host architecture. The Customer requested an architectural approach and plugin integration workflow, recorded in [DEC-009](../../docs/decisions.md#dec-009). The [meeting report](meeting-report.md) distinguishes that demonstrated version from the later redesign; neither the redesigned architecture nor the exact story bundle was accepted.

So far: [`docs/product-vision.md`](../../docs/product-vision.md) states the goal, stakeholders, constraints, and boundary, with a [system context diagram](../../docs/architecture/context.svg).

## Coverage

| Deliverable | Artifact |
| --- | --- |
| Kickoff action points | [reports/week-02/meeting-report.md#previous-action-points](meeting-report.md#previous-action-points), partial evidence; closure pending |
| Kickoff open questions | [reports/week-02/meeting-report.md#previous-open-questions](meeting-report.md#previous-open-questions), carried forward |
| Product vision | [`docs/product-vision.md`](../../docs/product-vision.md) |
| System context diagram | [`docs/architecture/context.svg`](../../docs/architecture/context.svg), embedded in the product vision |
| Assumptions | [docs/assumptions.md](../../docs/assumptions.md), team-owned; stable identifier completion pending |
| Decisions | [docs/decisions.md](../../docs/decisions.md), kickoff identifier migration pending; [DEC-009–011](../../docs/decisions.md#dec-009) record this validation |
| Story issues | [User story issues](https://github.com/iteam7/gateway7/issues?q=label%3Auser-story), team-owned; candidate links below verified |
| Issue forms | [`.github/ISSUE_TEMPLATE/user-story.yml`](../../.github/ISSUE_TEMPLATE/user-story.yml), [`task.yml`](../../.github/ISSUE_TEMPLATE/task.yml), [`config.yml`](../../.github/ISSUE_TEMPLATE/config.yml) |
| Labels | [Repository labels](https://github.com/iteam7/gateway7/labels), with `user-story`, `task`, and the `moscow:*` labels |
| Pull request template | [`.github/pull_request_template.md`](../../.github/pull_request_template.md) |
| Prototypes | [reports/week-02/prototypes.md](prototypes.md), draft; public view/screenshots pending |
| Meeting script | [reports/week-02/meeting-script.md](meeting-script.md), prospective planning draft; role assignments pending |
| Customer validation | [reports/week-02/meeting-report.md](meeting-report.md), factual draft from a privately supplied transcript; contributor chose not to publish original or sanitized transcript; onward sharing not authorized |
| AI usage | [`reports/week-02/ai-usage.md`](ai-usage.md) |

## Minimum Usable Product Candidate

Original proposed core task: send a chat request through a phone-masking plugin and receive an actual model's answer.

Original proposed bundle, retained for traceability:

- [US-01](https://github.com/iteam7/gateway7/issues/30): Get a model's answer without holding a provider key
- [US-02](https://github.com/iteam7/gateway7/issues/31): Mask phone numbers before a request leaves the company
- [US-03](https://github.com/iteam7/gateway7/issues/32): Add a company plugin without changing the gateway's code

Customer feedback requires a revised initial demonstration: start the system, add simple plugins, restart if needed, send a request and inspect the result. A two-plugin example was suggested; a deterministic test/static upstream is sufficient and preferred at this stage, per [DEC-010](../../docs/decisions.md#dec-010) and [DEC-011](../../docs/decisions.md#dec-011).

Verdict: revision requested; the exact US-01/US-02/US-03 bundle was not presented for acceptance. The team's revised candidate must map the requested demonstration to story criteria and obtain an explicit verdict. In particular, US-01 AC-05 still requires an actual provider, and US-03 AC-03 tests ordering but does not by itself establish all requested usable-demo steps. These issues are not silently edited or marked accepted by this report.

## What changed because of the customer

The [prototype preparation](prototypes.md) now targets architectural flow and plugin integration per [DEC-009](../../docs/decisions.md#dec-009); the candidate above records the deterministic-upstream clarification per [DEC-011](../../docs/decisions.md#dec-011). The required corresponding story, boundary, constraint or assumption update remains pending its owner's review; no accepted story or approved core-hook contract is claimed.

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

- Validation preparation is being recorded after the original Week 2 window. The current script is prospective preparation and does not establish that it preceded an earlier meeting. Actual meeting timing and prior script use remain unverified.
- The prototype remains owner-only; it is not a public view-only submission artifact. Genuine sanitized screenshots or an authorized, accessible view are still required. Browser rendering was blocked during preparation.
- The report now records three supported decisions and the two parts of the team's next-presentation commitment. Exact candidate acceptance, individual execution owners and due dates mapped to Week 3 remain unresolved. The available evidence must not be stretched to claim those requirements are satisfied.

- [Task #43](https://github.com/iteam7/gateway7/issues/43) was created through the GitHub connector API rather than the task form. The available repository-writing tool is API-based; the issue retains the task fields, label and numbered reviewer acceptance criteria. This is a declared workflow deviation, not an exemption from the form requirement.

## Privacy

TODO: confirm and state that no private-only material was committed to the repository.

The contributor chose to keep the supplied transcript private, including any sanitized version. This does not assert that the Customer refused publication or authorized onward sharing. The lane 4 draft adds factual meeting paraphrases, not the supplied transcript. It adds no recording, recording links or timecodes, real names, contact details, or credentials. The repository-wide privacy confirmation above remains for the team to complete.
