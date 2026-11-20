# UT-01 sessions

This directory holds the sanitized session notes, one file per counted session, named by the participant code: `P-01.md`, `P-02.md`, and so on.
A session's raw notes and its recording stay private; the file here is the sanitized note.

Assign participant codes in arrangement order, never reuse a retired code, and give each replacement the next unused code.
Keep the exact appointments, identity mapping, durable consent, raw notes and raw responses in the private text repository; recordings stay only in the team-owned private cloud folder.
Before data collection, the custodian verifies team/instructor store access and the facilitator explains the actual tools and withdrawal contact.
Raw responses are transcribed privately first; derive the public note only after sanitization, not by filling this public template with identifying answers.

## Facilitation script

The facilitator reads this script at the start of every counted session.

1. Welcome the participant, thank them for the time, and say that the session is about the product and not about them.
2. Read the consent form, collect the signature, and start the recording only after the signature.
3. Read the pre-test from [surveys.md](../surveys.md) and record the answers.
4. Say: "Please think aloud as you work. I will not answer questions about how to do the task, and I will not help unless the task stops completely."
5. Read the main scenario verbatim, start the timer, and observe.
6. At the end state or the time limit, stop the task, ask the SEQ question, and record it.
7. Read the second and third scenarios in the same way, in the fixed order, with the SEQ after each.
8. After all tasks, give the SUS and the open-ended post-test.
9. Debrief: answer the participant's questions, thank them, stop the recording, and store it in the team's cloud folder.
10. Record the session's notes here, sanitize them, and file the consent and the identity mapping in the private repository.

## Dry run

Before the first counted session, the team runs one dry run with a teammate.
It checks the scenarios' wording, the fixed order, the time limits, the help rule, the recording, the SUS readability, and the instrumentation path.
The dry run is not evidence and is not counted: it uses no participant code, its data is excluded from the results, and a teammate is never a participant.

## The no-help rule

Help is any direction about where to look, what to type, which command to run, or which field to use.
Repeating the scenario, answering a question about its wording, and reading the stop rule are not help.
A hint is recorded with its time, its wording, and the task it belongs to.
The facilitator does not demonstrate the product, does not name a command, and does not point at the screen.

## Observation sheet

Each session note records:

| Field | Value |
| --- | --- |
| Participant code | `P-nn` |
| Session link | use the participant code; exact appointment/time window and raw linkage stay private |
| Facilitator and observer | the GitHub usernames |
| Pre-test answers | sanitized relation to target user, familiarity and device; raw answers stay private |
| Task 1 outcome, time, SEQ | `Unaided`, `Assisted`, or `Failed`; minutes and seconds; 1–7 |
| Task 2 outcome, time, SEQ | as above |
| Task 3 outcome, time, SEQ | as above |
| Hints | time, wording, task |
| SUS raw responses | ten numbers, 1–5 |
| SUS score | the computed score |
| Post-test answers | sanitized themes; publish quotes only with separate consent |
| Instrumentation check | the request identifiers, or the offline check's exit status |
| Notes and friction | the observer's notes |
| Stop rule | whether it was used, and why |

## Stop rule

The session stops before the time limit when the participant asks to stop, when the participant withdraws, when the recording stops unintentionally, when a critical or security-sensitive problem appears, or when the facilitator judges that continuing would distress the participant.
A session stopped before its data is complete is not counted, including a stop before the pre-test, a stop before all three tasks and the instruments are complete, and a refused recording.
The team retires the participant code and recruits a replacement under the next free code.

A completed session with a failed task still counts; an incomplete, withdrawn, unrecorded or unconsented session does not.
Follow the [withdrawal and retention procedure](../README.md#consent-withdrawal-and-retention) for excluded data and later withdrawal.

## Roles

- **Facilitator:** [@DeniBorsh](https://github.com/DeniBorsh).
- **Observer:** [@iceberkut](https://github.com/iceberkut).
- **Data custodian:** [@ExFuseMe](https://github.com/ExFuseMe).

The facilitator runs every counted session; the observer records the help and the friction and keeps the recording; the data custodian keeps the private repository and the analysis.
A team member who is also a participant is not allowed, and the roles are recorded in the record before the first counted session.
