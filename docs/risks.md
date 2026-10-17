# Risks

| ID                  | Status | Impact | Likelihood | Risk                                                                                                                                                                    |
| ------------------- | ------ | ------ | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [RISK-01](#risk-01) | Open   | High   | Medium     | The team is a 3-4 student group splitting attention across a reporting-heavy course and a working gateway, so the Week 3 MUP slice may stay unfinished at the deadline. |
| [RISK-02](#risk-02) | Open   | High   | Low        | The stack decision (DEC-013) lands on an unmerged branch, so a late or blocked merge would leave `main` without a working gateway at the deadline.                      |
| [RISK-03](#risk-03) | Open   | Medium | Medium     | The MUP's first demonstration uses a deterministic fake upstream (DEC-011), so a later switch to a real provider may surface integration defects the demo never caught. |
| [RISK-04](#risk-04) | Open   | Medium | Low        | Plugin ordering and restart-only loading are agreed but not yet implemented, so a second plugin (TOS-03) may expose an ordering or configuration-validation gap.        |

## RISK-01

The team is a 3-4 student group splitting attention across a reporting-heavy course and a working gateway, so the Week 3 MUP slice may stay unfinished at the deadline.

- **Status:** Open
- **Impact:** High
  - A missed deadline leaves the candidate stories unmerged and unshown, which fails [TOS-01](threshold-of-success.md#tos-01) and [TOS-04](threshold-of-success.md#tos-04) outright.
- **Likelihood:** Medium
  - [`CON-02`](product-vision.md#con-02) and [`CON-03`](product-vision.md#con-03): a small team is also carrying the plan, the stack setup and the docs site in the same week as the build.
- **Trigger:** a task issue for a candidate story (US-01, US-02 or US-03) has no open pull request by the day before the customer meeting.
- **Window:** the Week 3 sprint, up to the Week 3 meeting.
- **Mitigation:** open one task issue per unit of work early in the sprint and merge each pull request as soon as it is ready, instead of batching merges near the deadline.
- **Contingency:** demonstrate whichever of US-01, US-02 and US-03 are merged, and move the rest out of the candidate with the Customer's decision, per [Building, Delivering, And Releasing The Candidate](https://github.com/inno-itpd/itpd/blob/main/requirements/minimum-usable-product-requirements.md#building-delivering-and-releasing-the-candidate).

## RISK-02

The stack decision (DEC-013) lands on an unmerged branch, so a late or blocked merge would leave `main` without a working gateway at the deadline.

- **Status:** Open
- **Impact:** High
  - Without the merge, `main` has no `gateway7/` package, so [TOS-01](threshold-of-success.md#tos-01) cannot be checked from a clean checkout at all.
- **Likelihood:** Low
  - The branch's checks (lychee, markdownlint, Python checks) are already green; only a human review and the `Responsible`/`Accountable` assignment are outstanding.
- **Trigger:** the pull request carrying the stack and the implementation has no reviewer approval by the day before the release is cut.
- **Window:** the Week 3 sprint, up to the first release.
- **Mitigation:** assign a reviewer to tick the linked task's acceptance criteria and approve the pull request as soon as the architecture proposal is confirmed, ahead of the release.
- **Contingency:** merge only the files the clean-checkout run needs and open a follow-up task for any remaining documentation gap, so the release still ships a working slice.

## RISK-03

The MUP's first demonstration uses a deterministic fake upstream (DEC-011), so a later switch to a real provider may surface integration defects the demo never caught.

- **Status:** Open
- **Impact:** Medium
  - A defect found only after the deterministic demo delays the real-provider check that US-01 / AC-05 still requires, per [`CON-01`](product-vision.md#con-01).
- **Likelihood:** Medium
  - The provider adapter has not yet been exercised against a live API; request/response shape mismatches are common on a first integration.
- **Trigger:** the first real-provider call returns a response the adapter cannot parse, or the provider rejects the request format.
- **Window:** the sprint that lifts [`CON-01`](product-vision.md#con-01), after the MUP milestone.
- **Mitigation:** keep the provider adapter behind the same interface the fake upstream implements, and add one live smoke call against the real provider before relying on it for a demonstration.
- **Contingency:** fall back to the deterministic upstream for the meeting and schedule the real-provider fix as the next sprint's first task.

## RISK-04

Plugin ordering and restart-only loading are agreed but not yet implemented, so a second plugin (TOS-03) may expose an ordering or configuration-validation gap.

- **Status:** Open
- **Impact:** Medium
  - A broken plugin contract would force a core change to add the second plugin, which directly fails [TOS-03](threshold-of-success.md#tos-03).
- **Likelihood:** Low
  - The architecture proposal already fixes plugin ordering, request-local state and startup validation before any second plugin is written.
- **Trigger:** adding the second plugin needs an edit outside its own plugin file or its documented configuration location.
- **Window:** the sprint in which the second plugin is added, per [TOS-03](threshold-of-success.md#tos-03)'s Week 4 measure.
- **Mitigation:** write the second plugin against the documented contract alone, with no access to the first plugin's internals, before declaring the contract stable.
- **Contingency:** patch the contract through a new minor version of the plugin interface and re-run both plugins' fixtures before merging.
