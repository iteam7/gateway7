# Value Proposition

**Revised direction, 2026-10-03:** A modular corporate LLM gateway whose trusted plugins can inspect requests and responses and adapt organization-specific policies. The [October 2 kickoff](../../reports/week-01/meeting-report.md#summary) established that direction; it did not endorse the team's earlier written privacy-first propositions, which were not presented. Python is the working proposal; the meeting accepted Python or Go. No implementation, measured advantage or market validation is claimed.

The original `VP-01` and `VP-02` identifiers are retained as narrower parts of that direction. Both depend on [gap hypotheses](gap-analysis.md) whose underserved tests remain open. Existing plugin systems are credible reuse baselines.

## VP-01: Predictable local preflight for small teams

**Revision:** The original small-team privacy-first proposition is narrowed to a sample privacy workflow inside the corporate plugin host. It no longer defines all gateway policy or assumes every company wants blocking.

**Closes:** [GAP-01](gap-analysis.md#gap-01-privacy-configuration-assurance-for-small-teams), if its specific need and underserved tests are validated.

For an IT team controlling which conversation text reaches a provider, gateway7 proposes an inspectable privacy-plugin configuration with explicit supported fields, processing stages and failure behavior. Its potential benefit is easier verification of one selected workflow. Local redaction and guardrails already exist in the alternatives.

**What we would build:** A trusted example plugin masks a synthetic phone-number pattern before forwarding. The later plugin contract covers both request and response hooks, with documented configured actions such as allow, mask, block or log. Tests use a fake upstream and synthetic text. Metadata-only diagnostic logging is a proposed default; customer-specific logging is configurable and requires its own data-handling review. Fail-closed handling is a proposed option to validate, not a Customer-approved universal policy.

**What it costs:** Processing adds latency; blocking reduces availability; masking can remove useful context. A simple digit-pattern demonstration is not a PII detector or a compliance guarantee. Supported text fields, streaming, tools and attachments require explicit decisions before implementation.

**How a competitor would respond:** LiteLLM can package an equivalent configuration around existing local filters and hooks; Portkey and Kong can guide users through their existing guardrails. If configuration or an extension meets the workflow more cheaply, building a separate gateway has not earned its place. See [ALT-01, ALT-03 and ALT-04](alternatives.md).

**Validation:** Compare the same synthetic request, response and failure cases in the closest configured alternative. Record coverage, mistakes and explanation effort before setting any performance or usability target.

## VP-02: Testable domain-filter extensions

**Revision:** Retain domain filters as a concrete extension task while making the contract suitable for the wider plugin-host direction. The Customer's examples also included access control, token accounting and organization-specific logging; they are scope examples, not a promise to implement all of them in MVP-0.

**Closes:** [GAP-02](gap-analysis.md#gap-02-verifiable-domain-filter-changes), if validated.

For corporate developers who maintain organization-specific rules, gateway7 proposes a small documented plugin contract, a worked example and synthetic regression fixtures so changes can be reviewed without sending real data to an LLM. The proposed distinction is the author-and-check workflow, not the existence of plugins, regexes or AI-assisted development.

**What we would build:** Request and response hook contracts, deterministic ordering, configuration validation and explicit exception behavior. Trusted plugins are loaded at startup; installing or changing one can require a restart. Focused instructions and an example should let a coding agent find the contract without loading the whole codebase. An offline fixture runner is a team proposal to evaluate, not a mandatory testing regime imposed on all plugin authors.

**What it costs:** Stable interfaces and examples need maintenance; fixtures miss realistic cases; restarts interrupt service. Trusted Python plugins execute server-side code and are not an untrusted-code sandbox. A short contract can limit plugin flexibility.

**How a competitor would respond:** LiteLLM users can write custom guardrails and tests; Presidio users can package recognizers and evaluation scripts. These baselines may already satisfy the need. A focused guide or extension could be the better outcome. See [ALT-02 and ALT-03](alternatives.md).

**Validation:** Have another developer implement one synthetic filter without editing the core, exercise positive, negative and exception cases, then repeat with the closest existing alternative. Record effort and mistakes. Keep API/security guarantees distinct from the quality of any generated plugin.

## Proposed MVP and boundaries

The following stages separate the meeting's first runnable example from the broader direction:

- **MVP-0 discussed at kickoff:** one-provider proxy; provider key configured on the server, for example through an uncommitted `.env`; one simple phone-number masking plugin; forwarding and returning the result. The estimate was two to three weeks after the kickoff, preceded by CI and linter setup, not delivery for Assignment 1.
- **Broader Customer direction:** client authentication and operator-held provider keys; request hooks first, response hooks second, routing third. Claude and Gemini were acceptable initial provider targets; broad provider coverage was not required. Users' own keys were discussed only as an optional operator-disableable feature.
- **Plugin lifecycle:** startup loading and restart on plugin installation are acceptable; hot loading is not required. Plugin-authoring guidance for coding agents is a nice-to-have.
- **Still to decide:** the exact client API, first provider, key-storage approach, streaming/tool/multimodal support, precise failure and logging defaults, plugin-count limit and latency budget. These are not settled by calling the system “OpenAI-compatible” or “secure.”
- **Proposed limits:** trusted plugins, no marketplace or untrusted-code sandbox, no complete enterprise-gateway replacement. Complex routing and full token-accounting/access-control feature sets can follow the first runnable milestone.

Assignment 1 is research-only. No gateway prototype is included or needed to complete this week's research deliverables.

## Assumptions

| Assumption | Supports | Current evidence / status | How and when to check |
| --- | --- | --- | --- |
| Corporate IT teams need easy organization-specific extensions | GAP-02, VP-02 | Customer-supported direction in the [kickoff](../../reports/week-01/meeting-report.md#summary); not a market study | Obtain one concrete workflow and current integration cost in the next alignment |
| A narrower privacy-plugin setup reduces verification mistakes | GAP-01, VP-01 | Unvalidated; ALT-03 already offers local filters and extension hooks | Compare the same synthetic cases in Week 2 before claiming an advantage |
| A concise contract, example and offline fixtures improve plugin changes | GAP-02, VP-02 | Agent-focused documentation was welcomed as a nice-to-have; the combined workflow is untested | Another developer performs the same change on gateway7 and the baseline during Week 2 planning/experiments |
| A one-provider masking proxy is a useful first runnable milestone | VP-01, VP-02 | Proposed by azamatbayramov at kickoff; not contested; two-to-three-week estimate | Split into owned work and review the estimate during Week 2 planning |
| Streaming, tools and attachments can initially be excluded | VP-01 | Unanswered at kickoff | Present explicit exclusions in the next Customer alignment before implementation |
| The chosen key-storage, error and logging policies meet the workflow | VP-01, VP-02 | Server-held keys preferred; storage/security details and budgets unresolved | Document trade-offs and obtain scope agreement in Week 2 |
| The simple architecture has an acceptable plugin-count limit | VP-02 | Customer requested an explicit limit; no numeric target agreed | State assumptions, test a synthetic chain after implementation, and report the measured boundary |
| Python is the final team choice | VP-02 | Working proposal; Python and Go accepted at kickoff | Confirm the team's choice and setup in Week 2; do not claim a delivered implementation |
