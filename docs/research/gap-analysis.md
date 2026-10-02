# Gap Analysis

**Status, 2026-09-30:** Candidate gaps, not validated gaps. Documentation supports the trade-offs below, but the Customer meeting has not happened and alternatives have not been tested under the same workload. In particular, the required “alternatives do not serve it” test is unresolved. Keeping this limitation explicit is more defensible than inventing an absence of competitor capabilities.

## GAP-01: Privacy-configuration assurance for small teams

**Evidence:** “Filtering effectiveness depends on request coverage, hook timing, service boundaries, and configuration, rather than the presence of a ‘guardrail’ checkbox.” [PAT-02](comparison.md#whole-table-patterns), P2/P3/P7; ALT-01 O2–O3, ALT-02 O4, ALT-03 O2–O3, ALT-04 O1–O3 in [the observations](alternatives.md).

**Hypothesis:** A small application team may need a narrow, locally inspectable text-gateway setup with explicit coverage and failure behavior more than a large set of optional policies.

| Required test | Current assessment | Evidence or next check |
| --- | --- | --- |
| Someone needs it | Unvalidated: developer responsible for preventing accidental disclosure in multi-turn LLM requests | Ask Customer about a specific workflow, sensitive fields, failure consequences and existing controls; do not assume regulated deployment |
| Alternatives do not serve it | Unproven: documented caveats create configuration choices, but LiteLLM and other gateways can potentially be configured to meet the requirement | Compare setup and failure handling for the same synthetic scenario; abandon this gap if a supported preset is sufficient |
| It is reachable | Plausible: package a mandatory local preflight that checks supported text fields before forwarding and rejects unsupported inputs or failed checks | Write an explicit allow/mask/block/error contract and data-flow diagram |
| Buildable by 3–4 in this course | Plausible only with narrow scope | One endpoint, two provider adapters, deterministic fixtures, no streaming or attachments in the first version; review estimate with Customer |

**Proposed evidence of value:** A new user can identify exactly which fields are checked, observe that a detector timeout causes zero upstream calls, and verify that default logs contain no fixture values. Establish baseline results first; no timing or accuracy advantage is claimed yet.

## GAP-02: Verifiable domain-filter changes

**Evidence:** “Existing components expose extension points and decision information, but assembling and validating a domain policy remains integration work.” [PAT-03](comparison.md#whole-table-patterns), P4/P6/P7; ALT-01 O3–O4, ALT-02 O2–O5, ALT-03 O3–O4, ALT-04 O2–O3 in [the observations](alternatives.md).

**Hypothesis:** Developers maintaining organization-specific identifier rules may value a small contract and synthetic regression report that make plugin changes reviewable without needing live provider calls.

| Required test | Current assessment | Evidence or next check |
| --- | --- | --- |
| Someone needs it | Unvalidated: developer who changes domain filters and must explain effects to an application owner | Ask Customer for a realistic identifier pattern, benign look-alikes, and who approves policy changes |
| Alternatives do not serve it | Unproven: custom hooks, recognizers and traces already exist | Evaluate whether a preset/test helper for LiteLLM or Presidio meets the job more cheaply; this may become a reuse project |
| It is reachable | Plausible: add a versioned filter interface and offline fixture runner reporting rule IDs, actions and expected-versus-actual outcomes | Define plugin inputs, outputs, errors, ordering and compatibility checks |
| Buildable by 3–4 in this course | Plausible for trusted plugins and a limited text policy | Two sample plugins and a local CLI/report; no plugin marketplace, untrusted-code sandbox or automatic policy synthesis |

**Proposed evidence of value:** A sample domain filter can be added without editing the core, passes synthetic positive/negative cases, and cannot silently bypass mandatory filtering after a plugin error. Tests prove the stated contract for those fixtures, not universal PII detection.

## Rejected gaps

| Candidate | Related pattern | Why rejected or deferred |
| --- | --- | --- |
| No alternative offers local PII filtering | PAT-01 | Contradicted by ALT-02, ALT-03 and ALT-04 deployment observations |
| No alternative supports custom patterns or plugins | PAT-01 | Contradicted by all four alternatives; Portkey explicitly documents BASIC regex redaction |
| No alternative explains filtering decisions | PAT-03 | Contradicted by documented result/tracing facilities; GAP-02 concerns workflow validation, not invention of explanations |
| No alternative restores masked information | PAT-01 | Contradicted by ALT-03 and ALT-04; restoration also creates sensitive-state handling costs |
| Build a complete enterprise gateway replacement | PAT-04 | Provider breadth, governance and operational maturity exceed the proposed course scope |
| Guarantee detection of all sensitive information | PAT-04 | Unsupported by evidence; automated detection has false positives and false negatives |
| Be faster, cheaper or easier than every competitor | PAT-04 | No controlled benchmark, deployment-cost model or usability study supports this claim |

## Decision gate

Before calling these validated gaps, obtain the Customer's workflow and requirements, revise the [value propositions](value-proposition.md), and test the closest alternative. If an existing gateway plus configuration satisfies the workflow, prefer extension or integration over claiming a nonexistent market gap. Record that decision and any disagreement in the meeting report.
