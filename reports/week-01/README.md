# Week 01 report

**Problem space:** Corporate IT teams need to mediate applications' LLM requests and responses while adapting access, usage tracking and data-handling policies to their own systems through replaceable plugins.

## Project

Modular LLM Gateway, team 7 (iTeam7). License: [MIT](../../LICENSE).
Assignment 1 is initial project research. This report was consolidated on 2026-10-03 from the team's merged contributions and the October 2 kickoff; no gateway implementation is claimed.

## Summary

We considered eleven candidates and researched Portkey, Presidio with application middleware, LiteLLM with Presidio, and Kong on-prem across seven properties. Their documentation already supports local processing, custom rules and extension points, so none of those alone is a defensible uniqueness claim. Nine documentation screenshots preserve configuration and limitation evidence, at least two per alternative. Portkey uses two fresh captures of its MIT-licensed gateway README; three earlier product-docs crops with unverified reuse terms remain excluded. No runtime benchmark was performed.

The initial privacy-first framing was too narrow. At the October 2 kickoff, the Customer described a corporate plugin host: request processing first, response processing second, routing third; operator-held provider keys are preferred, and installing plugins can require a restart. Claude and Gemini were acceptable initial targets. Our two revised propositions treat inspectable privacy behavior and testable domain-filter changes as parts of that host. Their comparative advantage remains a hypothesis to test against configured alternatives.

The first runnable milestone discussed was a one-provider proxy with a server-configured key and a simple phone-number masking plugin, estimated at two to three weeks after the kickoff with CI and linters first. It is future work, not an Assignment 1 deliverable. Remaining meeting questions are in the meeting report, rather than repeated here.

## Coverage

| Deliverable | Artifact / status |
| --- | --- |
| Team and project | Project section above; four-member contribution and current access evidence below |
| Repository setup | [Root README](../../README.md), [MIT license](../../LICENSE), [.gitignore](../../.gitignore), [PR template](../../.github/pull_request_template.md), [link workflow](../../.github/workflows/lychee.yml), [Dependabot](../../.github/dependabot.yml); platform evidence below |
| Candidate list | [candidate-list.md](candidate-list.md), including all eleven candidates and rejection reasons |
| Alternatives research | [alternatives.md](../../docs/research/alternatives.md), ALT-01–ALT-04 with source-linked observations and limitations |
| Compare alternatives | [comparison.md](../../docs/research/comparison.md), seven properties and four synthesis patterns |
| Gap analysis | [gap-analysis.md](../../docs/research/gap-analysis.md), GAP-01/GAP-02 and rejected gaps; underserved tests remain unproven |
| Value proposition | [value-proposition.md](../../docs/research/value-proposition.md), VP-01/VP-02, costs, competitor responses, staged scope and assumptions |
| Research board | [Evidence gallery](evidence-gallery.md), nine documentation screenshots with at least two per alternative; acceptance of the gallery substitution remains open |
| Meeting script | [meeting-script.md](meeting-script.md), a retrospective record, with preparation and coverage deviations below |
| Customer kickoff | [meeting-report.md](meeting-report.md) and [meeting-notes.md](meeting-notes.md); sanitized summary notes replace the transcript because publication permission is unconfirmed |
| AI usage | [ai-usage.md](ai-usage.md); the team must supply its own accepted/changed/rejected assessment |
| Repository process evidence | Ruleset, approved merged PR, exact-SHA link-check run and contribution table below; historical settings screenshot and current ruleset check below |
| Private submission wrapper | Prepared separately by the team for Moodle: identity mapping, permitted recording link, final main-SHA report permalink and matching ZIP; not part of this public repository |

## Repository evidence

