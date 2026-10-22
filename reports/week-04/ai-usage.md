# Week 04 AI usage

## Tools and work

Codex implemented the async middleware migration requested by azamatbayramov on 22 October 2026, tracked in [task #89](https://github.com/iteam7/gateway7/issues/89).
The executing agent changed the versioned plugin contract, configuration, loader, runner, built-in/sample middleware and regression tests.
The main agent migrated the real-process demo, added a synthetic guard and fault fixture, and updated the maintained setup, plugin and architecture guides.
A separate AI TechLead review checked next-handler lifetime and single-use behavior, failure propagation, timeout accounting, usage preservation and safe diagnostics.
That review found a retry after a rejected wrong-task next call and a descriptor-origin `StartupError` disclosure; both required correction before publishing the change.
The AI review is not a team member's approval or a Customer verdict.

## Validation

The migrated demo runs Gateway7 and the deterministic provider as separate HTTP processes.
It checks masking across history, module/config-only installation, disabling, reverse response order, and three distinct middleware types in one operation.
Request-side policy denial, exception and timeout each leave the provider call count unchanged.
A response-side exception records one provider call and returns a safe error without delivering the answer.
Only synthetic fixtures are printed; captured logs and client errors are checked for provider-key and raw-phone disclosure.
The final test and documentation results are recorded in the pull request implementation notes.
No actual Claude/Gemini call, Windows execution, Customer acceptance, story closure or release is claimed.

## Team evaluation

TODO: Team members must record what they accepted, changed or rejected after reviewing this migration.

## Deviations to carry into the weekly report

- Task #89 was created through the GitHub API rather than the web issue form; the API route did not set the `Task` issue type.
- The new task remains unscheduled: no distinct human Responsible/Accountable pair, matching assignees, milestone or Priority is inferred.
- Existing `main` has no `FR-nnn` or `ADR-nnn` records for this migration, so the task records the missing specification links explicitly and cites DEC-014/015. The Week 4 specification work remains separate.
- This file records the implementation work only. It does not complete the Week 4 report, meeting artifacts, retrospective or private submission.
