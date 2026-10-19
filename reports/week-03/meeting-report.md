# Week 03 customer meeting report

## Metadata

- **Status:** Retrospective account from the supplied transcript; participant review of this paraphrase and follow-up assignments remains pending.
- **Date:** 2026-10-16, derived from the supplied file's date and consistent with the prepared meeting script; not stated aloud in the transcript.
- **Duration:** Approximately 46 minutes across both teams; the Gateway7 presentation and feedback occupied approximately the first 23 minutes.
- **Attended:** Evidenced speakers were azamatbayramov, Customer and a presenter from another project team. The transcript does not establish the complete attendance roster or the other presenter's GitHub username.
- **Presented:** Python/FastAPI architecture diagrams, a running gateway with a mock HTTP upstream, one phone-masking example, YAML plugin configuration and the Python descriptor/hook interface.
- **Recording permission:** Customer announced recording; no separate question and answer granting recording permission is captured.
- **Public transcript permission:** Customer referred to a public transcript and later said it would be shared. A separate answer authorizing publication in this repository is not captured, so repository publication is not assumed.
- **Private sharing permission:** No separate permission question and answer is captured. The contributor supplied the transcript privately for this report; submission to instructors is not established.
- **Transcript:** None published. The supplied source remains private; this report contains sanitized paraphrases only, without recording links or timecodes.
- **Script:** [Prepared Week 03 script](meeting-script.md). The actual discussion did not follow its planned AC-by-AC validation and verdict questions.

## Previous action points

