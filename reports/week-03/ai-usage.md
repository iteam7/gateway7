# AI usage — Week 03

## Tools

OpenAI Codex with the repository's Orchestrator, Formater and TechLead roles, the GitHub connector for repository/issue access, and local shell tools for reading and editing documentation.
Claude Code (Claude Opus 5.5) with the TechLead role edited the Python workflow for task #77.
For task #52, TechLead delegated disjoint core, plugin and transport/demo implementation to Codex developer agents as permitted by `AGENTS.md`.
Python, uv, pytest and real local HTTP subprocesses were used to check the generated code.
For task #54, TechLead delegated the documentation build to an executing agent and reviewed its output; MkDocs, uv, npm, Markdownlint and Chromium were used for documentation checks.

## What we used them for

Prepared [task #50](https://github.com/iteam7/gateway7/issues/50), the architecture proposal, navigation and partial Week 3 report from the course rules, product vision, decisions, research and US-01–03.
At the contributor's requests, Codex expanded the lifecycle, added the seven-stage customer diagram, then shortened the proposal and MR description while preserving the design boundaries and story traceability.
Codex then arranged the Customer view as a downward request path and upward response path, and checked the rendered geometry in Chromium with Mermaid 11.12.1.
An earlier discussion explored Python plugin packaging and lifecycle without adopting a stack or implementing code in this architecture contribution.

After azamatbayramov explicitly selected Python on 15 October, Codex recorded [DEC-013](../../docs/decisions.md#dec-013) and implemented [task #52](https://github.com/iteam7/gateway7/issues/52): the FastAPI gateway, strict configuration/models, plugin lifecycle and chains, phone/sample modules, HTTP adapters, deterministic upstream, locked environment and repeatable demonstration.
It prepared setup/plugin/demo documentation and the Week 3 meeting script, keeping real-provider validation and the Customer's future verdicts separate.
For [task #77](https://github.com/iteam7/gateway7/issues/77), Claude Code added `windows-latest` to the Python workflow after the Windows run found failures that the Ubuntu-only job had missed.

For [task #54](https://github.com/iteam7/gateway7/issues/54), Codex prepared the Definition of Done, contribution guide, README navigation and documentation build/Pages workflow for the requested Assignment 3 items 6, 7, 14 and 15.
It retained source report citations while excluding weekly evidence from the published site, bundled Mermaid locally, and recorded the unresolved Pages activation and live-link requirements.

## Handling and checks of generated output

TechLead reviewed component responsibilities, independent hook order, fail-closed errors, state, keys, usage and shared-process trust/cancellation limits against the existing candidate.
The proposal preserves DEC-011's deterministic-demo scope, the separate real-provider check in US-01 / AC-05, and BND-02's exclusion of restoration storage.
Earlier versions passed Markdownlint, local-link/anchor and Mermaid syntax checks; a sequence-label syntax error was corrected.
This shortening retains the component and customer diagrams and replaces repeated lifecycle detail with compact rules; the current documentation checks are recorded in MR #51.
These checks and AI reviews do not establish runtime acceptance or human approval.

For the Python increment, TechLead reviewed every generated code area and checked startup error sanitization, async hook signatures, strict settings, exact story fixtures, separate-process key forwarding, fail-closed errors and request-state isolation.
The review found that a plugin factory's own `StartupError` could otherwise bypass sanitization; the error boundary was corrected and a regression test added before approval.
Runtime and final publication evidence is recorded in the [Week 3 report](README.md#python-prototype-evidence), without treating offline Claude mocks as US-01 / AC-05.
The final local run passed 99 tests, compile checks and the exact-fixture two-process demonstration; the documented manual service commands and README curl were checked as well.
Formater verified literal US-03 installation evidence in a disposable Git copy: only `config/demo.yaml` and `company_plugins/sample.py` changed, and restart produced the sample marker upstream.
TechLead's APPROVED verdict is an AI code-review result; it does not fill in the human evaluation below.
Official Claude Messages documentation informed the adapter; current Astral/GitHub documentation confirmed Dependabot's `uv` lockfile ecosystem.

For the documentation workflow, TechLead reviewed the source and full change diff and issued **APPROVED**.
Checks passed for all 39 Markdown files, a strict 13-page site build, 821 generated links/assets, desktop/mobile navigation and both rendered architecture diagrams, including the Customer view's upward response path.
The 16 historical report citations remain links in repository source and render as plain text on the site.
The workflow's action pins, locked dependencies, pull-request build and main-only deployment boundaries were checked.
GitHub Pages remained disabled; neither the first deployment nor a live site hyperlink was accepted as complete.

## Team evaluation

TODO: the team must record what it accepted, changed or rejected after reviewing the generated architecture, Python code, tests, documentation workflow and report.
The contributor's request for this MR is not recorded as approval of every drafted contract or as a completed human review.

## Workflow deviations

The API-created task and unresolved scheduling metadata are declared in [reports/week-03/README.md#deviations](README.md#deviations).
No customer decisions, story acceptance results or other contributors' assessments were invented.
