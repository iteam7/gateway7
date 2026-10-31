# Week 05 contributor confirmation

- **Recorded:** 2026-10-31.
- **Source:** azamatbayramov's answers to the completion questionnaire for [task #132](https://github.com/iteam7/gateway7/issues/132) and [task #133](https://github.com/iteam7/gateway7/issues/133).
- **Customer meeting:** 2026-10-30; [the original meeting report](meeting-report.md) is preserved as the account written from the supplied recording.
- **Purpose:** add the participant's subsequent confirmation without rewriting that meeting report or attributing the later answers to the transcript.

## Customer verdicts

azamatbayramov confirmed that the following stories were shown to Customer and that Customer was satisfied with them.
This is the participant's report of acceptance at the 30 October demonstration, recorded on 31 October; it is not a claim that the transcript itself names each verdict.

| Story | Reported verdict | Decision |
| --- | --- | --- |
| [US-01: answer without holding the provider key, #30](https://github.com/iteam7/gateway7/issues/30) | Accepted | [DEC-020](../../docs/decisions.md#dec-020) |
| [US-02: mask phone numbers, #31](https://github.com/iteam7/gateway7/issues/31) | Accepted | [DEC-020](../../docs/decisions.md#dec-020) |
| [US-03: add a company plugin, #32](https://github.com/iteam7/gateway7/issues/32) | Accepted | [DEC-020](../../docs/decisions.md#dec-020) |
| [US-04: configure the policy reaction, #33](https://github.com/iteam7/gateway7/issues/33) | Accepted | [DEC-020](../../docs/decisions.md#dec-020) |
| [US-05: check the model's response, #34](https://github.com/iteam7/gateway7/issues/34) | Accepted | [DEC-020](../../docs/decisions.md#dec-020) |
| [US-12: diagnose a failing or slow plugin, #140](https://github.com/iteam7/gateway7/issues/140) | Accepted | [DEC-020](../../docs/decisions.md#dec-020) |

The confirmation did not name US-06, [#35](https://github.com/iteam7/gateway7/issues/35); its existing closed state is not a recorded Customer verdict.
No rejected story or failed criterion was reported in these answers.
Acceptance records the Customer's reported verdict; it does not manufacture individual test outputs or silently change a criterion whose wording still needs reconciliation.

## Requirement clarification

azamatbayramov separately confirmed that OpenAI was demonstrated and was acceptable to Customer.
[DEC-021](../../docs/decisions.md#dec-021) records OpenAI as an acceptable real provider for US-01 alongside the previously named Claude/Gemini options.
This resolves the provider-choice question; it does not invent a new `pong` response log.

The answers did not establish agreement to change the plugin-name requirement in a client error for US-04/US-06, or US-04's startup-error example containing `explode`.
Keep those exact criteria and any discrepancy visible until it is verified or explicitly clarified.
Capacity, secret-manager selection and non-cooperative plugin execution remain open as stated in the original report.

## Participants and team records

azamatbayramov confirmed that he was the only Team 7 member at the Customer call.
The supplied record identifies Customer as the other participant in Gateway7's part of the shared meeting; the other project team's demonstration is separate.
The earlier script's missing advance arrangements and role allocation are not filled retrospectively.

The contributor reported that Team 7 discussed and confirmed the retrospective observations and actions on 31 October.
The [retrospective](sprint-retrospective.md) records that discussion and the remaining sprint-closeout work.
The contributor also confirmed that the AI tools already listed in the [AI report](ai-usage.md) were used, and that the team read their output and corrected it before using it.
The report records that human assessment as accepted with changes, without inventing particular rejected outputs.

## Confirmed follow-up plan

azamatbayramov confirmed the proposed owners, priorities and follow-ups from the questionnaire.
The following coordination dates were confirmed after the Customer meeting; they are not attributed to Customer's words in the recording.

| Action | Owner | Due |
| --- | --- | --- |
| Prepare three or four substantial demonstrations with visible US/AC wording, then record the next Customer verdicts. | azamatbayramov | 2026-11-06, Week 6 |
| Coordinate the blocking-plugin investigation in [#157](https://github.com/iteam7/gateway7/issues/157), measuring responsiveness and cooperative timeout limits before selecting a design. | azamatbayramov | 2026-11-06, Week 6 |
| Obtain the outstanding infrastructure, representative-capacity, secret-storage and per-meeting transcript-permission answers. | azamatbayramov | 2026-11-06, Week 6 |

## Planning, deployment and submission

The contributor confirmed that Sprint 05 planning took place, but did not supply its original selected stories, estimates or date.
The recorded 30 October `8 SP` forecast therefore remains separate from the unavailable original commitment.
He instructed the team to carry unfinished work forward; accepted stories and unfinished issues must be reconciled against the tracker rather than treating every open issue as new Sprint 06 scope.

The contributor reported that both staging and production now run OpenAI on the university VM.
The matching deployed commit, deployment time and current verification output have not yet been supplied; [the release preparation](release-preparation.md) retains that evidence handoff.
The older synthetic-provider verification in PR #147 remains historical evidence, not the new OpenAI deployment's proof.

The contributor suggested that the transcript could be included in Moodle, but did not report Customer's separate permission answer.
Public publication and private instructor sharing are still unconfirmed; no transcript is published from that suggestion.
The previous private submission PDF is being used only to recover private team details and links, without copying them into GitHub or treating old deployment data as current.
The contributor confirmed that nothing has been uploaded to Moodle for this assignment.

## Later deployment and private-submission confirmation

In later answers on 31 October, azamatbayramov confirmed that both OpenAI environments run `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`, the then-current main commit.
He confirmed successful health, readiness and OpenAI chat checks in both staging and production.
These are contributor-reported operational results, not a claim that the documentation agent connected to the VM or inspected its images.
The [quality record](quality-checks.md#reported-vm-core-verification) preserves their scope separately from the automated QRTs.

The contributor relayed the deployment operator's explanation that access currently requires SSH and port forwarding.
The environment details, recording link and access code are retained only for the private submission.
Direct HTTP access by the VM's IPv4 address from the university network is therefore an outstanding deployment requirement, not a VM-unavailable exception.
This SSH arrangement does not fulfil the campus HTTP-access requirement.

The contributor explicitly authorised including the transcript in the private PDF only.
This later instruction replaces the earlier uncertainty about the team's intended private submission, without attributing an unrecorded permission statement to Customer or authorising a public transcript.
The private appendix is limited to Gateway7's part of the shared recording; the preceding project team's demonstration is outside this report's scope.
The recording link, its access information, the team identity table and the transcript remain outside GitHub.

## Release publication after informed confirmation

After the runtime-tag and later-documentation distinction had been explained, the contributor explicitly authorised publication and merging the checked release records on 31 October.
The [v0.3.0 release](https://github.com/iteam7/gateway7/releases/tag/v0.3.0) was then published and checked to target the previously confirmed production commit `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`.
The [publication checkpoint](release-preparation.md#publication-checkpoint) preserves the first automated approval-review event and the successful action under that subsequent authorisation.
This publication does not change the SSH-only access limitation, fill the unverified QRTs or claim a Moodle upload.

## Tracker closeout checkpoint

On 31 October, the two remaining open SPRINT-05 tasks, [#138](https://github.com/iteam7/gateway7/issues/138) and [#139](https://github.com/iteam7/gateway7/issues/139), were moved to SPRINT-06 with their roles, assignees and Priority values preserved.
SPRINT-05 then had zero open issues.
Automated approval review prevented the subsequent milestone-close action because it required specific confirmation for that action; the milestone remains open and the action was not repeated.
This administrative checkpoint is separate from the published v0.3.0 release and does not change any story verdict or QRT result.
