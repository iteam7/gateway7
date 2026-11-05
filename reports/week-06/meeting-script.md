# Week 06 Customer Review script

## Context

Gateway7 helps a team use server-held LLM credentials and company policy plugins through one gateway; this Review must establish whether the deployed analytics answers the product-value question, the operating signals diagnose a staging failure, and the existing success threshold needs any Customer-agreed change.

This is preparation, not an account of a meeting already held.
Plan 30 minutes and ask for 60 if Customer can give it.
azamatbayramov coordinates the meeting time, private access and role confirmation; no date, attendance or permission answer is assumed by this script.
The team should attend and verify university-network access before the call.
Use the [readiness table](README.md#review-readiness) to obtain the four actual dashboards and the tested commit; use private bookmarks for their addresses and credentials.
If required evidence is unavailable, state the gap and record a follow-up rather than present the item as delivered.

## Agenda

1. **0–2 min: permissions.** Show no artifact; ask questions 1–3 separately and record each answer before recording begins.
2. **2–7 min: deployed product and substantial use cases.** Show the production deployment and visible story ACs, following [DEC-018](../../docs/decisions.md#dec-018), the [demo guide](../../docs/demo.md) and [authoring walkthrough](../../docs/authoring.md#try-the-installed-package-without-a-provider-account). Cover client/harness access, plugin installation, policy effects and diagnosis; distinguish synthetic fixtures from live-provider evidence. Ask question 4.
3. **7–11 min: product analytics.** Show the metric tree and event query from [#177](https://github.com/iteam7/gateway7/issues/177), both analytics dashboards ([staging #179](https://github.com/iteam7/gateway7/issues/179), [production #180](https://github.com/iteam7/gateway7/issues/180)) and [US-14 #174](https://github.com/iteam7/gateway7/issues/174) AC-01–02. Show the raw staging smoke event, its exclusion from the chart, and the computed metric value or the documented reason no focus value exists. Ask questions 5–6.
4. **11–18 min: operation and diagnosability.** Show [US-15 #175](https://github.com/iteam7/gateway7/issues/175) AC-01–02, the actual Active SLI and query, both observability dashboards ([staging #183](https://github.com/iteam7/gateway7/issues/183), [production #184](https://github.com/iteam7/gateway7/issues/184)) and [#185](https://github.com/iteam7/gateway7/issues/185)'s deployed QRT result. Show its command/environment/commit, the failed request's `request_id`, route, outcome/failure labels and duration, the log returned within 5 seconds, the numeric five-minute P95 failure series returned within 1 minute, and the sanitized screenshot. Show an optional runtime-QRT result and name its SLI only if that test was run. Ask questions 7–8.
5. **18–23 min: earlier follow-ups.** Show [the Week 5 outcome preparation](README.md#prior-follow-up-preparation), [#157](https://github.com/iteam7/gateway7/issues/157), the [quality record](../week-05/quality-checks.md) and [contributor confirmation](../week-05/meeting-follow-up.md). Present recorded answers as recorded answers, and ask only the unresolved questions 9–13; capture any item that needs a longer follow-up.
6. **23–27 min: threshold review, the last substantive topic.** Show [the four-row review](README.md#threshold-review), [the current goals](../../docs/threshold-of-success.md) and [the earlier unadopted clarification draft](../../docs/threshold-review.md). Present the recommendation to keep the current measures: two outcomes are already evidenced and the remaining Week 3 evidence cannot be replaced by telemetry. Ask question 14; record any actual requested change as a new decision rather than applying the old proposed dates.
7. **27–30 min: readback and Week 7 actions.** Show the notes captured during this call, not a prewritten outcome. Read back actual decisions, unresolved items and at least two actions with agreed owners/dates inside Week 7, 6–12 November. Ask questions 15–16 and confirm what may be shared.

## Questions

1. **Closed:** May we record this meeting?
2. **Closed:** May we publish a sanitized transcript of this meeting in the public repository?
3. **Closed:** If publication is refused, may we share this meeting's transcript privately with the instructors?
4. **Open, priority:** Across client/harness access, company-plugin installation, policy effects and failure diagnosis, which demonstrated step still prevents your team from using Gateway7, and which exact criterion describes that gap?
5. **Open:** Does the selected analytics query answer a question you recognise about the gateway's core value, and what conclusion would the current event definitions fail to justify?
6. **Closed:** Do you accept or reject US-14 against the demonstrated AC-01 and AC-02? If rejected, which exact criterion needs rework?
7. **Open, priority:** From this failed request's safe log and SLI result, what can you diagnose, and which missing context would change the next operational step?
8. **Closed:** Do you accept or reject US-15 against the demonstrated AC-01 and AC-02? If rejected, which exact criterion needs rework?
9. **Open:** Given the measured evidence available for #157, which blocking or cancellation-suppressing case must be resolved next before selecting a different execution boundary?
10. **Open:** Which configured plugin chain and concurrent workload should define the supported-capacity check?
11. **Closed:** Is server-held environment/configuration injection sufficient for provider secrets in this increment, or is an external secret manager required?
12. **Open:** For the Week 3 and Week 5 sources separately, what public-transcript and private-instructor-sharing permissions should we record? Keep those answers separate from this meeting's permissions.
13. **Closed:** Does the presented CI/DoD evidence close the carried infrastructure action, or which concrete part remains?
14. **Open, priority:** Do you agree that the existing threshold should remain unchanged on the evidence shown, and what historical evidence is still needed for TOS-01/TOS-02? If you request a different future bar, agree its exact measure and deadline explicitly; the settled TOS-03/TOS-04 outcomes are not rewritten.
15. **Open:** Which at least two concrete follow-ups do we agree for Week 7, who owns each and on which date within 6–12 November is it due? Possible discussion items are the bounded #157 investigation and the still-open policy-error AC reconciliation; these are candidates, not agreed commitments.
16. **Closed:** Does the readback accurately reflect the decisions, each action's owner/date, unresolved questions and the three permission answers?

## Roles

The following is a proposed allocation for azamatbayramov to confirm before the meeting; it is not an attendance record or a claim of prior agreement.

| Planned role | Proposed member | Responsibility |
| --- | --- | --- |
| Moderator | azamatbayramov | Confirm arrangements, control time, ask questions and read back decisions. |
| Note taker | iceberkut | Record actual verdicts, prior-item outcomes, permission answers and agreed action owners/dates. |
| Observer | DeniBorsh | Note unanswered questions and gaps between a dashboard, the SLI/QRT evidence and the story AC. |
| Deployment demonstrator | ExFuseMe | Operate the private environment/dashboard views and identify their actual revision and scope. |

## Key improvements

- **Before:** "Does monitoring look good?" **After:** Question 7 asks what the specific failed-request log and SLI result let Customer diagnose and what context changes the next step. **Principle:** seek an observable decision rather than general approval.
- **Before:** "Can we mark the whole candidate and all goals done?" **After:** Questions 6 and 8 request a named story verdict against its demonstrated ACs, while question 14 reviews the exact existing threshold and its historical evidence. **Principle:** separate Customer acceptance, test evidence and the success bar; do not infer one from another.