| Action | Outcome | Decision |
| --- | --- | --- |
| [reports/week-02/meeting-report.md#action-points](../week-02/meeting-report.md#action-points): "Present the technical architecture, including organization of the core and plugin integration" | Carried out: azamatbayramov presented the core, provider adapter, plugin chains, configuration and hooks. Customer requested deeper treatment of execution, diagnosis and failures. [Architecture follow-up](../../docs/architecture/README.md#review-questions-and-week-2-follow-up) records the remaining work; implementation was tracked in [task #50](https://github.com/iteam7/gateway7/issues/50). Presentation is not architecture acceptance. | [DEC-014](../../docs/decisions.md#dec-014). |
| [reports/week-02/meeting-report.md#action-points](../week-02/meeting-report.md#action-points): "Present a more technical prototype showing system/code structure beyond masking behavior" | Carried out: a request was sent through the Python gateway to a mock upstream; the presenter inspected masked content and showed configuration and plugin code. Customer requested multiple interacting plugins. [Demo follow-up](../../docs/demo.md#customer-feedback-follow-up) records that request; implementation was tracked in [task #52](https://github.com/iteam7/gateway7/issues/52). | [DEC-015](../../docs/decisions.md#dec-015). |
| [reports/week-02/meeting-report.md#action-points](../week-02/meeting-report.md#action-points): "Confirm completion or remaining scope of the infrastructure action carried from Week 1" | No explicit infrastructure review or closing outcome was captured. Existing [repository evidence](README.md#repository-evidence) describes CI, but does not establish a meeting verdict. The confirmation action is carried forward below. | None. |

## Previous open questions

| Question | Answer | Decision |
| --- | --- | --- |
| [reports/week-02/meeting-report.md#open-questions](../week-02/meeting-report.md#open-questions): "What is the upper limit of plugins running at once in our architecture, and what slows down past it?" | Unanswered. Customer's three-plugin example is a demonstration size, not a capacity ceiling. Remains open below. | None. |
| [reports/week-02/meeting-report.md#open-questions](../week-02/meeting-report.md#open-questions): "Python or Go for the gateway?" | Answered by the team's earlier Python selection, which the running implementation used. This was not a new Customer stack decision. | [DEC-013](../../docs/decisions.md#dec-013). |
| [reports/week-02/meeting-report.md#open-questions](../week-02/meeting-report.md#open-questions): "Do provider keys live in the gateway's configuration or in an external secret manager?" | Unanswered. The demonstration did not settle deployment secret storage; [CON-04](../../docs/product-vision.md#con-04) remains unchanged. | None. |
| [reports/week-02/meeting-report.md#open-questions](../week-02/meeting-report.md#open-questions): "What exact plugin contract, ordering and loading rules should gateway7 use?" | YAML instance names, per-plugin settings, explicit chains and Python hooks were explained. Customer said the interface was clearer, but requested execution/error rationale and debugging detail. The [existing contract](../../docs/plugins.md) remains a team implementation pending further validation. | [DEC-014](../../docs/decisions.md#dec-014), [DEC-015](../../docs/decisions.md#dec-015). |
| [reports/week-02/meeting-report.md#open-questions](../week-02/meeting-report.md#open-questions): "How should the initial deterministic demo exercise the accepted candidate while keeping real-provider criteria for the later integrated build?" | A mock upstream and one masking plugin were shown. Customer requested three interacting plugins; the actual-provider criterion was not tested or removed. The [demo](../../docs/demo.md#customer-feedback-follow-up) now records this next validation target. | [DEC-015](../../docs/decisions.md#dec-015); existing [DEC-011](../../docs/decisions.md#dec-011) still applies. |
| [reports/week-02/meeting-report.md#open-questions](../week-02/meeting-report.md#open-questions): "What exact calendar date is the following-week presentation?" | The supplied record establishes that the presentation occurred on 16 October, subject to the date-source limitation in Metadata. This closes the retrospective scheduling question without inventing an earlier agreement. | None. |

## Summary

- Customer asked for the architecture's operational detail: identify a failed or hanging plugin, explain timing and progress through the chain, and show how exceptions are handled. The high-level flow alone did not answer those questions.
- Django middleware and Twisted callback/error handling were suggested as examples to investigate. Customer left the design choice to the team and asked it to explain the trade-offs; neither framework was selected in the meeting.
- The running Python prototype demonstrated one phone-masking path to a mock upstream. Customer asked for three interacting plugins and a clear way to author, configure and run them; one plugin was considered too trivial to validate composition.
- The YAML and Python interface walkthrough made the extension mechanism clearer to Customer. This positive response did not accept an implemented story or settle the outstanding failure/lifecycle questions.
- [DEC-012](../../docs/decisions.md#dec-012) defines the candidate as US-01, US-02 and US-03. No AC-by-AC acceptance/rejection or candidate removal was recorded. The later presentation belonged to another team; its proposed implementation and scheduling commitments are not Gateway7 decisions.

The following table separates story evidence from Customer verdicts.

| Candidate story | What the supplied record establishes | Customer verdict |
| --- | --- | --- |
| [US-01](https://github.com/iteam7/gateway7/issues/30) | Gateway-to-mock traffic was demonstrated, but AC-01's exact response/key conditions were not individually assessed. AC-02–04 key forwarding, missing-key startup and leak checks were not walked through. No real Claude/Gemini AC-05 call was shown. | Not recorded; no acceptance/rejection DEC exists. |
| [US-02](https://github.com/iteam7/gateway7/issues/31) | One phone-masking example was inspected upstream. The transcript does not establish AC-01's three exact fixtures or the AC-02 history and AC-03 unchanged-text checks. | Not recorded; no acceptance/rejection DEC exists. |
| [US-03](https://github.com/iteam7/gateway7/issues/32) | Configuration, order and descriptor/hooks were explained. AC-01's file/config-only restart, AC-02 missing-module failure and AC-03 two-plugin marker order were not demonstrated as acceptance checks. | Not recorded; no acceptance/rejection DEC exists. |

The story mapping above is a report analysis against the existing issues; the speakers did not identify these demonstrations by US/AC number.
Repository tests remain separate evidence and cannot supply a missing Customer verdict.
No story is closed or removed by this report, and no verdict is inferred for US-04–09.

## Decisions

- [DEC-014: Explain plugin execution, failure handling and diagnosis, and justify the chosen architecture against alternatives.](../../docs/decisions.md#dec-014)
- [DEC-015: Use three interacting plugins and a clear authoring/configuration walkthrough for the next usable demonstration.](../../docs/decisions.md#dec-015)

These are directions for the next validation, not story acceptance or approval of a specific middleware framework.

## Action points

The first two actions follow Customer's requests. The Week 4 dates and presenter nominations below are proposals for participant review, not assignments agreed during the meeting; implementation owners remain unassigned.
The third carries the existing infrastructure owner forward without inventing a renewed commitment.
Consequently, agreed owners and dates remain an open requirement.

| Action | Owner | Due |
| --- | --- | --- |
| Present three interacting plugins with observable input/output effects and the steps for adding and configuring another plugin, following DEC-015. | azamatbayramov, proposed presenter based on the previous presentation role; confirmation required | Proposed 2026-10-23, inside Week 4; not agreed in the meeting |
| Present the runner's execution, timing, failure and diagnosis approach, compare relevant middleware patterns, and explain the selected trade-offs, following DEC-014. | azamatbayramov, proposed presenter; implementation ownership to be agreed by the team | Proposed 2026-10-23, inside Week 4; not agreed in the meeting |
| Confirm the completed infrastructure scope and identify any remaining CI/linter work from the carried Week 1 action. | azamatbayramov, existing post-kickoff owner; no renewed commitment recorded | Proposed 2026-10-23, inside Week 4; confirmation required |

## Open questions

| Question | What it would change | Follow-up |
| --- | --- | --- |
| What is the supported plugin/concurrency limit, and which work dominates latency? | Capacity claims and execution design | Measure representative plugin chains before setting a limit. |
| Should deployment provider keys come from server environment/configuration or an external secret manager? | Setup and deployment scope | Present options under CON-04 and obtain a decision. |
| Which execution/error model and diagnostic evidence will satisfy Customer? | Runner design and observability work | Compare alternatives and demonstrate failure cases under DEC-014; do not infer that Django or Twisted was chosen. |
| Do US-01, US-02 and US-03 satisfy their existing ACs, including the actual-provider check? | Story acceptance and remaining MLS-03 work | Run each AC and request explicit Customer verdicts; record genuine verdict DECs and story comments then. |
| Who will implement and present the requested follow-ups, and on which agreed dates? | Week 4 assignments and delivery commitments | Confirm the proposed actions with the team; schedule task issues without treating these nominations as accepted assignments. |
| What publication/private-submission permissions apply to this meeting's transcript? | Location of required transcript evidence | Confirm the per-meeting permission answers and instructor-access route with a participant and Customer. |

## Disagreements

| Your position | Customer's position | What you changed |
| --- | --- | --- |
| The component and request-flow diagrams were the initial architecture explanation. | The difficult design choices were hidden inside the plugin runner: failures, hangs, diagnosis and trade-offs needed explanation. | Added the DEC-014 review target to the [architecture follow-up](../../docs/architecture/README.md#review-questions-and-week-2-follow-up) and [SPRINT-04](../../docs/project-plan.md#sprint-04); no unreviewed runtime change is claimed. |
| One masking plugin illustrated the running prototype. | A usable demonstration should show about three plugins working together and make authoring/configuration clear. | Recorded DEC-015 in the [demo follow-up](../../docs/demo.md#customer-feedback-follow-up) and SPRINT-04 plan. Completion of that stronger demonstration still needs evidence. |
