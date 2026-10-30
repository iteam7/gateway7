# Week 05 Customer meeting report

## Metadata

- **Status:** Account of the supplied meeting record; participant review and explicit story verdicts remain outstanding.
- **Date:** 2026-10-30, from the supplied recording's filename; not stated aloud.
- **Duration:** Approximately 29 minutes for Gateway7 within a shared meeting of approximately 56 minutes.
- **Attended:** Evidenced Gateway7 speakers were azamatbayramov and Customer; the shared meeting also included another project team. The complete attendance roster is not established.
- **Presented:** A local gateway, OpenAI-compatible HTTP endpoints, provider and plugin configuration, Python middleware, documentation and architecture, an OpenAI request reported as HTTP 200, and Prometheus/Grafana outcomes, durations and token metrics.
- **Environment:** azamatbayramov demonstrated locally because he was outside the university network. This explains the demonstration's location; it does not establish VM unavailability or waive the production-review requirement.
- **Recording permission:** Customer announced recording; a separate permission question and answer is not captured.
- **Public transcript permission:** No explicit permission to publish this meeting's sanitized transcript is captured; publication is not assumed.
- **Private sharing permission:** No separate permission answer is captured; the supplied source is private, and instructor sharing still needs confirmation.
- **Transcript:** None published. The contributor supplied the source privately; this report contains sanitized paraphrases without personal names, recording links or timecodes.
- **Script:** [Prepared Week 05 script](meeting-script.md), preserved as preparation rather than rewritten to match the subsequent meeting. Its unfilled arrangements and roles do not prove that those steps occurred.

## Previous action points

No Week 4 Customer meeting took place, so there is no Week 4 meeting report to reconstruct.
The following rows follow the still-open Week 3 actions instead.

