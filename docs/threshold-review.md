# Threshold clarification for Customer review

**Status:** Proposal awaiting a Customer decision. No goal, measure, deadline or historical statement in [the current threshold](threshold-of-success.md) is changed by this page.

The audit found two places where a goal promises more than its measure proves.
The proposals below are concrete wording for the next review, not new acceptance criteria for the [US-01–03 candidate](project-plan.md#mls-03).

## Pipeline verification

[TOS-02](threshold-of-success.md#tos-02) covers the product's configured request and response pipelines, but its measure only names phone-masking fixtures.
Phone masking by itself cannot establish the allow/modify/deny behavior of both hook phases.

- **Proposed goal:** The configured request and response pipelines enforce each allow, modify and deny result, with repeatable evidence that rejected data is not forwarded to the next boundary.
- **Proposed measure:** By the original Week 3 deadline, 17 October 2026, recorded fixtures cover allow, modify and deny in both phases, the existing US-02 phone/history/unchanged-text cases, and exception/timeout handling; denied requests produce zero upstream calls, denied responses are not delivered, and default audit output contains no raw payload or credential.
- **Proposed success criterion:** A reviewer can reproduce those fixtures at the recorded commit and see each boundary enforced, rather than infer the full pipeline's behavior from one masking example.
- **Why:** This makes the existing broad goal testable without adding a production response-policy story to the Week 2 candidate. It does not repair the missing historical evidence or extend the original deadline. The reported Windows timeout defect in [task #84](https://github.com/iteam7/gateway7/issues/84) must be considered when evaluating a platform-wide claim.

Customer and team must first assess the existing goal against the evidence available by its original deadline.
If it is already certain to have been missed, record `Missed` and an evidence-linked outcome; do not silently give it a new date. A later replacement goal needs its own identifier and Customer decision.

## Candidate acceptance

[TOS-04](threshold-of-success.md#tos-04) requires acceptance, while its current measure and success statement allow a recorded verdict even if the candidate is rejected.
Its phrase "Week 3 or later" also leaves the final date open.

- **Proposed goal:** Customer explicitly accepts every story in the unchanged US-01–03 MUP candidate against its acceptance criteria.
- **Proposed measure:** By 23 October 2026, proposed for Customer confirmation, the meeting report links a genuine acceptance DEC-nnn for US-01, US-02 and US-03 after every AC has been demonstrated, including US-01 AC-05. Each story issue links the verdict and evidence.
- **Proposed success criterion:** All three candidate stories are accepted; a rejection or a missing verdict remains unfinished validation, even when it is correctly documented.
- **Why:** This aligns the measure with the existing acceptance goal and supplies a finite review date. [DEC-012](decisions.md#dec-012) approved what to build; [DEC-014](decisions.md#dec-014) and [DEC-015](decisions.md#dec-015) requested further architecture/plugin evidence. None accepts the implemented stories or approves this proposed date.

Apply any agreed change through a new Customer DEC-nnn and the goal's `Changed` field, following [the threshold rules](https://github.com/inno-itpd/itpd/blob/main/requirements/planning-requirements.md#the-threshold-of-success).
Preserve the existing failure/success statement cells as the historical record; this review does not rewrite them or mark either goal achieved.
