# AI usage — Week 03

## Tools

OpenAI Codex with the repository's Orchestrator, Formater and TechLead roles, the GitHub connector for repository/issue access, and local shell tools for reading and editing documentation.

## What we used them for

Prepared [task #50](https://github.com/iteam7/gateway7/issues/50) and drafted the architecture proposal, documentation navigation and this partial Week 3 report.
Codex read the current course rules and Assignment 3, product vision, research, decisions, Week 2 meeting report, and the live US-01–03 acceptance criteria.
The proposal develops the contributor's preceding architecture discussion into responsibilities, request/plugin contracts, loading rules and a first implementation slice.

## Handling and checks of generated output

The AI review checked traceability and consistency with the existing candidate, including test-key forwarding and missing-key startup failure in US-01, conversation-history masking in US-02, and plugin installation/order in US-03.
It kept Python/Go unresolved, distinguished DEC-011's deterministic demonstration from US-01 AC-05, and excluded restoration storage from request context because of BND-02.
It separated proposed response hooks from delivered scope, and made the shared-process trust and cancellation limits explicit.
No product implementation or runtime test result is claimed.
Formater checked all 32 Markdown files with Markdownlint CLI2 0.23.2, checked local targets and anchors for 46 links in the five changed files, retrieved the five distinct GitHub destinations through the connector, parsed both diagrams with Mermaid 11.12.1, and ran `git diff --check`.
The Mermaid parser found a semicolon interpreted as a statement separator; replacing it with a comma fixed the sequence diagram without changing its meaning.
The Week 2 action-point citation lives in the weekly report and task rather than the maintained architecture page, so the documentation site need not navigate to weekly evidence.
These checks validate documentation; they are not product-runtime tests or human approval.

## Team evaluation

TODO: the team must record what it accepted, changed or rejected after reviewing the generated architecture and report.
The contributor's request for this MR is not recorded as approval of every drafted contract or as a completed human review.

## Workflow deviations

The API-created task and unresolved scheduling metadata are declared in [reports/week-03/README.md#deviations](README.md#deviations).
No customer decisions, story acceptance results or other contributors' assessments were invented.
