# Gap Analysis

**Status, 2026-10-03:** Candidate gaps, not validated market gaps. The [October 2 kickoff](../../reports/week-01/meeting-report.md#summary) happened and changed the framing: corporate IT teams should be able to add or replace plugins for requests and responses; privacy filtering is one example. The Customer explicitly acknowledged existing gateways. That supports investigating an extensibility workflow, not claiming that competitors cannot do it. Alternatives have not been tested under the same workload, so the required “alternatives do not serve it” test remains unresolved.

The original `GAP-01` and `GAP-02` identifiers are retained. Their narrower privacy use cases now sit inside the plugin-host direction rather than defining the whole product. This dated revision does not claim that our written propositions were presented or endorsed at the meeting.

## GAP-01: Privacy-configuration assurance for small teams

**Evidence:** “Filtering effectiveness depends on request coverage, hook timing, service boundaries, and configuration, rather than the presence of a ‘guardrail’ checkbox.” [PAT-02](comparison.md#whole-table-patterns), P2/P3/P7; ALT-01 O2–O3, ALT-02 O4, ALT-03 O2–O3, ALT-04 O1–O3 in [the observations](alternatives.md).

**Hypothesis, revised after kickoff:** The IT team deploying a corporate gateway may need a locally inspectable privacy-plugin configuration with explicit coverage and failure behavior. The original small-application-team segment was not established; this remains one workflow within a broader plugin host.

| Required test | Current assessment | Evidence or next check |
| --- | --- | --- |
| Someone needs it | Partly supported: Customer named corporate access control, code fingerprinting and organization-specific logging; no concrete privacy-policy workflow was validated | [Kickoff summary and disagreements](../../reports/week-01/meeting-report.md); obtain synthetic examples and existing-control details in follow-up |
| Alternatives do not serve it | Unproven: documented caveats create configuration choices, but LiteLLM and other gateways can potentially be configured to meet the requirement | Compare setup and failure handling for the same synthetic scenario; abandon this gap if a supported preset is sufficient |
| It is reachable | Plausible: provide a privacy plugin that checks specified text fields and has an explicit configured action | Define request and response hooks plus allow/mask/block/log/error behavior; do not impose one policy choice on every corporate workflow |
| Buildable by 3–4 in this course | Plausible only with narrow scope | First runnable milestone: one provider and one simple masking plugin; request/response hooks and Claude/Gemini support are staged goals. The meeting estimate was two to three weeks, not delivery during Assignment 1 |

**Proposed evidence of value:** A new user can identify exactly which fields are checked, verify the selected error policy (including zero upstream calls for a blocking configuration), and verify that default diagnostic logs contain no fixture values. Establish baseline results first; no timing or accuracy advantage is claimed yet.

## GAP-02: Verifiable domain-filter changes

**Evidence:** “Existing components expose extension points and decision information, but assembling and validating a domain policy remains integration work.” [PAT-03](comparison.md#whole-table-patterns), P4/P6/P7; ALT-01 O3–O4, ALT-02 O2–O5, ALT-03 O3–O4, ALT-04 O2–O3 in [the observations](alternatives.md).

**Hypothesis, revised after kickoff:** Corporate developers maintaining organization-specific filters may value a small plugin contract, focused authoring instructions and synthetic regression reports. The Customer supported easy plugin creation and called coding-agent instructions a nice-to-have; a comparative workflow advantage remains unmeasured.

| Required test | Current assessment | Evidence or next check |
| --- | --- | --- |
| Someone needs it | Customer-supported direction: IT departments adapt their own policy and logging plugins; precise filter-review needs remain unvalidated | [Kickoff decisions](../../reports/week-01/meeting-report.md#decisions); obtain a fictional identifier, benign examples and the policy-approval workflow |
| Alternatives do not serve it | Unproven: custom hooks, recognizers and traces already exist | Evaluate whether a preset/test helper for LiteLLM or Presidio meets the job more cheaply; this may become a reuse project |
| It is reachable | Plausible: add a versioned filter interface and offline fixture runner reporting rule IDs, actions and expected-versus-actual outcomes | Define plugin inputs, outputs, errors, ordering and compatibility checks |
| Buildable by 3–4 in this course | Plausible for trusted plugins and a limited text policy | Two sample plugins and a local CLI/report; no plugin marketplace, untrusted-code sandbox or automatic policy synthesis |

**Proposed evidence of value:** A sample domain filter can be added without editing the core, passes synthetic positive/negative cases, and follows its documented configured failure behavior after a plugin error. Tests prove the stated contract for those fixtures, not universal PII detection.

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

The [value propositions](value-proposition.md) now reflect the recorded plugin-host direction. Before calling these validated gaps, obtain a concrete Customer workflow and test the closest configured alternative. If an existing gateway plus configuration satisfies the workflow, prefer extension or integration over claiming a nonexistent market gap. Record that decision and any disagreement in the meeting report.
