# Week 02 report

**Validation contribution prepared for review.** The prototype artifact, factual meeting report, decisions, requirement change, candidate follow-up, ownership and AI-use assessment are linked below. The report still identifies broader team-owned submission items and the screenshot limitation; this is not a claim that every course requirement is complete.

## Project

Modular LLM Gateway, team 7.

## Summary

The meeting showed that our phone-masking demonstration tested the easy behavior rather than the uncertain plugin-host architecture. The Customer requested an architectural approach and plugin integration workflow, recorded in [DEC-009](../../docs/decisions.md#dec-009). The [meeting report](meeting-report.md) distinguishes that demonstrated version from the later redesign; the transcript does not record acceptance of the redesign or exact story bundle. A later [contributor-reported candidate approval](../../docs/decisions.md#dec-012) is recorded separately.

So far: [`docs/product-vision.md`](../../docs/product-vision.md) states the goal, stakeholders, constraints, and boundary, with a [system context diagram](../../docs/architecture/context.svg).

## Coverage

| Deliverable | Artifact |
| --- | --- |
| Kickoff action points | [reports/week-02/meeting-report.md#previous-action-points](meeting-report.md#previous-action-points), partial evidence; closure pending |
| Kickoff open questions | [reports/week-02/meeting-report.md#previous-open-questions](meeting-report.md#previous-open-questions), carried forward |
| Product vision | [`docs/product-vision.md`](../../docs/product-vision.md) |
| System context diagram | [`docs/architecture/context.svg`](../../docs/architecture/context.svg), embedded in the product vision |
| Assumptions | [docs/assumptions.md](../../docs/assumptions.md), team-owned; stable identifier completion pending |
| Decisions | [docs/decisions.md](../../docs/decisions.md), kickoff identifier migration pending; [DEC-009–012](../../docs/decisions.md#dec-009) record the validation and attributed candidate follow-up |
| Story issues | [User story issues](https://github.com/iteam7/gateway7/issues?q=label%3Auser-story), team-owned; candidate links below verified |
| Issue forms | [`.github/ISSUE_TEMPLATE/user-story.yml`](../../.github/ISSUE_TEMPLATE/user-story.yml), [`task.yml`](../../.github/ISSUE_TEMPLATE/task.yml), [`config.yml`](../../.github/ISSUE_TEMPLATE/config.yml) |
| Labels | [Repository labels](https://github.com/iteam7/gateway7/labels), with `user-story`, `task`, and the `moscow:*` labels |
| Pull request template | [`.github/pull_request_template.md`](../../.github/pull_request_template.md) |
| Prototypes | [reports/week-02/prototypes.md](prototypes.md), with [standalone HTML](https://github.com/iteam7/gateway7/blob/1ecf06a9f2d5fe9133160452d19faed907f20d34/prototypes/architecture-lab.html); screenshot limitation declared below |
| Meeting script | [reports/week-02/meeting-script.md](meeting-script.md), follow-up preparation; meeting roles must be assigned before use |
| Customer validation | [reports/week-02/meeting-report.md](meeting-report.md), factual report from a privately supplied transcript; contributor chose not to publish original or sanitized transcript; onward sharing not authorized |
| AI usage | [`reports/week-02/ai-usage.md`](ai-usage.md) |

## Minimum Usable Product Candidate

Original proposed core task: send a chat request through a phone-masking plugin and receive an actual model's answer.

Approved candidate bundle, based on azamatbayramov's separately recorded follow-up:

- [US-01](https://github.com/iteam7/gateway7/issues/30): Get a model's answer without holding a provider key
- [US-02](https://github.com/iteam7/gateway7/issues/31): Mask phone numbers before a request leaves the company
- [US-03](https://github.com/iteam7/gateway7/issues/32): Add a company plugin without changing the gateway's code

Customer feedback requires a revised initial demonstration: start the system, add simple plugins, restart if needed, send a request and inspect the result. A two-plugin example was suggested; a deterministic test/static upstream is sufficient and preferred at this stage, per [DEC-010](../../docs/decisions.md#dec-010) and [DEC-011](../../docs/decisions.md#dec-011).

Verdict: Customer approval of US-01, US-02 and US-03 was reported by azamatbayramov on 10 October, after he was asked specifically about that bundle; see [DEC-012](../../docs/decisions.md#dec-012). The supplied transcript does not contain that explicit verdict, so this is attributed follow-up evidence rather than a reconstructed transcript statement.

This approves a candidate to build, not completed stories. [CON-01](../../docs/product-vision.md#con-01), citing DEC-011, permits a deterministic upstream for the initial usable validation. US-01 AC-05's actual-provider check remains for the integrated implementation; the HTML simulator cannot pass it. The two-plugin example guides the demo, not an invented capacity ceiling or an automatically approved hook contract.

## What changed because of the customer

The [prototype preparation](prototypes.md) now targets architecture and plugin integration per [DEC-009](../../docs/decisions.md#dec-009). [CON-01](../../docs/product-vision.md#con-01) changed to allow a deterministic test/static upstream for the first usable demonstration, citing [DEC-011](../../docs/decisions.md#dec-011), while retaining real-provider integration as the later product goal.

## Contribution

| Member | Work |
| --- | --- |
| azamatbayramov | [Validation contribution PR #44](https://github.com/iteam7/gateway7/pull/44), [task #43](https://github.com/iteam7/gateway7/issues/43), [off-main prototype evidence PR #45](https://github.com/iteam7/gateway7/pull/45); will bring both the architecture and technical prototype the following week. |

Other team members' contribution rows remain to be completed by their owners.

## Repository evidence

[PR #44](https://github.com/iteam7/gateway7/pull/44) merged and closed its task issue, [#43](https://github.com/iteam7/gateway7/issues/43), via its merge commit `b3cabc31ecc993bf55753c7c447301cc7bb0525a`. The latest green [link-check run](https://github.com/iteam7/gateway7/actions/runs/38077817927) and [Markdown-check run](https://github.com/iteam7/gateway7/actions/runs/38077817793) on `main` are both that same merge.

## Deviations

- The branch `stories-and-mup` was pushed before its task issue existed, so its name does not follow the Week 2 `<issue-number>-<short-description>` rule.
  The pull request was requested before anyone had opened a task issue for this work.
  The task issue will be opened from the task form and named in the pull request with `Closes #<n>` before merge, so the change is still tied to exactly one task issue.
- For [issue #22](https://github.com/iteam7/gateway7/issues/22), the story-form and task-form catch-up changes were combined in one pull request instead of separate catch-up pull requests, and the task issue was created through the GitHub API rather than the issue form.
  The changes were combined at the contributor's request, and the API-created issue still carries every task field, a checklist of acceptance criteria, and the `task` label; see [AI usage](ai-usage.md#workflow-deviations-for-issue-22).

- Validation preparation is being recorded after the original Week 2 window. The current script is prospective preparation and does not establish that it preceded an earlier meeting. Actual meeting timing and prior script use remain unverified.
- The contributor selected downloadable standalone HTML from the validation archive instead of changing the private Site's visibility. The HTML is public in closed, unmerged PR #45, with a fixed-commit link and local-browser instructions. Browser screenshot capture remained blocked even after a permitted retry. This provides an inspectable interactive artifact but does not claim to satisfy the course's screenshot expectation for a code spike; no fabricated image is substituted.
- The transcript-supported decisions and later contributor-reported candidate approval have distinct provenance. azamatbayramov confirmed he will bring the architecture and technical prototype; the agreed relative target remains the following week. No exact calendar date was specified, so none is invented.

- [Task #43](https://github.com/iteam7/gateway7/issues/43) was created through the GitHub connector API rather than the task form. The available repository-writing tool is API-based; the issue retains the task fields, label and numbered reviewer acceptance criteria. This is a declared workflow deviation, not an exemption from the form requirement.

- PR #45 is supporting prototype evidence and is intentionally closed unmerged, with no new task issue or second task-closing keyword. PR #44 alone closes task #43. This additional evidence-only PR departs from the usual one-task/one-PR arrangement to preserve the selected HTML without merging disposable prototype code.

## Privacy

No private-only material — real names beyond `Customer` and public GitHub handles, personal emails, recording links or timecodes, or secrets — has been committed to the repository as of this report.

The contributor chose to keep the supplied transcript private, including any sanitized version. This does not assert that the Customer refused publication or authorized onward sharing. The validation contribution adds factual meeting paraphrases, not the supplied transcript. It adds no recording, recording links or timecodes, real names, contact details, or credentials. The repository-wide privacy confirmation above remains for the team to complete.
