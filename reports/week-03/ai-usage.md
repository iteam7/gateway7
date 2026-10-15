# AI usage — Week 03

## Tools

OpenAI Codex in the Orchestrator, Formater and TechLead roles, with the GitHub connector and local documentation tools.

## What we used them for

Prepared [task #50](https://github.com/iteam7/gateway7/issues/50), the architecture proposal, navigation and partial Week 3 report from the course rules, product vision, decisions, research and US-01–03.
At the contributor's requests, Codex expanded the lifecycle, added the seven-stage customer diagram, then shortened the proposal and MR description while preserving the design boundaries and story traceability.
An earlier discussion explored Python plugin packaging and lifecycle without adopting a stack or implementing code in this architecture contribution.

## Handling and checks of generated output

TechLead reviewed component responsibilities, independent hook order, fail-closed errors, state, keys, usage and shared-process trust/cancellation limits against the existing candidate.
The proposal preserves DEC-011's deterministic-demo scope, the separate real-provider check in US-01 / AC-05, and BND-02's exclusion of restoration storage.
Earlier versions passed Markdownlint, local-link/anchor and Mermaid syntax checks; a sequence-label syntax error was corrected.
This shortening retains the component and customer diagrams and replaces repeated lifecycle detail with compact rules; the current documentation checks are recorded in MR #51.
These checks and AI reviews do not establish runtime acceptance or human approval.

## Team evaluation

TODO: the team must record what it accepted, changed or rejected after reviewing the generated architecture and report.
The contributor's request is not a completed human review.

## Workflow deviations

The API-created task and unresolved scheduling metadata are declared in [reports/week-03/README.md#deviations](README.md#deviations).
No customer decisions, story acceptance results or other contributors' assessments were invented.
