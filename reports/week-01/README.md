# Week 01 report

## Project

Modular LLM Gateway, team 7.
License: [MIT](../../LICENSE).

**Problem space:** Corporate IT teams need to route LLM requests and responses through replaceable plugins that adapt access, usage tracking and data-handling policies to their own systems.

## Summary

We researched eleven candidates, compared four alternatives on seven properties, and retained two gap hypotheses. Existing products already support local filtering and custom extensions, so a comparative advantage remains unproven. The October 2 kickoff broadened the direction from privacy preflight to a corporate plugin host. MVP-0 is a one-provider proxy with a server-configured key and simple masking plugin, estimated at two to three weeks with CI and linters first; no implementation is claimed for Assignment 1.

## Coverage

| Deliverable       | Artifact                                                                          |
| ----------------- | --------------------------------------------------------------------------------- |
| Candidate list    | [candidate-list.md](candidate-list.md) |
| Alternatives      | [docs/research/alternatives.md](../../docs/research/alternatives.md)             |
| Comparison        | [docs/research/comparison.md](../../docs/research/comparison.md)                 |
| Gap analysis      | [docs/research/gap-analysis.md](../../docs/research/gap-analysis.md)             |
| Value proposition | [docs/research/value-proposition.md](../../docs/research/value-proposition.md)   |
| Research board    | [Evidence gallery](evidence-gallery.md), nine screenshots; repository-gallery deviation pending acceptance |
| Meeting script    | [meeting-script.md](meeting-script.md)                                            |
| Customer kickoff  | [meeting-report.md](meeting-report.md), [meeting-notes.md](meeting-notes.md) |
| AI usage          | [ai-usage.md](ai-usage.md)                                                        |
| Remaining submission work | [submission-checklist.md](submission-checklist.md), unresolved confirmations and final package checks |

Publication permission for the transcript is unconfirmed. This revision uses sanitized summary notes; the previous transcript remains in Git history, which has not been rewritten.

## Repository evidence

- Branch protection: [September 28 screenshot](images/branch-protection.png); [active main ruleset](https://github.com/iteam7/gateway7/rules/24131483), rechecked October 3: PR required, one approval, no bypass actors. All four members have verified write-or-higher access
- Merged pull request approved by another member: [PR #13](https://github.com/iteam7/gateway7/pull/13), [approved by azamatbayramov](https://github.com/iteam7/gateway7/pull/13#pullrequestreview-5396752624)
- Dated pre-correction baseline, verified October 3: green `main` link check [run 37133115154](https://github.com/iteam7/gateway7/actions/runs/37133115154), SHA `1e5fb6c739cfaa6e182d9ff1b004150f31cbeb31`. After the remaining corrections merge, check the final `main` SHA and its own green run before submission; retain that check with the submission record rather than creating another commit solely to refresh this baseline
- Excluded links: None. The existing workflow accepts 429 and 503; that setting is unchanged, so a green run does not by itself prove every page returned content

## Contribution

| Member | Commits | Issues | Pull requests | Reviews |
| ------ | ------- | ------ | ------------- | ------- |
| azamatbayramov | [4a17909](https://github.com/iteam7/gateway7/commit/4a17909c096236a1dd4f28fafaa7a07ac051cc75) | — | [#2](https://github.com/iteam7/gateway7/pull/2); kickoff participation | [Approved #13](https://github.com/iteam7/gateway7/pull/13#pullrequestreview-5396752624) |
| ExFuseMe | [e6f6703](https://github.com/iteam7/gateway7/commit/e6f67031422cc43b622f804181b9a3a8df7f4401) | — | [#13 candidates](https://github.com/iteam7/gateway7/pull/13) | [Approved #9](https://github.com/iteam7/gateway7/pull/9#pullrequestreview-5352290924) |
| DeniBorsh | [d7dbccf](https://github.com/iteam7/gateway7/commit/d7dbccf236fed3aab8934f0db85a3416a907f30a), sole commit in their PR #12 | — | [#12 gaps](https://github.com/iteam7/gateway7/pull/12), [#11 alternatives](https://github.com/iteam7/gateway7/pull/11) | [Approved #16](https://github.com/iteam7/gateway7/pull/16#pullrequestreview-5396089844) |
| iceberkut | [7ce57af](https://github.com/iteam7/gateway7/commit/7ce57af6af97dbfc3ffad5c86d2c644513a72c7f) | — | [#14 meeting](https://github.com/iteam7/gateway7/pull/14), [#10 propositions](https://github.com/iteam7/gateway7/pull/10) | [Approved #2](https://github.com/iteam7/gateway7/pull/2#pullrequestreview-5343485306) |

## Deviations

- **Meeting script written after the meeting.**
  No script was prepared before the kickoff.
  [meeting-script.md](meeting-script.md) lists only the questions actually asked, so business goals and current workflow have no questions and `## Key improvements` is `None`.
  The team had no problem-space sentence yet, so the script's `## Context` works from the proposed direction in the value proposition draft.
  We did not invent a preparation that did not happen.
- **One team member attended.**
  Only azamatbayramov attended, as he confirmed on October 3. The team reports that partial attendance was allowed. There was no separate note taker or observer; the automatic record supported the later summary notes.
- **Joint session with another team.**
  A member of another course team on the same project took part and asked questions 6 to 13 of the script.
  The Customer's answers to them are part of the record and are used in the [meeting report](meeting-report.md).
- **Direction not presented.**
  Our `VP-01`/`VP-02` direction was not shown at the kickoff; the disagreement with `VP-01` comes from the Customer's description of the product, not from a reaction to a presentation.
- **Publication/private-sharing permission unconfirmed.**
  The Customer initiated recording. On October 3 the participant did not recall asking the separate permission questions; the earlier claims of off-record permission were removed. Summary notes replace the verbatim transcript in this revised tree.
- **Action deadlines unagreed.** October 8 was not agreed. The meeting report leaves real owners/dates to be confirmed rather than inventing replacements.
- **Repository gallery instead of an external board.** The [gallery](evidence-gallery.md) contains at least two screenshots per alternative, with source captions and [license notices](../../ATTRIBUTION.md). Course acceptance of this arrangement remains unconfirmed.
- **Research limits.** Criteria were refined during research, and the gap hypotheses still need comparative validation. Declaring deviations does not waive the corresponding requirements.
- **Historical branch evidence.** PR #11 (`fill_alternatives`) and PR #12 (`fill_gap-analysis`) used underscores instead of hyphens. PR #12's source branch was absent at the October 3 audit; its PR and commit remain accessible, but the deletion time and actor are unverified. These historical deviations are not repaired by renaming evidence or rewriting history.

## Privacy

No recording, recording link, university email, identity mapping or credential is included in this revised public tree. The previously published transcript remains in Git history; publication permission is unconfirmed and no history rewrite is claimed.
