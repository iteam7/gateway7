# Threshold of success

The threshold of success is the minimal set of goals that must all be achieved for gateway7 to count as a success this term.
Each goal below answers a failure statement listed in [Failure And Success Statements](#failure-and-success-statements).
The [Customer review proposal](threshold-review.md) identifies measure/goal inconsistencies in TOS-02 and TOS-04 and offers concrete clarifications; those proposals are not part of the current threshold.

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

- **Status:** Open
- **Measure:** a second, previously unwritten plugin is installed and exercised through configuration alone ([VP-02](research/value-proposition.md#vp-02-testable-domain-filter-extensions)), with no edit to any file outside its own plugin and configuration files, by Week 4.

## TOS-04

The Customer accepts the minimum usable product candidate against its stories' acceptance criteria.

- **Status:** Open
- **Measure:** a `DEC-nnn` records the Customer's verdict on US-01, US-02 and US-03 in a Week 3 or later meeting report.

## Failure And Success Statements

| Goal | Success statement | Failure statement |
| ---------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| [TOS-01](#tos-01) | A stranger can run the candidate end to end from a clean checkout by following the setup guide. | Nobody outside the team can run the gateway, so the term ends with code that only its authors can start. |
| [TOS-02](#tos-02) | The masking policy's allow/mask/block decisions are each proven by an offline fixture, not a demo. | The masking plugin looks correct in a live demo but has no repeatable check, so a later change could silently break it. |
| [TOS-03](#tos-03) | A second plugin is added through configuration alone, proving the plugin contract generalizes. | The plugin interface only ever hosts the one plugin it was built for, so the "plugin host" claim rests on a single case. |
| [TOS-04](#tos-04) | The Customer's verdict on the candidate is recorded, win or lose. | The team builds and ships a candidate the Customer never explicitly accepted or rejected, so "done" is the team's opinion. |
| — | The stack and its CI gates are in place before the candidate's logic is built. | The team starts writing plugin logic before linters, tests and CI exist, so defects accumulate before anything catches them. |
