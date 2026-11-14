# UT-01: Send A First Request, Recover From A Model Denial, And Check A Middleware Change

- **Status:** Planned
- **Design sprint:** [SPRINT-07](../../project-plan.md#sprint-07)
- **Run sprint:** [SPRINT-08](../../project-plan.md#sprint-08)

A developer new to Gateway7 sends a first chat request on staging, recovers from a denied model, and checks a middleware change offline without help, in one session.

## Research questions

1. Can a participant new to the gateway send a first request and read the policy result in the answer without help?
2. When the gateway denies a model, can the participant recover to an allowed model without a hint?
3. Does the offline middleware check give the participant a result they can interpret and report?

## The Requirement

[`QR-06`](../../quality-requirements/qr/QR-06.md), whose `QRT-01` names `UT-01` in `**Runs at:**`.
The requirement reads the main task's SEQ rating, which this record's [Measures](#measures) and [Analysis Plan](#analysis-plan) report.

## Participant Profile

- **Role:** a backend developer who calls an LLM API from application code and works in a terminal.
- **Familiarity:** has sent a request to an LLM API with `curl` or an SDK, and has run a command-line check or test.
- **Device:** the team's prepared laptop on the university network, with the session checkout already present.
- **Relation to the target user:** a developer who would evaluate and configure a gateway for a small team.
- **Excluded:** teammates, the Customer, instructors, course staff, and anyone under 18.
- **Recruitment target:** at least three completed sessions of representative adults aged 18 or older, with five as the design target.
- **Recruitment plan:** the team arranges the sessions in the Week 8 window through its own contacts and a course-chat announcement, and records the arranged dates in the private usability-data repository before the first counted session.
  This repository records no participant names and no session dates.
  Assign codes `P-01`, `P-02` and so on in arrangement order, not completion order.
  Keep contact details, eligibility checks and appointments in the private arrangement register.
  Incomplete, withdrawn, unconsented or recording-refused sessions do not count; retire their codes and give replacements the next unused code.
  A failed task in an otherwise completed session still counts.

## The Tasks

The same three tasks, in the same order, for every participant.
The facilitator reads each scenario verbatim and answers only questions about the scenario's wording.

The outcome of each task is `Unaided` when the participant reaches the end state within the time limit without help, `Assisted` when a recorded hint is needed, and `Failed` when the end state is not reached within the time limit.
These criteria are written before the first counted session and are not changed after the data.

### Main task: send a first request

You are a developer on a small team that wants one gateway in front of its LLM provider.
Send one chat message through the staging gateway and confirm that the gateway masked the personal data in your message before the answer reached you.

- **Start point:** the session card with the staging address and a client token.
- **End state:** the participant has an answer in hand and can say which personal data in the message was masked.
- **Time limit:** 8 minutes.
- **Success criterion:** `Unaided`, `Assisted`, or `Failed` as defined above.
- **Help rule:** no help beyond [the protocol](#protocol) rule; a hint is recorded with its time and wording.

### Secondary task: recover from a denied model

Your application asks for a model the gateway does not allow for your client.
Find out why the request was refused, then get an answer with a model your client may use.

- **Start point:** the session card, after the main task.
- **End state:** the participant has seen a refusal that names the model access, and then received an answer with an allowed model.
- **Time limit:** 6 minutes.
- **Success criterion:** `Unaided`, `Assisted`, or `Failed` as defined above.
- **Help rule:** no help beyond [the protocol](#protocol) rule; a hint is recorded with its time and wording.

### Secondary task: check a middleware change offline

A teammate changed the example email-masking middleware.
Check the change against the middleware's offline examples and tell the team whether it still behaves as expected.

- **Start point:** the prepared checkout on the session laptop, with the changed middleware and its examples.
- **End state:** the participant has run the offline check and reported whether it passed.
- **Time limit:** 7 minutes.
- **Success criterion:** `Unaided`, `Assisted`, or `Failed` as defined above.
- **Help rule:** no help beyond [the protocol](#protocol) rule; a hint is recorded with its time and wording.

The tasks are fixed in this order for every session.
A participant who finishes a task early moves to the next one; the time limit is a stop rule, not a target.

## Protocol

Welcome, consent and recording check, pre-test, think-aloud instruction, the three scenarios read verbatim in order, observation, the SEQ after each task, the SUS and the open-ended post-test after all tasks, and the debrief.

The facilitator never demonstrates a request, never names a command or a field, and never points at a screen area.
The facilitator may repeat a scenario, answer a question about its wording, and read the stop rule.
Any other direction counts as help and is recorded with its time and wording.

A participant may stop at any point; a session stopped before its data is complete is not counted, including a withdrawal, a refused recording, a stop before the pre-test, and a stop before all three tasks and the instruments are complete.

The full session template, the observation sheet, and the roles are in [sessions/README.md](sessions/README.md).

## Measures

- The completion and the assistance of each task, as `Unaided`, `Assisted`, or `Failed`.
- The time on task for each task, from the scenario reading to the end state or the time limit.
- The SEQ rating after each task, on the standard seven-point scale.
- The SUS after all tasks, from the ten standard items, with the score formula.
- The test's instrumentation, where it covers a task, as described under [Instrumentation](#instrumentation).

The qualitative record is the observer's think-aloud notes and the open-ended post-test.

## Instrumentation

The following map ties each research question to its evidence source. The gateway events record request lifecycle only; the observer's sheet and notes record whether the participant understood the result and completed the task.

| Research question and task | Record and emitter | Environment and store | Participant link |
| --- | --- | --- | --- |
| RQ1, main task: send a first request and identify the masked personal data | Reuse `chat_started` and `chat_completed`, emitted by the gateway container's analytics emitter for the HTTP request. `chat_completed` records the outcome and duration; it carries no prompt or answer text. | Staging gateway with the synthetic provider; the event goes to the staging OpenPanel project. The observer's outcome, time, SEQ and comprehension note go to the private usability-data repository. | Task #268 adds `participant_code=P-nn` to the event schema. The event `request_id`, also returned as `X-Request-ID`, pairs start/completion. The observer records the code and request ID on the session sheet. |
| RQ2, secondary task: understand a model denial and recover with an allowed model | Reuse `chat_started` and `chat_completed` for each HTTP request, emitted by the gateway container's analytics emitter. The observer records whether the refusal was understood, whether recovery succeeded, any hint and time. | Staging gateway with a reset synthetic seed and synthetic provider; events go to the staging OpenPanel project. Task observations go to the private usability-data repository. | `participant_code=P-nn` groups the participant's request attempts; each `request_id` pairs one request's start/completion. The session time window disambiguates repeated attempts. |
| RQ3, secondary task: check the middleware change offline | No analytics event is emitted. The local offline command produces its normal exit status; the observer records the status, reported outcome, help and time on the session sheet. | Prepared session-laptop checkout, offline with no provider account or network call; the sheet and notes go to the private usability-data repository. | The observer labels the sheet with `P-nn`; no participant code is sent to an analytics service for this task. |

For the two API tasks, the events carry `source=usability-test`, which only staging accepts, and the optional participant code that [task #268](https://github.com/iteam7/gateway7/issues/268) adds. The session link is the code recorded in the private repository's identity mapping, plus the session time window. The code may appear in staging telemetry; its mapping to a person stays private.

The instrumentation does not cover comprehension, the reason for a hint, or the offline task's internal steps. The observer's notes and post-test answers provide that evidence, and the results state the coverage gap.

The test writes no production data and makes no real payment. The staging seed is reset before each session. Before the first counted session, a teammate verifies that the two API events reach the staging event list, the `participant_code` filter selects that run, and the production project receives no event. The verification is not counted; its evidence goes in the private repository and the Week 7 report. Consent and private-store provisioning remain in [task #269](https://github.com/iteam7/gateway7/issues/269).

## Analysis Plan

A per-participant table with the participant code, each task's outcome and assistance, each task's time, each task's SEQ, and the participant's ten raw SUS responses and score.

The main task's completion count and unaided proportion, and the main task's median time on task.
The median SEQ for each task.
The SUS mean and median with the `n=<count>` sample size.

`QR-06`'s measure is the main task's SEQ, read as the median across the counted sessions, against the bar the requirement sets before the first session.
The other measures stay analysis results and do not change the requirement.

A thematic analysis of the think-aloud notes and the post-test answers, grouped into themes with a quoted, sanitized example per theme.
A severity per finding, chosen from `Critical`, `Major`, and `Minor`, with the reason for the choice.

An instrumentation comparison that reads the test's own instrumentation against the observation, and names which task or question the instrumentation could not cover.
The limitations: the small sample, the single environment, the synthetic provider, the session laptop, and the participant profile's narrowness.

The results file is [results.md](results.md), whose headings are already in place, with the findings template and the triage plan.

## Schedule

The team arranges the counted sessions in the Week 8 window, after the design review and the instrumentation verification, and records the arranged dates in the private repository.
A session may run as soon as the design and the verification are ready.

The results, the findings, and the `QR-06` verdict are due with Submission 8 on 21 November 2026 at 23:59.
The Week 7 report claims no result, the `Results` cell in [the index](../README.md) stays `Pending`, and this record stays `Planned` until the first counted session.

## Roles

- **Facilitator:** [@DeniBorsh](https://github.com/DeniBorsh) runs every counted session and reads the scenarios verbatim.
- **Observer:** [@iceberkut](https://github.com/iceberkut) records the help and the friction and keeps the recording.
- **Data custodian:** [@ExFuseMe](https://github.com/ExFuseMe) keeps the private repository, the identity mapping, and the analysis.

A participant never fills a role, and no role changes between counted sessions without the team recording the change here before the session.
The team design recorded on 2026-11-13 uses the role assignments, scenarios, participant profile, QR-06 measure and bar, and SPRINT-08 run plan shown here.

## Pilot and Customer review

A teammate completed the non-counted pilot, and Customer reviewed the UT-01 design; both outcomes were reported as successful on 2026-11-14.
The supplied materials do not include a pilot checklist, detailed observations, or aspect-by-aspect Customer feedback.
The pilot is not a counted participant session, supplies no usability result, and does not establish a QR-06 verdict.

The supplied 2026-11-13 product-demo transcript does not contain the UT-01 review discussion.
The exact pilot date and detailed review feedback were not supplied.
This record captures the reported overall outcomes only; it does not attribute specific comments or criteria-level findings to Customer.
No counted session or participant result is claimed.

## Environment

The staging deployment on the university VM, reached from a machine on the university network, with the synthetic provider and the seed reset before each session.
The offline middleware task runs on the session laptop's prepared checkout of the same tested revision, with no provider account and no network call.

No real payment is made, and production is not used.
The staging address and the client token stay in the private submission and the session card, not in this repository.

## Consent And Data

Every counted session collects the durable consent in [consent.md](consent.md) before the session starts.
The consent records the 18-or-older declaration, the mandatory recording, the sanitized public results, the optional quotes, the private access, the tools used, the withdrawal, and the deletion after grading.

The authoritative text store is the [private usability-data repository](https://github.com/iteam7/gateway7-usability-data).
The link needs authentication and is excluded from automated link checking for that reason.
On 14 November 2026, private visibility, the initialized text-only homes and the current operator account's repository access were verified through authenticated GitHub readback.
Team collaborator permission metadata includes the confirmed facilitator, observer and data custodian; this is evidence of configured access, not a claim that every person has opened the data.
Instructor readership and successful instructor read checks remain unverified.
The recordings belong in a team-owned cloud folder; its address and access instructions stay in the private repository and the Moodle PDF, never in a public product file.
Recordings are never committed to either Git repository.
Actual staging addresses, dashboard/backend addresses and credentials stay Moodle-only, not in the private text repository.

### Access and arrangement gates

The team-confirmed profile, contact/course-chat recruitment channel, SPRINT-08 arrangement window and facilitator/observer/custodian roles above come from the confirmed #267 design; they are not replaced by issue assignees or guesses.
Recruitment success, signed consent, a counted session and instructor access are not established by that design confirmation.
Before collecting participant data, ExFuseMe must verify private repository visibility, team and instructor readers, cloud-folder ownership and a successful instructor read check, recording date, verifier and outcome privately in `access-and-retention.md`.
An invitation sent or the operator's own access is not an instructor read check.
The private text repository and its authoritative layout are provisioned; instructor access remains pending.
No verified team-owned recordings folder is available: the connected Drive reports no shared drives and no matching project/team folder.
No recording folder or sharing grant was created by this change, and no instructor read check is claimed.
Keep data collection blocked until the recordings and instructor-access gates pass.

If an instructor cannot use GitHub, deliver a dated text archive through Moodle only and declare the deviation in the weekly report; the repository remains the authoritative working home and the archive is a delivery copy.
If recordings-folder access fails, repair sharing or choose another team-owned folder and verify access before sessions; never substitute public sharing or Git storage.
If fewer than three representative complete sessions can be arranged, recruit replacements with the same eligibility, retain the open run window and declare/reschedule the gap; do not count disqualified sessions or lower the profile to fill the target.
The non-counted pilot and Customer review in #270 and the separate pre-session instrumentation verification must pass before counted sessions.

### Consent, withdrawal and retention

Before each session, DeniBorsh explains the form and collects durable consent before recording or tasks; ExFuseMe retains the text record privately.
A signed form, email or message can provide durable consent, but only text records belong in the private repository; never commit a scan or recording to Git.
Fill the recorder, survey/note-tool and withdrawal-contact placeholders in each private participant copy before consent; keep the public template unsigned.
Recording and sanitized public results are required; refusal of optional quotes does not exclude a participant.

On withdrawal, remove the participant's raw text, consent, identity mapping, working analysis, filtered telemetry and recording/tool copies under team control, including retained versions/history; retire the code and exclude the session from analysis.
Remove affected public notes and quotes and revise aggregates/findings as needed; do not publish the identity or withdrawal reason.
Explain that copies of already downloaded sanitized public material cannot be recalled.
Incomplete, unrecorded or unconsented data is removed and never counted.

Keep the private repository and recordings until the course is graded.
After grading, ExFuseMe deletes the private repository **and its history**, local clones, exports, team-controlled delivery copies, recorder/survey-tool copies and cloud recordings, including available trash/version copies; the sanitized public record stays.
Maintain a private deletion checklist and coordinate instructor-held delivery-copy deletion through the course's private channel.

## Evidence Map

| Item | Authoritative home |
| --- | --- |
| The record, surveys, blank consent and session template | Product repository: `docs/usability-tests/ut-01/` |
| Sanitized session notes | Product repository: `docs/usability-tests/ut-01/sessions/P-nn.md` |
| Results, findings and limitations | Product repository: `docs/usability-tests/ut-01/results.md` |
| Sanitized public screenshots | Product repository: `docs/usability-tests/ut-01/images/` |
| Durable consent text records | Private usability-data repository: `consent/` |
| Identity mapping, screening and exact arrangement register | Private usability-data repository: `participants.md` |
| Raw notes and raw survey responses | Private usability-data repository: `raw/` |
| Working analysis | Private usability-data repository: `analysis/` |
| Filtered test telemetry export | Private usability-data repository: `telemetry/`; text only, no IP, location, user agent, referrer or free text; the staging participant code is allowed but its identity mapping stays private |
| Recordings | Team-owned private cloud folder, never Git; link and access instructions in the private repository's `recordings.md` and the Moodle PDF |
| Store-access verification and retention checklist | Private usability-data repository: `access-and-retention.md` |
| Actual staging/production addresses and dashboard/backend access/credentials | Moodle-only private submission, never either Git repository |
| Week 8 results report | `reports/week-08/README.md`, linking the authoritative results rather than copying raw data |

Moodle archive copies and filtered exports are dated delivery/analysis copies, not second authoritative stores.

The results are in [results.md](results.md).
