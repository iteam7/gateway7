# Week 01 submission checklist

Open items for Modular LLM Gateway, team 7, as of October 3, 2026. This list does not satisfy the missing requirements or confirm that the assignment has been submitted.

## Recorded updates

- [x] Replace the AI-assessment placeholder with azamatbayramov's actual accepted/changed/rejected decisions; do not attribute an assessment to other members.
- [x] Record the October 3 post-kickoff assignments: repository infrastructure to azamatbayramov and base architecture to ExFuseMe; keep the proposed October 12 architecture target and unagreed infrastructure date explicit.
- [x] Trace the Customer-confirmed corporate plugin-host need to the kickoff while retaining the specific competitive-gap uncertainty.
- [x] Keep the current public meeting evidence as sanitized summary notes, with no recording URL or private identity mapping. This closes the current-tree replacement, not the permissions or historical-copy questions below.
- [x] Compile and inspect the one-page [sanitized Typst preview](submission-preview.pdf). It is a draft and contains no private team mapping or recording URL.

## Confirmations still needed

- [ ] Confirm the proposed October 12 architecture target with ExFuseMe and agree the infrastructure date with azamatbayramov. October 12 is outside the required Week 2 window (October 2–8); keep that deviation explicit. These are post-kickoff clarifications; October 8 was not agreed at the meeting.
- [ ] Establish the narrower workflow benefits and competitive shortfall for `GAP-01`/`GAP-02`, or retain the explicitly conditional proposals. The kickoff confirms the broader plugin-host need, not that alternatives serve it poorly.
- [ ] Resolve three separate kickoff permissions with the Customer: recording, publishing a sanitized transcript, and sharing it privately with instructors if publication is refused. Record when each answer is obtained; the Customer starting the recording does not establish the other permissions or prove the questions were asked beforehand.
- [ ] Resolve the previously published transcript and the privacy statement with the Customer/instructors. Its historical copy remains accessible; replacing it with notes did not remove it from Git history. If prohibited exposure is confirmed, follow the course's private incident-reporting and authorized cleanup procedure.
- [ ] Obtain acceptance of the repository-gallery deviation or provide a real view-only board using the existing screenshots, then update its public links.

Keep the historical preparation, missing question areas/rewrites, attendance/role, unpresented-direction, criteria-timing and branch-evidence deviations truthful. A later meeting's preparation must be dated as new work; it cannot be presented as kickoff preparation. A 49-minute meeting does not prove that 30 minutes were planned or 60 requested. Declaring deviations does not waive requirements.

## Final private package

- [ ] After the reviewed corrections merge, freeze the final full `main` SHA and verify that exact commit's link check is green. Keep the check result with the submission record; do not make a new commit solely to update the dated baseline run in the report.
- [ ] Open the rendered `reports/week-01/README.md` permalink at that full SHA and verify its public links without privileged access.
- [ ] Download and inspect the repository ZIP for the same exact SHA; do not reuse the older partial draft bundle.
- [ ] Prepare and inspect the private PDF, at most two pages: project/team/week, private GitHub-username–real-name–university-email mapping, full report permalink, instructor-accessible recording link, sanitized transcript only if publication is refused and private sharing is permitted, and an honest privacy line. Keep all private material out of the repository and include no duplicate public report.
- [ ] Obtain an instructor-accessible recording link or have the missing-recording deviation accepted. The Customer supplied only a transcript and overview, with no recording/link; no access check is currently possible. Verify any private links once supplied.
- [ ] Submit the PDF and matching ZIP once as the team's Moodle submission and retain the receipt. Record the actual submission time rather than claiming an earlier deadline was met.

Requirements: [Assignment 1](https://github.com/inno-itpd/itpd/blob/fe58ba70bbd90b92ffd6942d340f1e8b35b4bbb1/assignments/assignment-1.md), [artifact requirements](https://github.com/inno-itpd/itpd/blob/fe58ba70bbd90b92ffd6942d340f1e8b35b4bbb1/requirements/artifact-requirements.md), and [permalinks and snapshots](https://github.com/inno-itpd/itpd/blob/fe58ba70bbd90b92ffd6942d340f1e8b35b4bbb1/requirements/repository-requirements.md#permalinks-and-snapshots).

## Build the private PDF with Typst

The public [template](submission.typ) and [preview](submission-preview.pdf) contain no private values. The preview links the pre-MR `main` baseline `7dfa6d008fef0131a322aa5b948198000176dda3`; it is not the final submission SHA. Rebuild after the reviewed changes merge.

From the repository root, compile the public preview with [Typst](https://typst.app/docs/):

```sh
typst compile --input report-sha=7dfa6d008fef0131a322aa5b948198000176dda3 reports/week-01/submission.typ reports/week-01/submission-preview.pdf
```

For the private wrapper, create `reports/week-01/submission.private.json` locally with this schema. Keep it and the resulting PDF out of Git; both filenames are ignored. Use verified identities and university emails, never guessed mappings. Do not change the tracked template to insert them.

```json
{
  "members": [
    {"username": "azamatbayramov", "name": "", "email": ""},
    {"username": "ExFuseMe", "name": "", "email": ""},
    {"username": "DeniBorsh", "name": "", "email": ""},
    {"username": "iceberkut", "name": "", "email": ""}
  ],
  "report_sha": "",
  "recording_url": "",
  "privacy_statement": "",
  "links_verified": false,
  "privacy_resolved": false
}
```

Set `links_verified` only after checking the full-SHA report and instructor recording access. Set `privacy_resolved` only after resolving the historical transcript and permissions; supply the accurate privacy statement rather than copying an unsupported clean-history claim. Then compile:

```sh
typst compile --input private-data=submission.private.json --input mode=final reports/week-01/submission.typ reports/week-01/submission.private.pdf
```

Use preview mode for the current private draft while the recording link and other confirmations are missing; the wrapper states that no recording/link was supplied. This disclosure does not satisfy the recording requirement. Final mode rejects incomplete fields and wrappers longer than two pages. It cannot verify an email's ownership, a commit's membership in `main`, or instructor permissions: the checklist still requires those checks. If publication was actually refused and private transcript sharing permitted, add `transcript`, `publication_refused: true` and `private_sharing_permitted: true` to the private JSON; do not infer either permission. Inspect every page and link in the filled PDF before the authorized Moodle submission.
