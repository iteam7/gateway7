# UT-01 results

This file is a stub until the counted sessions run.
It carries no finding, no verdict, and no participant data, and the Week 7 report claims no result.

## Results

The per-participant table is filled in the run week from the sanitized session notes; the row per participant is added there, and the ten raw SUS responses stay in the session note and are repeated in the SUS table below.
The public and private split follows the evidence map in [the record](README.md#evidence-map).

| Participant | Task 1 | Assistance 1 | Task 2 | Assistance 2 | Task 3 | Assistance 3 | Time 1 | Time 2 | Time 3 | SEQ 1 | SEQ 2 | SEQ 3 | SUS score |
| ----------- | ------ | ------------ | ------ | ------------ | ------ | ------------ | ------ | ------ | ------ | ----- | ----- | ----- | --------- |

| Participant | Item 1 | Item 2 | Item 3 | Item 4 | Item 5 | Item 6 | Item 7 | Item 8 | Item 9 | Item 10 | Score |
| ----------- | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------- | ----- |

The aggregate measures are the main task's completion and unaided proportion, the main task's median time, the median SEQ for each task, and the SUS mean and median with `n=<count>`.

## Findings

Each significant finding becomes a section, cited by its anchor.
The template is:

### Finding 1

- **Severity:** `Critical`, `Major`, or `Minor`, with the reason.
- **Tasks:** the task or tasks it was observed in.
- **Evidence:** the sanitized session notes and the instrumentation records that support it.
- **Recommendation:** what the team should change.
- **Task issue:** the task issue that carries the change, when one is opened.

## Triage

Every finding is triaged in the run week.
A significant finding becomes a task issue in `SPRINT-08`; a behaviour change or a defect names the story and the `AC-nn` it serves, and the `FR-nnn` or `ADR-nnn` it touches.
The task issue cites the finding by its anchor, such as `docs/usability-tests/ut-01/results.md#finding-1`.
A finding the team decides not to act on records the reason here.

## Limitations

The sample size, the single staging environment, the synthetic provider, the session laptop, and the participant profile's narrowness.

## Conclusion

The `QR-06` verdict, `Passes` or `Fails`, with the measured statistic and the bar, once the sessions have run.
