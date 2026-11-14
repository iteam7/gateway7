# Week 7 Customer review report

## Metadata

- **Date:** 2026-11-13, the date of the supplied product-demo recording.
- **Duration:** The supplied recording covers at least 11 minutes and 37 seconds.
- **Attendees:** `azamatbayramov` and Customer, as identified by the recording and the task owner's note.
- **Presented:** The working gateway through OpenCode, the read-only operator overview, provider usage, middleware chains, startup validation, and phone-masking and blocking examples. DeniBorsh separately confirmed that the UT-01 design review and teammate pilot were completed successfully; the current [test record](../../docs/usability-tests/ut-01/README.md#pilot-and-customer-review) lists the reviewed materials.
- **Permission answers:** Not present in the supplied transcript; no individual answer is inferred here.
- **Transcript:** None in the public repository. The supplied transcript is retained outside the repository because publication permission is not established in the available source.
- **Meeting script:** [Week 7 design-review script](meeting-script.md). The supplied transcript does not establish whether this script was used for the recorded demonstration or for the separate UT-01 review.

## Previous action points

The Week 5 report labels its Week 6 follow-ups as proposed rather than Customer-agreed actions.
The Week 6 report records that no formal Customer Review took place and that no Week 6 meeting report exists, so there are no Week 6 Customer action points to close.

| Action | Outcome | Decision |
| --- | --- | --- |
| Prepare a harness, plugin and policy demonstration from the [Week 5 report](../week-05/meeting-report.md#action-points). | The 13 November demonstration showed OpenCode integration, a read-only dashboard, middleware and policy examples. Customer said the product now looked more complete and asked to see a plugin being added; that follow-up is listed below. | None. |
| Investigate blocking-plugin behavior and clarify the operational questions from the [Week 5 report](../week-05/meeting-report.md#open-questions). | The recording showed a policy-blocking example, but did not review the blocking-plugin investigation, capacity target or secret-storage question. Those questions remain open. | None. |

## Previous open questions

| Question | Answer | Decision |
| --- | --- | --- |
| Which demonstrated stories does Customer accept or reject? | Customer reacted positively to the working integration and dashboard, but the recording contains no story-by-story verdict. | None. |
| How should developers add a plugin and understand its behavior? | The middleware chain and masking/blocking examples were shown. Customer asked for a separate plugin-add demonstration. | None. |
| What plugin-chain capacity, blocking behavior and secret-storage approach are required? | Not addressed in this demonstration; keep these questions open. | None. |

## Summary

- The live OpenCode flow reached the gateway. A later provider attempt failed while the presenter was on the university network; the presenter attributed the failure to the proxy/network path, so the report does not describe every request as successful.
- The operator view showed client access, provider usage, configured middleware chains and startup validation. Sanitized screenshots are [the overview](images/customer-demo-operator-overview.jpg), [provider usage](images/customer-demo-provider-usage.jpg), and [middleware validation](images/customer-demo-middleware-validation.jpg).
- Customer said the product now looked more complete and that the dashboard and policy plugins made the DevOps proposition clearer. Customer asked to see a plugin being added as the next demonstration.
- DeniBorsh confirmed on 2026-11-14 that the teammate pilot and UT-01 design review were completed successfully; the [UT-01 record](../../docs/usability-tests/ut-01/README.md#pilot-and-customer-review) keeps that confirmation separate from participant results.

## Decisions

- [DEC-022: Proceed with the current UT-01 design in SPRINT-08.](../../docs/decisions.md#dec-022)

## Action points

| Action | Owner | Due |
| --- | --- | --- |
| Record and show a walkthrough of adding a plugin. | `azamatbayramov` | 2026-11-21, Week 8. |
| Arrange the counted UT-01 sessions and deliver the results and QR-06 verdict with the Week 8 submission. | `DeniBorsh` | 2026-11-21, Week 8. |

## Open questions

| Question | What it would change | Follow-up |
| --- | --- | --- |
| Does the plugin-add walkthrough resolve Customer's remaining concern about how a developer installs and diagnoses a plugin? | The authoring workflow and the next customer-facing acceptance check. | Show the walkthrough at the next Customer meeting and record the response. |
| What plugin-chain capacity and blocking behavior should the gateway support? | The product's operational limits and the scope of the follow-up investigation. | Keep open until Customer and the team select a representative workload and failure case. |

## Disagreements

None.
