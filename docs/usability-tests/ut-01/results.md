# UT-01 results

Three counted sessions ran in `SPRINT-08` after the design was fixed.
The table below summarizes the sanitized notes; see [P-01](sessions/P-01.md), [P-02](sessions/P-02.md), and [P-03](sessions/P-03.md) for the evidence.

## Results

| Participant | Task 1 | Help 1 | Task 2 | Help 2 | Task 3 | Help 3 | Time 1 | Time 2 | Time 3 | SEQ 1 | SEQ 2 | SEQ 3 | SUS |
| ----------- | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ----- | ----- | ----- | ---: |
| [P-01](sessions/P-01.md) | Unaided | None | Failed | 3:05 | Unaided | None | 4:45 | 6:10 | 3:55 | 6 | 3 | 5 | 87.5 |
| [P-02](sessions/P-02.md) | Unaided | None | Failed | 4:10 | Assisted | 2:40 | 6:30 | 7:20 | 5:05 | 5 | 4 | 3 | 72.5 |
| [P-03](sessions/P-03.md) | Unaided | None | Unaided | None | Unaided | None | 3:50 | 5:15 | 3:05 | 6 | 6 | 6 | 97.5 |

`Unaided` means no hint was needed; `Assisted` means the recorded hint was needed; `Failed` means the end state was not reached within the task's time limit.
The notes contain the sanitized hint wording and SUS responses.

| Measure | Result |
| ------- | ------ |
| Task 1 completed | 3/3 (100%) |
| Task 1 completed unaided | 3/3 (100%) |
| Task 1 median time | 4:45 |
| Task 1 median SEQ | 6/7 |
| Task 2 median SEQ | 4/7 |
| Task 3 median SEQ | 5/7 |
| SUS mean | 85.83 (`n=3`) |
| SUS median | 87.5 (`n=3`) |

These are descriptions of three sessions, not estimates for a wider population.

## Qualitative analysis

All three participants completed the first-request task without help.
Two described recognizing the masking effect directly in the answer; one noticed it after comparing the answer with the original request.

The model-denial task had the clearest friction.
Two participants did not recover within six minutes: one first searched the message body for the setting, and the other saw a field name but did not know which command to use.
The third found the allowed-model configuration without a hint.

The offline check was completed by all three participants; one needed a hint that the command matched the CI check.
The other two completed it unaided.

## Instrumentation comparison

The supplied sanitized reconciliation of the private filtered export reports one matched `chat_started`/`chat_completed` pair for each of the three counted sessions, linked by the documented request ID and participant code.
It reports zero missing events, zero duplicates and zero corresponding production events.
For P-02, the completion event had about 40 seconds of ingest delay; the wider session-matching window retained the match.
The export itself, exact request IDs and event timestamps remain private and are not reproduced here.

The online events show that a request started and completed, but cannot establish whether a participant understood the policy result, needed a hint or finished within the task time limit.
Those outcomes come from the observer's task record and timer.
Task 3 is offline and has no telemetry by design; its process exit status shows the check result but not whether the participant could interpret or report it, which was covered by observation.

## Findings and triage

### Finding 1

- **Severity:** `Minor` — the recovery task failed for two of three participants, but it is secondary to the successful first-request task, one participant completed it unaided, and the gateway's access denial continued to enforce the allowed-model boundary.
- **Tasks:** `UT-01 Task 2`; [UT-01 P-01](sessions/P-01.md), [UT-01 P-02](sessions/P-02.md), and [UT-01 P-03](sessions/P-03.md).
- **Evidence:** P-01 and P-02 exceeded the six-minute limit after looking for how to change the model; P-03 found the allowlist without help. Their Task 2 outcomes, SEQ scores, times and notes are in the linked session records above.
- **Recommendation:** Consider adding a direct pointer from the denial guidance to the client allowlist configuration and the command or file used to change it.
- **Task issue:** None. The recommendation is deferred for future review; no product or documentation change is committed or declined.

### Finding 2

- **Severity:** `Minor` — one participant needed a single hint on the secondary offline task, while the other two completed it unaided.
- **Tasks:** `UT-01 Task 3`; [UT-01 P-01](sessions/P-01.md), [UT-01 P-02](sessions/P-02.md), and [UT-01 P-03](sessions/P-03.md).
- **Evidence:** P-02 needed the hint that the offline check runs as it does in CI; P-01 and P-03 completed the check unaided. See the linked notes for the outcomes and observations.
- **Recommendation:** Review whether the offline-check guide makes the command and its result easier to locate and interpret.
- **Task issue:** None. The recommendation is deferred for future review; no change or sprint schedule is committed.

| Finding | Severity | Issue decision | Schedule |
| ------- | -------- | -------------- | -------- |
| [Finding 1](#finding-1) | Minor | Deferred for future review; no task issue opened and no change declined. | Not scheduled. |
| [Finding 2](#finding-2) | Minor | Deferred for future review; no task issue opened and no change declined. | Not scheduled. |

The responsible issue owner deferred both recommendations because the sample contains only three participants, both findings concern secondary tasks, and no product change was selected from the evidence.
Neither finding records a committed fix, a declined change, or a release decision.
No product change is claimed as part of `REL-08`.

## Limitations

The sample is three participants, all of whom fit the broad backend-developer profile but differ in how often they send SDK requests and run command-line checks; the results cannot be generalized to all Gateway7 users.
Sessions used the university staging environment and synthetic provider.
P-01 and P-03 used the team session laptop in a campus room; P-02 used their own laptop in a university dormitory, on the university network, which deviated from the planned room and device.

Instrumentation conclusions use the supplied sanitized reconciliation summary; the filtered export itself, exact request IDs and event timestamps remain private and are not reproduced or independently reprocessed in this report.
Telemetry does not measure human understanding, assistance, or task duration.
The small sample also limits the strength of conclusions from individual points of friction.

## Conclusion

1. **First request and policy result:** all three participants reached the defined end state unaided; the main-task median SEQ was 6/7.
   The research question is answered positively for these three sessions.
2. **Recovery after model denial:** one participant recovered unaided and two did not reach the end state within six minutes.
   This sample does not support a conclusion that new users can reliably recover without help.
3. **Offline middleware check:** all three reached the end state, with one needing a hint.
   Two participants interpreted and reported the check without help; the result is mixed for unaided interpretation.

`QR-06 QRT-01` **Passes**: the three counted sessions meet the minimum sample, and the main-task median SEQ is 6/7, above the predeclared threshold of 5/7.
The [testing-plan row](../../project-plan.md#quality-requirement-testing-plan) records this verdict for `SPRINT-08`.
`UT-01` is completed and the [index](../README.md) links these results.

The responsible issue owner has deferred both recommendations for future review.
Neither is recorded as declined or committed, and neither has a sprint schedule or task issue.
