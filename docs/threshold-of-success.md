# Threshold of success

The threshold of success is the minimal set of goals that must all be achieved for gateway7 to count as a success this term.
Each goal below answers a failure statement listed in [Failure And Success Statements](#failure-and-success-statements).
The [earlier Customer review proposal](threshold-review.md) identifies measure/goal inconsistencies and preserves unadopted clarifications; those proposals are not part of the current threshold.
Open goals retain their original deadlines while the missing historical evidence is assessed.

## TOS-01

A clean checkout runs the minimum usable product candidate (US-01, US-02, US-03) end to end by following `docs/setup.md`, with no manual patching.

- **Status:** Open
- **Measure:** a reviewer following `docs/setup.md` from a clean checkout sends a chat request and gets a filtered response, covering US-01, US-02 and US-03, by the Week 3 deadline.

## TOS-02

Every request and response passes through the configured policy pipeline, and the pipeline's allow, mask, and block decisions are each independently verifiable.

- **Status:** Open
- **Measure:** the phone-number masking plugin's offline fixture suite ([VP-01](research/value-proposition.md#vp-01-predictable-local-preflight-for-small-teams)) passes its positive, negative and error cases, with no raw payload in the default audit log, by the Week 3 deadline.

## TOS-03

A company plugin can be added to the gateway without changing the core's code.

- **Status:** Achieved
- **Measure:** a second, previously unwritten plugin is installed and exercised through configuration alone ([VP-02](research/value-proposition.md#vp-02-testable-domain-filter-extensions)), with no edit to any file outside its own plugin and configuration files, by Week 4.
- **Outcome:** the recorded 19 October 2026 disposable-checkout check installed and exercised a new `company_plugins/sample.py` through configuration with no core edit, before the Week 4 deadline; [the historical US-03 re-verification](https://github.com/iteam7/gateway7/blob/090106fa1cfd88cbeceb291975e5de7b645ea301/reports/week-03/README.md#us-03-issue-32-re-verification-on-19-october-2026) records the changed paths, commit and result. This assessment reads that existing record; it is not a new test run.

## TOS-04

The Customer accepts the minimum usable product candidate against its stories' acceptance criteria.

- **Status:** Achieved
- **Measure:** a `DEC-nnn` records the Customer's verdict on US-01, US-02 and US-03 in a Week 3 or later meeting report.
- **Outcome:** Customer acceptance of US-01, US-02 and US-03 at the 30 October meeting is recorded in [DEC-020](decisions.md#dec-020), supported by [the contributor confirmation recorded on 31 October](https://github.com/iteam7/gateway7/blob/090106fa1cfd88cbeceb291975e5de7b645ea301/reports/week-05/meeting-follow-up.md#customer-verdicts). This is member-reported evidence supplementing the transcript-only meeting report; it does not claim that the original transcript names those verdicts or adopt the earlier proposed acceptance date.

## Failure And Success Statements

| Goal | Success statement | Failure statement |
| ---------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| [TOS-01](#tos-01) | A stranger can run the candidate end to end from a clean checkout by following the setup guide. | Nobody outside the team can run the gateway, so the term ends with code that only its authors can start. |
| [TOS-02](#tos-02) | The masking policy's allow/mask/block decisions are each proven by an offline fixture, not a demo. | The masking plugin looks correct in a live demo but has no repeatable check, so a later change could silently break it. |
| [TOS-03](#tos-03) | A second plugin is added through configuration alone, proving the plugin contract generalizes. | The plugin interface only ever hosts the one plugin it was built for, so the "plugin host" claim rests on a single case. |
| [TOS-04](#tos-04) | The Customer's verdict on the candidate is recorded, win or lose. | The team builds and ships a candidate the Customer never explicitly accepted or rejected, so "done" is the team's opinion. |
| — | The stack and its CI gates are in place before the candidate's logic is built. | The team starts writing plugin logic before linters, tests and CI exist, so defects accumulate before anything catches them. |
