# Risks

| ID | Status | Impact | Likelihood | Risk |
| ------------------- | ------ | ------ | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [RISK-01](#risk-01) | Open | High | Medium | The team is a 3-4 student group splitting attention across a reporting-heavy course and a working gateway, so the Week 3 MUP slice may stay unfinished at the deadline. |
| [RISK-03](#risk-03) | Open | Medium | Medium | The MUP's first demonstration uses a deterministic fake upstream (DEC-011), so a later switch to a real provider may surface integration defects the demo never caught. |
| [RISK-04](#risk-04) | Open | Medium | Low | The existing plugin contract and fixtures may not cover a new company plugin's behavior, so integration could reveal a compatibility gap requiring core changes and failing TOS-03. |
| [RISK-02](#risk-02) | Mitigated | High | Low | The stack and the first implementation sit on an unmerged pull request, so a late or blocked merge would leave `main` without a working gateway at the deadline. |
| [RISK-05](#risk-05) | Open | High | Medium | The team may not recruit at least three representative participants before the run week ends, so the usability test cannot reach the sample its quality requirement needs. |
| [RISK-06](#risk-06) | Open | Medium | Medium | A participant may withdraw or refuse the recording, so the session cannot be counted and its data must be removed. |
| [RISK-07](#risk-07) | Open | High | Low | An instructor may not be able to open the private usability-data repository or the recordings folder, so the evidence cannot be reviewed. |
| [RISK-08](#risk-08) | Open | High | Medium | The design review or the sessions may not finish before the Week 8 deadline, so the results and the quality requirement's verdict are not ready. |

The response overview below summarizes the operative fields; each risk section retains their full wording and evidence.

| Risk | Trigger | Window | Mitigation | Contingency |
| --- | --- | --- | --- | --- |
| [RISK-01](#risk-01) | Candidate task has no PR the day before the Customer meeting | Week 3, before the meeting | Open small tasks early and merge ready work | Demonstrate merged work; any candidate removal requires Customer DEC |
| [RISK-02](#risk-02) | Implementation PR has no approval before release | Week 3, before first release; settled by PR #51 | Arrange independent review before release | Deliver the clean-checkout slice; track documentation follow-up |
| [RISK-03](#risk-03) | First live provider rejects the request or its response cannot be parsed | Before US-01 AC-05 and MLS-03 acceptance | Validate the real adapter with one authorized live smoke call | Keep the deterministic demo usable while fixing the adapter; US-01 remains unfinished |
| [RISK-04](#risk-04) | Adding another plugin requires a core edit | Week 4 plugin integration | Implement against only the documented contract | Revise the interface version and rerun both plugins' fixtures |
| [RISK-05](#risk-05) | Fewer than three participants are confirmed 48 hours before the results deadline | Week 8, before Submission 8 | Recruit early through the course chat and personal contacts, keep a reserve list, and book sessions as soon as the design and verification are ready | Recruit replacements; if three still cannot be recruited, keep the QR/QRT row Not verified or move it to SPRINT-09, declare the shortfall, and claim no result |
| [RISK-06](#risk-06) | A participant refuses the recording or withdraws | Any counted session in Week 8 | Collect the durable consent before every session, explain the recording and the withdrawal, and keep the code mapping private | Do not count the session, remove its raw text and recording, retire the code, and recruit a replacement under the next free code |
| [RISK-07](#risk-07) | An instructor reports a missing repository, folder, or permission | Week 7 and Week 8, before submission | Create the private repository with the team and the instructors as readers, share the cloud folder with them, and verify both before the first session | Give the private text through a Moodle-only archive and declare the deviation; keep the recordings in the cloud folder |
| [RISK-08](#risk-08) | No confirmed design-review slot by 14 November, or no sessions booked by 18 November | Week 7 and Week 8 | Book the design review early, run the design and instrumentation in parallel, and schedule sessions once the verification passes | Move the QR/QRT row to SPRINT-09 with a reason, declare it in the report, and claim no result |

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

The stack and the first implementation sit on an unmerged pull request, so a late or blocked merge would leave `main` without a working gateway at the deadline.

- **Status:** Mitigated
- **Impact:** High
  - Without the merge, `main` has no `gateway7/` package, so [TOS-01](threshold-of-success.md#tos-01) cannot be checked from a clean checkout at all.
- **Likelihood:** Low
  - The branch's checks (lychee, markdownlint, Python checks) are already green; only a human review and the `Responsible`/`Accountable` assignment are outstanding.
- **Trigger:** [the pull request carrying the stack and the implementation](https://github.com/iteam7/gateway7/pull/51) has no reviewer approval by the day before the release is cut.
- **Window:** the Week 3 sprint, up to the first release.
- **Mitigation:** assign a reviewer to tick the linked task's acceptance criteria and approve the pull request as soon as the architecture proposal is confirmed, ahead of the release.
- **Contingency:** merge only the files the clean-checkout run needs and open a follow-up task for any remaining documentation gap, so the release still ships a working slice.
- **Outcome:** [PR #51](https://github.com/iteam7/gateway7/pull/51) merged into `main` on 2026-10-17, carrying the stack, `gateway7/` package and `docs/setup.md`, per [`DEC-013`](decisions.md#dec-013); `main` now has a working package, so this risk can no longer materialize.

## RISK-03

The MUP's first demonstration uses a deterministic fake upstream (DEC-011), so a later switch to a real provider may surface integration defects the demo never caught.

- **Status:** Open
- **Impact:** Medium
  - A defect found only after the deterministic demo delays the real-provider check that US-01 / AC-05 still requires, per [`CON-01`](product-vision.md#con-01).
- **Likelihood:** Medium
  - The provider adapter has not yet been exercised against a live API; request/response shape mismatches are common on a first integration.
- **Trigger:** the first real-provider call returns a response the adapter cannot parse, or the provider rejects the request format.
- **Window:** before [US-01 AC-05](https://github.com/iteam7/gateway7/issues/30) can pass and [MLS-03](project-plan.md#mls-03) can be accepted. [CON-01](product-vision.md#con-01) permits a deterministic initial demo; it does not defer the candidate's real-provider criterion until after the MUP.
- **Mitigation:** keep the provider adapter behind the same interface the fake upstream implements, and add one live smoke call against the real provider before relying on it for a demonstration.
- **Contingency:** keep the deterministic upstream available for plugin demonstrations while correcting the real-provider integration; US-01 and MLS-03 stay unfinished until AC-05 passes. Removing or rescoping that criterion requires the Customer's recorded decision, not a fallback to mock evidence.

## RISK-04

The existing plugin contract and fixtures may not cover a new company plugin's behavior, so integration could reveal a compatibility gap requiring core changes and failing TOS-03.

- **Status:** Open
- **Impact:** Medium
  - A broken plugin contract would force a core change to add the second plugin, which directly fails [TOS-03](threshold-of-success.md#tos-03).
- **Likelihood:** Low
  - One configured middleware order with reverse response unwinding is implemented in [the loader](https://github.com/iteam7/gateway7/blob/main/gateway7/loader.py) and [pipeline](https://github.com/iteam7/gateway7/blob/main/gateway7/pipeline.py).
    [Application startup](https://github.com/iteam7/gateway7/blob/main/gateway7/app.py) loads configuration and starts plugins before readiness; the [plugin guide](plugins.md) documents installation through a module and configuration followed by restart.
    The existing [core tests](https://github.com/iteam7/gateway7/blob/main/tests/test_core.py) cover middleware order, descriptor/settings/handle validation and startup cleanup, but do not establish compatibility with every new company plugin.
- **Trigger:** adding the second plugin needs an edit outside its own plugin file or its documented configuration location.
- **Window:** the sprint in which the second plugin is added, per [TOS-03](threshold-of-success.md#tos-03)'s Week 4 measure.
- **Mitigation:** write the second plugin against the documented contract alone, with no access to the first plugin's internals, before declaring the contract stable.
- **Contingency:** patch the contract through a new minor version of the plugin interface and re-run both plugins' fixtures before merging.

## RISK-05

The team may not recruit at least three representative participants before the run week ends, so the usability test cannot reach the sample its quality requirement needs.

- **Status:** Open
- **Impact:** High
  - Fewer than three counted sessions leave [`QR-06`](quality-requirements/qr/QR-06.md) `Not verified` and the Week 8 results incomplete.
- **Likelihood:** Medium
  - The sessions depend on personal contacts and the course chat inside a short window, and the test excludes the team, the Customer, the instructors, and the course staff.
- **Trigger:** fewer than three participants are confirmed 48 hours before the results deadline.
- **Window:** Week 8, before Submission 8 on 21 November 2026.
- **Mitigation:** recruit through the course chat and personal contacts in Week 7, keep a reserve list, and book sessions as soon as the design and the instrumentation verification are ready.
- **Contingency:** recruit replacements; when three still cannot be recruited, keep the `QR/QRT` row `Not verified` in `SPRINT-08` or move it to `SPRINT-09`, declare the shortfall, and claim no result.

## RISK-06

A participant may withdraw or refuse the recording, so the session cannot be counted and its data must be removed.

- **Status:** Open
- **Impact:** Medium
  - A lost session costs a recruitment slot and can push the counted sample below three.
- **Likelihood:** Medium
  - The recording is mandatory for a counted session, and the consent allows withdrawal at any time.
- **Trigger:** a participant refuses the recording before the session, or withdraws during or after it.
- **Window:** any counted session in Week 8.
- **Mitigation:** collect the durable [consent](usability-tests/ut-01/consent.md) before every session, explain the recording and the withdrawal in advance, and keep the identity mapping private.
- **Contingency:** do not count the session, remove its raw text and recording, retire the code, and recruit a replacement under the next free code.

## RISK-07

An instructor may not be able to open the private usability-data repository or the recordings folder, so the evidence cannot be reviewed.

- **Status:** Open
- **Impact:** High
  - The submission's private evidence is then unreadable to the grader, which weakens the Week 8 results and the Moodle wrapper.
- **Likelihood:** Low
  - Access is set when the private repository and the cloud folder are created, before the first session.
- **Trigger:** an instructor reports a missing repository, a missing folder, or a missing permission.
- **Window:** Week 7 and Week 8, before the submission.
- **Mitigation:** create the private repository with the team and the instructors as readers, share the cloud recordings folder with them, and verify both before the first session.
- **Contingency:** give the private text through a Moodle-only archive and declare the deviation; the recordings stay in the cloud folder.

## RISK-08

The design review or the sessions may not finish before the Week 8 deadline, so the results and the quality requirement's verdict are not ready.

- **Status:** Open
- **Impact:** High
  - Submission 8 then loses the usability results and the `QR-06` verdict.
- **Likelihood:** Medium
  - The schedule depends on the Customer's review slot and on the participants' availability.
- **Trigger:** no confirmed design-review slot by 14 November 2026, or no sessions booked by 18 November 2026.
- **Window:** Week 7 and Week 8.
- **Mitigation:** book the design review early, run the design and the instrumentation in parallel, and schedule sessions once the verification passes.
- **Contingency:** move the `QR/QRT` row to `SPRINT-09` with a reason, declare it in the report, and claim no result.
