# Gap Analysis

**Status, 2026-10-03:** Customer-confirmed project need; two candidate competitive gaps. At the [October 2 kickoff](../../reports/week-01/meeting-report.md#decisions), the Customer confirmed a corporate plugin host in which a company's IT department can build or replace request and response plugins and choose policy actions. Privacy filtering is one use case. The narrower privacy-assurance and policy-review proposals below remain hypotheses: the recorded meeting did not establish their specific workflow benefits or show that the alternatives serve them poorly.

## GAP-01: Privacy-configuration assurance for small teams

**Evidence:** “Filtering effectiveness depends on request coverage, hook timing, service boundaries, and configuration, rather than the presence of a ‘guardrail’ checkbox.” [PAT-02](comparison.md#whole-table-patterns), P2/P3/P7; ALT-01 O2–O3, ALT-02 O4, ALT-03 O2–O3, ALT-04 O1–O3 in [the observations](alternatives.md).

**Hypothesis:** A small application team may need a narrow, locally inspectable text-gateway setup with explicit coverage and failure behavior more than a large set of optional policies.

| Required test | Current assessment | Evidence or next check |
| --- | --- | --- |
| Someone needs it | Confirmed at the broader project level: corporate IT teams need company-controlled request and response policies. The narrower small-team privacy-assurance need is not yet established | [Kickoff notes](../../reports/week-01/meeting-notes.md#discussion-in-chronological-order) establish the plugin-host direction; identify one privacy workflow, its current difficulty, sensitive fields and failure consequences before treating GAP-01's specific need as validated |
| Alternatives do not serve it | Unproven: ALT-03 already documents local Presidio integration, pre-call masking and default-on enforcement (O2/O3/O6). Inference: any remaining opportunity concerns Customer-specific configuration assurance | Map one Customer workflow to the supported configuration, including input fields, timing, detector errors and logs; retain only an evidenced unmet requirement or material setup burden, and abandon this gap if configuration meets the job |
| It is reachable | Plausible: package a mandatory local preflight that checks supported text fields before forwarding and rejects unsupported inputs or failed checks | Write an explicit allow/mask/block/error contract and data-flow diagram |
| Buildable by 3–4 in this course | Plausible only with narrow scope | One endpoint, two provider adapters, deterministic fixtures, no streaming or attachments in the first version; review estimate with Customer |

**Proposed evidence of value:** A new user can identify exactly which fields are checked, observe that a detector timeout causes zero upstream calls, and verify that default logs contain no fixture values. Establish baseline results first; no timing or accuracy advantage is claimed yet.

## GAP-02: Verifiable domain-filter changes

**Evidence:** “Existing components expose extension points and decision information, but assembling and validating a domain policy remains integration work.” [PAT-03](comparison.md#whole-table-patterns), P4/P6/P7; ALT-01 O3–O4, ALT-02 O2–O5, ALT-03 O3–O4, ALT-04 O2–O3 in [the observations](alternatives.md).

**Hypothesis:** Developers maintaining organization-specific identifier rules may value a small contract and synthetic regression report that make plugin changes reviewable without needing live provider calls.

| Required test | Current assessment | Evidence or next check |
| --- | --- | --- |
| Someone needs it | Confirmed at the broader project level: a company's IT department needs to build or replace its own plugins. The proposed offline domain-filter review workflow is not yet established | [Kickoff notes](../../reports/week-01/meeting-notes.md#discussion-in-chronological-order) establish company-authored plugins; obtain one realistic rule, benign look-alikes and the current change-review process before treating GAP-02's specific benefit as validated |
| Alternatives do not serve it | Unproven: ALT-02 supplies recognizer evaluation and synthetic datasets (O6); ALT-03 supplies custom hooks, execution records and mocked LLM calls (O3/O6). Inference: any remaining opportunity concerns a combined policy-review workflow | For one Customer rule and benign look-alikes, assess whether existing tools provide the reviewer's required before/after decisions, rule identity and error behavior; prefer a preset or integration if sufficient, and retain only a concrete unmet review requirement |
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

Keep the Customer-confirmed plugin-host need as the project direction. Before calling GAP-01 or GAP-02 a validated competitive gap, record a concrete workflow and its current difficulty, then compare the closest alternative using documentation or source evidence. Use a controlled synthetic check later where behavior remains uncertain. The [value propositions](value-proposition.md) distinguish the confirmed broader need from the proposed privacy and extension workflows. If an existing gateway plus configuration satisfies the job, prefer extension or integration. Record new Customer decisions in a subsequent meeting report rather than attributing them to the kickoff.

Documentation or source comparison can establish or reject specific capability claims; the synthetic checks above are proposed follow-up validation, not a [Week 1 implementation requirement](https://github.com/inno-itpd/itpd/blob/main/assignments/assignment-1.md#assignment-1-initial-project-research).
