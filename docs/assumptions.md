# Assumptions

The kickoff confirmed the broader plugin-host need and the scope decisions recorded in the [meeting report](../reports/week-01/meeting-report.md#decisions). The table below contains the narrower assumptions that the recorded meeting did not settle; it does not reopen the confirmed project direction. Confirm an assumption only when supporting evidence is recorded in a subsequent meeting report or research result.

Source: [docs/research/value-proposition.md](research/value-proposition.md#assumptions).

| Assumption | Supports | How we will check it | When |
| --- | --- | --- | --- |
| A small-team text workflow is the right user segment | VP-01, VP-02 | Ask Customer for current process, users, concrete examples and consequences | Week 2 follow-up; unresolved at kickoff |
| The useful initial boundary can exclude streaming, tools and attachments | VP-01 | Present explicit exclusions and ask which break the workflow | Week 2 follow-up; unresolved at kickoff |
| Existing configurations impose a meaningful verification burden | GAP-01, VP-01 | Compare the same synthetic scenario in LiteLLM and the proposed workflow; accept reuse if sufficient | Week 2 planning, before committing to standalone implementation |
| Custom domain identifiers matter more than broad model/provider coverage | GAP-02, VP-02 | Request a fictionalized format and benign counterexamples; rank needs | Week 2 follow-up; unresolved at kickoff |
| An offline contract runner improves policy-change review | VP-02 | A second developer performs the same change with the baseline and proposed interface; record effort/errors | Week 2 experiment |
| Added latency and fail-closed rejection are acceptable | VP-01 | Agree budgets with Customer, then measure local synthetic cases | Budgets in Week 2 follow-up; measurements after implementation |
| The proposed core/plugin split fits team capacity | VP-01, VP-02 | Break the scope into owned tasks and review estimates | Week 2 planning |
| Selected detector languages/entity types match the workflow | VP-01, VP-02 | Agree a representative synthetic corpus; report precision/recall by category | Corpus during Week 2 planning, measurement later |
