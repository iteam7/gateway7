# Week 02 prototypes

**Evidence-backed draft; public prototype views and acceptance of the redesign remain pending.**
The meeting report is a factual paraphrase of the supplied private transcript; that transcript is not published by this change.

## Phone-masking behavior prototype shown at the meeting

- **What it is:** A local HTML/CSS/JavaScript behavior simulation showing phone-number replacement, stable placeholders for repeated values, distinct placeholders for different values, and unchanged text when no number is present. It was explicitly presented as neither a real proxy nor an LLM integration.
- **View:** Pending. No genuine sanitized screenshot of the exact version shown at the meeting is available in this change. The later redesigned simulator must not be substituted as evidence of what the Customer saw.
- **Tested:** Behavior related to [US-02](https://github.com/iteam7/gateway7/issues/31), but the issue ID and exact acceptance-criteria fixture set were not presented. No actual fake-upstream request or production detector result was demonstrated, so no story AC pass is claimed.
- **Question:** Would the masking behavior communicate the proposed system logic adequately for validation? This is the team's retrospective description of the demonstration's purpose, not a claimed verbatim pre-meeting question.
- **What the customer said:** The Customer expected an architectural approach centered on extensibility: how plugins fit, what enters and leaves a plugin, how messages move between plugins, and how to add them. Specific phone-number replacement was not the main problem. See the [meeting summary](meeting-report.md#summary).
- **What changed:** [DEC-009](../../docs/decisions.md#dec-009) redirects validation to the plugin-host architecture and integration workflow. The preparation was redesigned as described below; the [follow-up script](meeting-script.md) tests the missing lifecycle and interface. The current story bundle remains a proposal requiring revision and an explicit verdict.

## Architecture and plugin lifecycle simulator prepared afterwards

- **What it is:** An English interactive architecture simulator showing caller → gateway core → request hooks → provider adapter → simulated provider → response hooks → caller, plus plugin registration, configuration order and restart activation. It is a disposable flow prototype, not a running gateway, implemented plugin host or technical proof of provider integration. Python contract/plugin/registry snippets are illustrative and are not executed by the simulator.
- **View:** Pending public evidence. The hosted simulator is owner-only and is not a grader-accessible view-only artifact. Browser rendering was blocked during preparation, so no screenshots are claimed or attached. Before submission, capture genuine sanitized screenshots in `reports/week-02/images/` of request/response trace inspection and registration/configuration/restart activation. Use synthetic examples only.
- **Tested:** Intended follow-up target: [US-03](https://github.com/iteam7/gateway7/issues/32), especially AC-01's registration/restart boundary and AC-03's configured order; secondary examples concern [US-01](https://github.com/iteam7/gateway7/issues/30) forwarding and [US-02](https://github.com/iteam7/gateway7/issues/31) masking. This exercises concepts, not real HTTP/filesystem/provider-key acceptance criteria. Missing-plugin startup failure (US-03 AC-02), real-provider integration (US-01 AC-05) and US-02's exact token/fixture contract are not established. The risky assumption is that the core/plugin split fits team capacity; [the assumption log](../../docs/assumptions.md) has no stable identifier for it yet, so the required `ASM-nn` citation remains pending.
- **Question:** Can a company plugin author explain where request/response hooks run, add a plugin without changing core logic, and predict when configuration changes take effect after restart?
- **What the customer said:** The transcript does not show this redesigned simulator being presented. Its trigger was the Customer's architectural feedback on the earlier behavior prototype, not approval of this redesign. Customer evaluation of the proposed hook semantics, ordering, failure policy and registration mechanism remains pending.
- **What changed:** Preparation now demonstrates the architecture and lifecycle requested by [DEC-009](../../docs/decisions.md#dec-009), and makes the restart boundary confirmed by [DEC-010](../../docs/decisions.md#dec-010) explicit. [DEC-011](../../docs/decisions.md#dec-011) supports a deterministic upstream for the future usable demo; this browser simulation alone does not establish fulfillment of the team's promised technical/code-structure prototype, and it is not a usable gateway MUP. The [candidate update](README.md#minimum-usable-product-candidate) records the revised demonstration scope and unresolved story mapping.

## Preparation checks and limits

The canonical redesigned simulator HTML has SHA-256 `25ca68824b389ea2153755ca5cfd05b6310f30d7bcc9867c4467672ddd131988`.
On 10 October, 21 functional checks passed against its actual inline JavaScript in a minimal DOM harness.
They covered hook order, registration/restart, reordered/disabled plugins, block/error paths, stepping, reset and text-only synthetic-data handling.
They do not verify browser layout, mobile rendering, customer usability, actual gateway implementation or production security.
The masking heuristic has known false positives and negatives; the four-plugin demo catalog is not a measured capacity limit.
No prototype HTML, test source or executable product code is included in this documentation change.