- **Main protection:** [active ruleset](https://github.com/iteam7/gateway7/rules/24131483), checked through GitHub on 2026-10-03: applies to `main`, requires a PR and one approval, dismisses stale approvals, blocks force pushes/deletion, and has no bypass actors. The [team-supplied settings screenshot](images/branch-protection.png), captured September 28, visibly shows the repository, active main ruleset, empty bypass list, required PR and one approval. The fresh API check corroborates the current settings; the image is not described as an October 3 capture.
- **Approved merged PR:** [PR #13](https://github.com/iteam7/gateway7/pull/13), authored by ExFuseMe, with [azamatbayramov's approval](https://github.com/iteam7/gateway7/pull/13#pullrequestreview-5396752624). This is other-member review evidence, not self-approval.
- **Latest main link check at audit time:** [successful run 37125360390](https://github.com/iteam7/gateway7/actions/runs/37125360390) for full SHA `4d62cd7f947809b754276a201b3947ee9aa524da`, completed 2026-10-03. This run predates the consolidated corrections; it does not validate their final commit. The actual submission must use a green run on its final `main` SHA.
- **Link exceptions:** [.lycheeignore](../../.lycheeignore) has no excluded URLs. The existing workflow accepts HTTP 429 and 503 as well as 200/206; 503 was added in [PR #16](https://github.com/iteam7/gateway7/pull/16) after transient GitHub failures. This consolidation preserves that authorized setting. A green run therefore does not prove every destination returned content, and final browser verification is still required.
- **Collaborator access:** rechecked through GitHub on 2026-10-03 after repository access was restored: azamatbayramov has admin access; ExFuseMe, DeniBorsh and iceberkut each have write access. All four also have commit-via-PR and other-member approval evidence below.

## Contribution

This table records existing contributions, not a reassignment of colleagues' work to the consolidation author. PRs #11 and #14 were already merged before the consolidation began; no colleague branch was rewritten.

| Member | Commit evidence | Pull requests / work | Approval of another member's PR |
| --- | --- | --- | --- |
| azamatbayramov | [4a17909](https://github.com/iteam7/gateway7/commit/4a17909c096236a1dd4f28fafaa7a07ac051cc75) | [#2 license](https://github.com/iteam7/gateway7/pull/2); kickoff participation | [#13 approval](https://github.com/iteam7/gateway7/pull/13#pullrequestreview-5396752624) |
| ExFuseMe | [e6f6703](https://github.com/iteam7/gateway7/commit/e6f67031422cc43b622f804181b9a3a8df7f4401) | [#13 comparison](https://github.com/iteam7/gateway7/pull/13) | [#9 approval](https://github.com/iteam7/gateway7/pull/9#pullrequestreview-5352290924) |
| DeniBorsh | [d7dbccf](https://github.com/iteam7/gateway7/commit/d7dbccf236fed3aab8934f0db85a3416a907f30a), the sole commit in their PR #12 | [#12 gap analysis](https://github.com/iteam7/gateway7/pull/12), [#11 alternatives](https://github.com/iteam7/gateway7/pull/11) | [#16 approval](https://github.com/iteam7/gateway7/pull/16#pullrequestreview-5396089844) |
| iceberkut | [7ce57af](https://github.com/iteam7/gateway7/commit/7ce57af6af97dbfc3ffad5c86d2c644513a72c7f) | [#14 kickoff artifacts](https://github.com/iteam7/gateway7/pull/14), [#10 value propositions](https://github.com/iteam7/gateway7/pull/10) | [#2 approval](https://github.com/iteam7/gateway7/pull/2#pullrequestreview-5343485306) |

Commit evidence for DeniBorsh is traced through PR ownership because that commit's GitHub author object was not linked. No unverified issue attribution is claimed; the Week 1 contribution minimums are evidenced by commits, PRs and reviews.

## Deviations

- **Meeting script written after the meeting.** No script was prepared before the kickoff. The reconstructed script lists only questions actually asked; business goals and current workflow have no questions, and `Key improvements` is `None`. We did not invent prior preparation. This remains a shortfall against the required question coverage and rewrites.
- **Partial team attendance and no separate roles.** Azamatbayramov confirmed on October 3 that he was the only Team 7 attendee. The team reports that the Customer allowed partial attendance. Separate note-taker and observer roles were not assigned; the automatic record supported the later summary notes.
- **Joint session and no direction presentation.** A member of another course team asked some questions. Our written VP-01/VP-02 direction was not presented; the conflict with privacy-first framing comes from the Customer's own description. The maintained research was reconciled afterward on October 3, not retrospectively represented as a meeting decision.
- **Permission evidence.** On October 3 the participant could not confirm that publication or private-sharing permission had been requested; the Customer had initiated recording. The earlier off-record-permission assertions were removed. The revised tree uses sanitized summary notes and withholds the verbatim transcript pending consent. The earlier published transcript remains in Git history; no history rewrite or retroactive consent is claimed.
- **Action deadlines not agreed.** The original report's October 8 action deadlines were rejected by the participant on October 3. No substitute date is invented; Week 2 planning must agree owners and due dates. The assignment's two dated-action minimum remains open.
- **Research properties refined during research.** The original criteria and candidate selection were developed together. No separate pre-evaluation commitment is claimed.
- **Repository evidence gallery.** Nine captioned documentation screenshots are included in the repository rather than an external board, with source MIT notices in [attribution](../../ATTRIBUTION.md). The gallery is navigable and read-only for public readers after publication, but course acceptance of this substitution remains open. The earlier Portkey product-docs crops were replaced by two October 3 captures from the MIT-licensed gateway README; the original crops remain excluded.
- **Documentation-only evaluation.** No products were installed or benchmarked. The Customer clarified a direction, while GAP-01/GAP-02 still lack comparative validation. These are limitations, not claims that the rubric has been fully met.
- **Late hand-in.** The team intends to submit on October 3, after the October 2 hard deadline, and the stated 10%-per-day late policy applies. This does not claim an extension or a completed Moodle submission.

Declaring these deviations makes the record accurate; it does not waive the corresponding requirements.

## Privacy

No recording, recording link, university email, identity mapping, credentials or other known private-only material is included in this revised public tree. The transcript is withheld pending permission; the previously published version remains in Git history, which has not been rewritten.
