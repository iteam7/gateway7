# Week 06 Customer Review script

## Context

Gateway7 gives teams one LLM gateway with server-held provider credentials and configurable company policy plugins.
The Week 6 Review needs Customer's assessment of product analytics, failure diagnosis and the existing threshold of success against the evidence actually available.

On 7 November 2026, azamatbayramov reported that the planned live Review had not happened because the demonstration was not ready.
The [unused live script](live-review-script.md) preserves the previous preparation exactly; it is not an attendance or outcome record.
This canonical script prepares a **proposed written asynchronous Review** under the [course's written-meeting rules](https://github.com/inno-itpd/itpd/blob/c2e737f7a16221e9fcdaf4234b045baca9cd0c6e/requirements/customer-meetings-requirements.md#every-meeting).
It has not been sent, no written exchange has taken place, and Customer has not agreed to this format.
The reason for the missed Review is the team's preparation shortfall, not Customer unavailability.
The team must arrange an actual exchange; preparing this option does not excuse missing the Review.

Before sending, check the [readiness table](README.md#review-readiness) and identify the revision and environment of every result.
Merged [PR #193](https://github.com/iteam7/gateway7/pull/193) supplies telemetry implementation and local synthetic checks, not proof of deployed analytics, four dashboards or a deployed QRT.
Present every unavailable artifact as unavailable; an unreviewable story has no acceptance verdict.
Share real backend/dashboard addresses and credentials privately using the team's existing access route, never through this public script.
Do not send provider keys, raw prompts, responses or personal data.

A substantive timestamped Customer exchange, with the permission answers actually given, is needed before writing the factual meeting report.
Retain the written transcript only as permitted, declare the asynchronous substitution, and preserve this script as the preparation record after the Review.
Unanswered questions remain unresolved; silence is not acceptance or agreement.
The submission deadline remains 8 November, 23:59, and later proposed actions do not defer its required increment.

## Agenda

Send the parts in this order and wait for the relevant Customer replies before treating them as outcomes.
This is an ordered exchange, without live-meeting roles or timeboxes.

| Order | Material to send | Response to request |
| --- | --- | --- |
| 1. Format and permissions | A short explanation of the missed live Review, this proposed written format and the three separate permission questions below. No private artifact is published. | Confirm whether a written Review is possible and record each permission answer separately before further sharing. |
| 2. Existing product use cases | The [demo guide](../../docs/demo.md), [authoring walkthrough](../../docs/authoring.md#try-the-installed-package-without-a-provider-account), [DEC-018](../../docs/decisions.md#dec-018) and only the actual private deployment evidence the team has verified. Identify synthetic and live-provider evidence separately. Show an external harness only for an implemented, verified exchange. | Identify the concrete remaining obstacle to using Gateway7 and its criterion, question 4. |
| 3. Product analytics | [US-14 #174](https://github.com/iteam7/gateway7/issues/174) AC-01–02 and the actual [#177](https://github.com/iteam7/gateway7/issues/177) metric tree, event definitions, computed query, raw staging smoke event and its exclusion. Include both scoped dashboard views ([#179](https://github.com/iteam7/gateway7/issues/179), [#180](https://github.com/iteam7/gateway7/issues/180)) only if ready; otherwise name each evidence gap. | Assess the query's value and explicitly accept or reject the story against the supplied evidence, questions 5–6. An inability to assess is recorded as unresolved. |
| 4. Operation and diagnosability | [US-15 #175](https://github.com/iteam7/gateway7/issues/175) AC-01–02, [SLI-01](../../docs/observability.md#sli-01) and its actual query, both scoped observability views ([#183](https://github.com/iteam7/gateway7/issues/183), [#184](https://github.com/iteam7/gateway7/issues/184)) and [#185](https://github.com/iteam7/gateway7/issues/185)'s real deployed QRT evidence, if available. Identify the command, environment, commit, failed `request_id`, route, outcome/failure labels, duration, measured log lookup and five-minute P95 failure query. State any missing result explicitly. | Explain what the failed request's evidence diagnoses and give an explicit story verdict, questions 7–8. Do not substitute the local synthetic test for a staging result. |
| 5. Earlier follow-ups | The [prior-item evidence map](README.md#prior-follow-up-evidence), [#157](https://github.com/iteam7/gateway7/issues/157), [Week 5 quality evidence](../week-05/quality-checks.md) and [contributor confirmation](../week-05/meeting-follow-up.md). Preserve their original provenance. | Answer only the unresolved execution, capacity, secrets, permissions and infrastructure questions 9–13; distinguish recorded earlier answers from new replies. |
| 6. Threshold, the last substantive topic | The [four-row threshold review](README.md#threshold-review), [current goals](../../docs/threshold-of-success.md) and [unadopted clarification history](../../docs/threshold-review.md). Recommend retaining the exact existing measures and deadlines; TOS-03/04 have evidence-backed outcomes, TOS-01/02 still need historical proof. | Confirm or challenge the recommendation in question 14. Any requested future change needs an explicit measure, deadline and actual Customer decision. |
| 7. Actions and readback | A readback built from Customer's actual replies: decisions, verdicts, unanswered items, permissions and at least two proposed Week 7 actions. | Confirm or change the actual owners, dates and scope in questions 15–16. Capture the timestamped reply rather than prewriting agreement. |

## Questions

1. **Closed:** May we retain this timestamped written exchange as the Customer Review record? If we add a voice or screen note, may we record it?
2. **Closed:** May we publish a sanitized transcript of this exchange in the public repository?
3. **Closed:** If public publication is refused, may we share the transcript privately with the instructors?
4. **Open, priority:** Across the evidenced client/harness access, company-plugin installation, policy effects and failure diagnosis, which step still prevents your team from using Gateway7, and which exact criterion describes the gap?
5. **Open:** Does the supplied analytics query answer a question you recognise about the gateway's core value, and what conclusion would the current event definitions fail to justify? If the query is not ready, which question should it answer first?
6. **Closed:** Do you accept or reject US-14 against AC-01 and AC-02 on the actual supplied evidence? If rejected, which criterion needs rework? If the evidence is insufficient for a verdict, please state that explicitly; we will retain the unresolved status.
7. **Open, priority:** From the supplied failed-request log and SLI result, what can you diagnose, and which missing context would change the next operational step? If the deployed evidence is missing, which part prevents assessment?
8. **Closed:** Do you accept or reject US-15 against AC-01 and AC-02 on the actual supplied evidence? If rejected, which criterion needs rework? If no verdict is possible, please identify the missing evidence; we will not infer acceptance.
9. **Open:** Given the measured evidence actually available for #157, which blocking or cancellation-suppressing case must be resolved next before selecting a different execution boundary?
10. **Open:** Which configured plugin chain and concurrent workload should define the supported-capacity check?
11. **Closed:** Is server-held environment/configuration injection sufficient for provider secrets in this increment, or is an external secret manager required?
12. **Open:** For the Week 3 and Week 5 sources separately, what public-transcript and private-instructor-sharing permissions should we record? Keep those answers separate from this exchange's permissions.
13. **Closed:** Does the supplied CI/DoD evidence close the carried infrastructure action, or which concrete part remains?
14. **Open, priority:** Do you agree that the existing threshold should remain unchanged on the evidence supplied, and what historical evidence is still needed for TOS-01/TOS-02? If you request a different future bar, agree its exact measure and deadline explicitly; the settled TOS-03/TOS-04 outcomes are not rewritten.
15. **Open:** Which at least two concrete follow-ups do we agree for Week 7, who owns each and on which date within 6–12 November is it due? The team's proposals are: iceberkut checks a complete analytics path for duplicate events and smoke exclusion, with its query and sanitized result, by 10 November; DeniBorsh presents measured [#157](https://github.com/iteam7/gateway7/issues/157) findings about a blocking plugin, its deadline and a neighbouring request, and proposes the next step, by 12 November. Confirm or change the scope, owners and dates; these are not agreed commitments and do not defer the mandatory Assignment 6 increment beyond 8 November.
16. **Closed:** Does the readback accurately reflect your decisions, each action's owner/date, unresolved questions and the three permission answers?

## Key improvements

- **Before:** "Does monitoring look good?" **After:** Question 7 asks what the specific failed-request evidence lets Customer diagnose and which missing context changes the next step. **Principle:** seek an observable decision and disclose missing evidence.
- **Before:** "Can we mark everything done?" **After:** Questions 6 and 8 ask for explicit named-story verdicts on the evidence supplied, while question 14 reviews the unchanged threshold separately. **Principle:** distinguish Customer acceptance, measured test evidence and the success bar; missing replies establish none of them.
