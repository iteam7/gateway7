# Value Proposition

**Proposed direction, 2026-09-30:** A small text-only LLM gateway emphasizing explicit, testable privacy behavior and a core-plus-plugins architecture. No implementation, customer endorsement, measured advantage, or market validation is claimed. Both entries depend on [unvalidated gap hypotheses](gap-analysis.md).

## VP-01: Predictable local preflight for small teams

**Closes:** [GAP-01](gap-analysis.md#gap-01-privacy-configuration-assurance-for-small-teams), if its need and underserved tests are validated.

For developers who must control which conversation text leaves their environment, gateway7 proposes a narrowly scoped proxy that applies a mandatory local policy before forwarding and makes its supported fields, failure behavior and logging boundary explicit. The intended benefit is easier verification of one agreed workflow, not unique ownership of local redaction.

**What we would build:** Supported text fields pass through an ordered policy pipeline; decisions are allow, mask, block or error. The core prevents forwarding on policy errors or unsupported content. Default audit records contain request IDs, rule IDs, actions and durations rather than raw payloads. An isolated fake upstream records only synthetic test requests so the team can verify the boundary.

**What it costs:** Preflight adds latency; fail-closed behavior can reduce availability; masking can reduce answer usefulness. Initial scope excludes streaming, images, attachments and tool payloads, rather than silently passing them unexamined. A self-hosted service still needs operation and updates. “Local” does not mean “accurate” or “compliant.”

**How a competitor would respond:** LiteLLM could document or bundle a privacy-focused preset using its existing local filtering and hooks. Portkey or Kong could offer a similar guided workflow. If those options satisfy the Customer, a preset or extension is more rational than a separate gateway. See [ALT-01, ALT-03 and ALT-04](alternatives.md).

**Validation:** First compare equivalent configurations and failure cases. Reject the proposition if the Customer has no such workflow or if gateway7 offers no meaningful reduction in setup mistakes or verification effort. Set measurable targets only after a baseline and Customer agreement.

## VP-02: Testable domain-filter extensions

**Closes:** [GAP-02](gap-analysis.md#gap-02-verifiable-domain-filter-changes), if validated.

For developers maintaining organization-specific sensitive-data rules, gateway7 proposes a small versioned plugin contract and an offline regression workflow, so a policy change can be reviewed against synthetic examples before it is enabled. The intended distinction is the focused change-and-check experience, not the existence of custom regexes or plugins.

**What we would build:** Two trusted sample plugins, a documented schema, deterministic ordering, configuration validation, and a fixture runner producing expected/actual decisions by rule ID. The core retains control of forwarding and handles plugin exceptions according to the mandatory policy. Reuse existing detectors where their behavior fits the agreed task.

**What it costs:** A stable interface creates maintenance obligations; fixtures require curation and can miss realistic cases. Trusted plugins can still contain defects; this design is not an untrusted-code sandbox. Narrow rules may under-detect contextual information or over-redact benign text.

**How a competitor would respond:** Presidio users can package recognizers and evaluation scripts; LiteLLM users can add a custom guardrail and tests. The project must demonstrate a workflow improvement against those baselines, and should pivot to an extension if that is the better fit. See [ALT-02 and ALT-03](alternatives.md).

**Validation:** Have another team member add a supplied synthetic identifier rule without changing core code, run positive/negative/error fixtures, and explain the result from the report. Repeat the same task with the closest existing alternative. Record errors and effort, not only a successful demo.

## Proposed MVP and boundaries

- Core: one OpenAI-style text chat endpoint, configuration validation, ordered plugin execution and provider dispatch
- Providers: two adapters selected with Customer; use a fake upstream during safety tests
- Filters: one deterministic domain-pattern plugin and one adapter to an existing detector, if needed
- Verification: offline fixtures, full supported-message coverage, block/error non-forwarding and metadata-only logging tests
- Exclusions: streaming, multimodal requests, arbitrary tools, restoration storage, complex routing, billing, multi-tenant governance and an untrusted plugin marketplace

This is a proposal for subsequent work. Assignment 1 is research-only; building a prototype is not needed to complete this week's assignment.

## Assumptions

No assumption is marked confirmed until its evidence is recorded in the [meeting report](../../reports/week-01/meeting-report.md) or a subsequent experiment.

| Assumption | Supports | How we will check it | When |
| --- | --- | --- | --- |
| A small-team text workflow is the right user segment | VP-01, VP-02 | Ask Customer for current process, users, concrete examples and consequences | During the Week 1 kickoff, before approving scope |
| The useful initial boundary can exclude streaming, tools and attachments | VP-01 | Present explicit exclusions and ask which break the workflow | During kickoff |
| Existing configurations impose a meaningful verification burden | GAP-01, VP-01 | Compare the same synthetic scenario in LiteLLM and the proposed workflow; accept reuse if sufficient | Week 2 planning, before committing to standalone implementation |
| Custom domain identifiers matter more than broad model/provider coverage | GAP-02, VP-02 | Request a fictionalized format and benign counterexamples; rank needs | During kickoff |
| An offline contract runner improves policy-change review | VP-02 | A second developer performs the same change with the baseline and proposed interface; record effort/errors | Week 2 experiment |
| Added latency and fail-closed rejection are acceptable | VP-01 | Agree budgets with Customer, then measure local synthetic cases | Budgets at kickoff; measurements after the first authorized implementation |
| The proposed core/plugin split fits team capacity | VP-01, VP-02 | Break the scope into owned tasks and review estimates | Week 2 planning |
| Selected detector languages/entity types match the workflow | VP-01, VP-02 | Agree a representative synthetic corpus; report precision/recall by category | Corpus during Week 2 planning, measurement later |