| Action | Outcome | Decision |
| --- | --- | --- |
| [reports/week-03/meeting-report.md#action-points](../week-03/meeting-report.md#action-points): "Present three interacting plugins with observable input/output effects and the steps for adding and configuring another plugin, following DEC-015." | Partly carried out: multiple email/phone/policy plugins, YAML settings, Python modules and authoring documentation were explained. The source does not establish a fresh company-plugin installation or exact composition AC checks; these remain in the next structured demonstration. [Task #130](https://github.com/iteam7/gateway7/issues/130) and [the demo guide](../../docs/demo.md) provide implementation evidence separately. | [DEC-018](../../docs/decisions.md#dec-018). |
| [reports/week-03/meeting-report.md#action-points](../week-03/meeting-report.md#action-points): "Present the runner's execution, timing, failure and diagnosis approach, compare relevant middleware patterns, and explain the selected trade-offs, following DEC-014." | Partly carried out: architecture, middleware and monitoring were discussed, and Customer praised plugin outcomes. A blocking function declared async remained an unanswered failure case; [task #157](https://github.com/iteam7/gateway7/issues/157) now tracks the promised investigation. | [DEC-019](../../docs/decisions.md#dec-019). |
| [reports/week-03/meeting-report.md#action-points](../week-03/meeting-report.md#action-points): "Confirm the completed infrastructure scope and identify any remaining CI/linter work from the carried Week 1 action." | No explicit closing review was captured. [Task #135](https://github.com/iteam7/gateway7/issues/135) supplies the CI/DoD work, but a green workflow is not the missing Customer confirmation. Carried forward below. | None. |

## Previous open questions

| Question | Answer | Decision |
| --- | --- | --- |
| [reports/week-03/meeting-report.md#open-questions](../week-03/meeting-report.md#open-questions): "What is the supported plugin/concurrency limit, and which work dominates latency?" | Not settled by the meeting. [The middleware benchmark](../../docs/demo.md#measure-local-middleware-overhead) measures local pipeline overhead, not a supported production capacity; the representative workload remains open. | None. |
| [reports/week-03/meeting-report.md#open-questions](../week-03/meeting-report.md#open-questions): "Should deployment provider keys come from server environment/configuration or an external secret manager?" | Not settled. The presenter used a server-held OpenAI key; no secret-manager decision was recorded. | None. |
| [reports/week-03/meeting-report.md#open-questions](../week-03/meeting-report.md#open-questions): "Which execution/error model and diagnostic evidence will satisfy Customer?" | Customer found monitoring useful but asked how synchronous or apparently async blocking code affects the gateway. The meeting established investigation work, not an isolation architecture or acceptance of every failure case. | [DEC-019](../../docs/decisions.md#dec-019). |
| [reports/week-03/meeting-report.md#open-questions](../week-03/meeting-report.md#open-questions): "Do US-01, US-02 and US-03 satisfy their existing ACs, including the actual-provider check?" | No named story verdict was recorded. An OpenAI request does not itself satisfy US-01 AC-05's current Claude/Gemini wording, and no criterion change was agreed. | None. |
| [reports/week-03/meeting-report.md#open-questions](../week-03/meeting-report.md#open-questions): "Who will implement and present the requested follow-ups, and on which agreed dates?" | azamatbayramov presented and promised a blocking-plugin backlog item. No full implementation-owner/date agreement was captured; the follow-up plan below is identified separately. | [DEC-019](../../docs/decisions.md#dec-019). |
| [reports/week-03/meeting-report.md#open-questions](../week-03/meeting-report.md#open-questions): "What publication/private-submission permissions apply to this meeting's transcript?" | Still unanswered for the earlier meeting. The new recording announcement and invitation to send short demonstrations do not supply either meeting's separate transcript permissions. | None. |

## Summary

- Real harness integration exposed an unsupported streaming requirement. Customer asked the team to connect interacting systems early, before further work hides integration risks; OpenCode was not connected in this demonstration.
- Customer praised monitoring and Docker Compose startup. Replaceable monitoring integration was suggested as an extension idea, with an explicit statement that keeping the current integration in the core was also acceptable.
- Customer asked what happens when plugin code blocks the event loop despite an async declaration. azamatbayramov committed to adding the investigation to the backlog; forced termination or process isolation was not selected.
- The next demonstration should bring three or four substantial use cases with visible GitHub stories and exact criteria, demonstrate the behavior, and request explicit verdicts. Customer welcomed questions and short recordings between meetings.
- No specific US/AC acceptance or rejection was captured. General positive feedback and an example of saying "I approve" are not mapped story verdicts; no acceptance DEC or story closure is created from them.

The presenter reported an HTTP 200 OpenAI answer consistent with email masking, but the supplied record does not establish the exact upstream payload or the phone/response fixtures in the existing stories.
The external provider dashboard did not visibly update during the discussion; the reason was not established.
No identified QRT result was read out or assessed in the supplied record, so later CI results must not be backdated as evidence shown in this meeting.

## Decisions

- [DEC-017: Try real harness integration early to expose compatibility requirements before extending the gateway further.](../../docs/decisions.md#dec-017)
- [DEC-018: Structure the next Customer demonstration around three or four substantial use cases with visible stories, exact criteria and explicit verdicts.](../../docs/decisions.md#dec-018)
- [DEC-019: Add an investigation of blocking plugin behavior and cooperative deadline limits to the backlog.](../../docs/decisions.md#dec-019)

These records describe integration and validation direction, not acceptance of implemented stories.

## Action points

The backlog commitment came from the meeting; [task #157](https://github.com/iteam7/gateway7/issues/157) was created while preparing this report.
The following Week 6 follow-ups are a plan prepared under azamatbayramov's instruction to complete [task #132](https://github.com/iteam7/gateway7/issues/132), not deadlines or assignments agreed by Customer during the call.
azamatbayramov coordinates them; implementation ownership and the proposed dates remain for participant confirmation.

| Action | Owner | Due |
| --- | --- | --- |
| Prepare three or four linked use-case demonstrations covering harness access, plugin installation/configuration, policy effects and diagnosis; request named story verdicts and record only the answers actually received. | azamatbayramov | Proposed 2026-11-06, inside Week 6 |
| Coordinate the blocking-plugin investigation in [task #157](https://github.com/iteam7/gateway7/issues/157), including event-loop responsiveness and the limits of cooperative timeouts, before choosing an implementation change. | azamatbayramov | Proposed 2026-11-06, inside Week 6 |
| Confirm the outstanding infrastructure action and obtain the unanswered capacity, secret-storage and transcript-permission decisions; retain unanswered items rather than close them by inference. | azamatbayramov | Proposed 2026-11-06, inside Week 6 |

## Open questions

| Question | What it would change | Follow-up |
| --- | --- | --- |
| Which demonstrated stories does Customer accept or reject against their current ACs? | Story closure, rework and actual velocity | Bring the exact issue wording and evidence; record genuine verdict DECs and issue comments. |
| Should US-01 AC-05 accept OpenAI as well as Claude/Gemini? | The live-provider acceptance check | Ask explicitly; keep the existing wording until agreed. |
| What behavior is required for a plugin that blocks the event loop or suppresses cancellation? | Plugin trust boundary, execution design and timeout claims | Use [task #157](https://github.com/iteam7/gateway7/issues/157) to compare measured cases and options before selecting a design. |
| Which plugin chain and concurrent workload should define supported capacity? | Capacity claims and operational testing | Propose representative scenarios and obtain the intended workload. |
| Is server environment/configuration sufficient for provider secrets, or is an external manager needed? | Deployment configuration scope | Present the existing setup and the alternative; obtain a decision. |
| What permissions and instructor-access route apply to the Week 3 and Week 5 transcript sources? | Whether transcripts may be published or submitted privately | Confirm each meeting separately; publish neither source by assumption. |

## Disagreements

| Your position | Customer's position | What you changed |
| --- | --- | --- |
| The live walkthrough narrated the system and left the acceptance mapping until the end. | Bring visible stories and criteria for a small set of substantial use cases, demonstrate each and request its verdict. | Recorded DEC-018 and the structured follow-up above; no verdict was inferred retrospectively. |
| Streaming compatibility was discovered while attempting to connect OpenCode shortly before the demonstration. | Try real integrations early because they expose requirements that component work alone misses. | Recorded DEC-017; [task #153](https://github.com/iteam7/gateway7/issues/153) and [PR #156](https://github.com/iteam7/gateway7/pull/156) are subsequent integration work, not functionality shown in this meeting. |
