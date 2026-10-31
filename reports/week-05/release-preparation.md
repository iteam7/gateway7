# REL-05 release and submission record

Prepared on 30 October and updated on 31 October 2026 under [task #133](https://github.com/iteam7/gateway7/issues/133), using the [contributor confirmation](meeting-follow-up.md).
**Status: [v0.3.0](https://github.com/iteam7/gateway7/releases/tag/v0.3.0) was published on 31 October 2026 at the confirmed production commit; final report merging and private packaging follow the checked common-SHA workflow below.**
Direct campus HTTP access remains an explicit deployment deviation, and no Moodle upload is claimed.
The [Week 05 report](README.md) indexes the public evidence; this file keeps the remaining release handoffs explicit.

## Verified checkpoint

The confirmed production-code commit on main is [`a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`](https://github.com/iteam7/gateway7/commit/a15b1cd14618ee7b5ac423f4aed5ed2f496f405d).
Its [Python check job](https://github.com/iteam7/gateway7/actions/runs/41130602373/job/124320199306) reports `1088 passed in 46.82s`, including `tests/test_testability.py` and `tests/test_confidentiality.py`.
The named `Run tests` step took 48 seconds and `Exercise separate HTTP processes` took 12 seconds, satisfying QR-02's five-minute bounds.
The [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan) records the two CI results at that commit.
The [supporting Linux run](quality-checks.md#qr-01-linux-execution) passed 50 repetitions of each of four failure cases with zero upstream requests.
At this release-cut checkpoint, the full QR-01 still needed the Windows procedure and QR-03 QRT-02 still needed deployed output; neither was inferred from that CI or Linux-only run.
The later [cross-platform CI record](quality-checks.md#qr-01-native-ci-execution-on-31-october) and [operator-reported staging result](quality-checks.md#staging-check) are dated follow-ups, not changes to the published tag or release body.

[PR #147](https://github.com/iteam7/gateway7/pull/147) records staging and production health/chat verification at `26dab3122dbc2f4247533d0c57cdb0f83e5073cf` with the synthetic provider.
It says the VM was available; lack of access from this preparation environment does not establish the assignment's VM-unavailable exception.
In the [later 31 October follow-up](meeting-follow-up.md#later-deployment-and-private-submission-confirmation), the contributor identifies `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d` for both OpenAI environments and confirms successful health, readiness and chat checks.
The [core-check record](quality-checks.md#reported-vm-core-verification) records these as member-reported results; raw remote output and independent image inspection are not claimed.
Access currently requires SSH forwarding, so direct HTTP access through the VM IPv4 address from the university network is not fulfilled.
This restriction must remain visible in the release limitation and private access instructions; the VM is not described as unavailable.

## Handoffs and remaining work

| Handoff | Required completion |
| --- | --- |
| Review and human records, [#132](https://github.com/iteam7/gateway7/issues/132) | Six story acceptances, the sole team attendee, the retrospective, prior AI-output review and PDF-only transcript instruction are confirmed in [the follow-up](meeting-follow-up.md); preserve the unclarified error criteria. |
| Final candidate, [#133](https://github.com/iteam7/gateway7/issues/133) | The contributor-selected deployed candidate is exact main commit `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`; later report-only commits are not substituted for that production tag target. |
| Deployment, [#134](https://github.com/iteam7/gateway7/issues/134) | The matching OpenAI deployments and core checks are contributor-confirmed. Direct campus HTTP access still needs correction; the separately reported deployed privacy PASS is recorded with its confirmed tested revision in [quality evidence](quality-checks.md#staging-check). |
| Quality evidence, [#136](https://github.com/iteam7/gateway7/issues/136) and [#137](https://github.com/iteam7/gateway7/issues/137) | At release cut, two CI QRTs and a Linux reliability run were evidenced. The later main CI completes native Windows/Linux reliability; the operator-reported staging PASS has its explicitly confirmed deployed revision in the current [quality record](quality-checks.md). |
| Sprint closeout, [#138](https://github.com/iteam7/gateway7/issues/138) and [#139](https://github.com/iteam7/gateway7/issues/139) | Both remaining open tasks were moved to SPRINT-06 with their fields preserved; SPRINT-05 has zero open issues. Automated approval review prevented the close action, so the milestone remains open pending specific confirmation. |
| Private submission, [#133](https://github.com/iteam7/gateway7/issues/133) | Verified team details, the current VM/access details and the recording are held privately; the contributor explicitly authorised a PDF-only transcript. Build the final private PDF and ZIP from one merged report commit; no Moodle upload is claimed. |

## Operator evidence handoff

Use the existing [manual deployment runbook](../../docs/deployment.md#manual-deployment) and the environment's already prepared checkout and separate ports, configuration and credentials.
The following commands remain a reproducible operator handoff for future checks or a deployment; they are not presented as raw output of the contributor-confirmed core checks.
An on-campus operator runs them on the VM; no hostname or checkout directory is supplied here.
The chosen commit must be the same in both checkouts; record the full output of `git rev-parse HEAD` before starting each stack.
Keep real credentials and the environment addresses out of the shared evidence.

In the staging checkout, after selecting that commit and the existing staging configuration:

```sh
git rev-parse HEAD
docker compose -p gateway7-staging up --build --detach --wait
docker compose -p gateway7-staging ps
STAGING_URL="http://$(docker compose -p gateway7-staging port gateway 8000)"
python3 scripts/check_confidentiality.py --gateway "$STAGING_URL" --project gateway7-staging
qrt_exit=$?
printf 'QRT exit=%s\n' "$qrt_exit"
test "$qrt_exit" -eq 0
```

The QRT expects a valid staging client token already exported as `GATEWAY7_CLIENT_TOKEN` and a model named `fake`; its current implementation is for a synthetic-provider staging configuration.
It must report the expected HTTP statuses, zero values found in logs, metrics and error bodies, a final `PASS QR-03 QRT-02` line and exit 0.
For a deployment whose provider key is held in an operator environment variable, add the existing `--provider-key-env` option naming that variable; do not print its value.
If staging runs a real-provider-only configuration, this hard-coded `fake` scenario is not a valid passing run as written: retain `Not verified` and coordinate the separate QRT/configuration change before promotion.
Keep this precondition explicit rather than treating a model-authorization failure as a successful privacy check.

After staging verification passes, select the same commit in the production checkout, then run:

```sh
git rev-parse HEAD
docker compose -p gateway7-production up --build --detach --wait
docker compose -p gateway7-production ps
PRODUCTION_URL="http://$(docker compose -p gateway7-production port gateway 8000)"
uv run --locked gateway7 smoke --url "$PRODUCTION_URL" --token-env GATEWAY7_CLIENT_TOKEN
smoke_exit=$?
printf 'Smoke exit=%s\n' "$smoke_exit"
test "$smoke_exit" -eq 0
```

The smoke command uses the checkout's locked CLI installation from the setup guide and an already exported production token; it checks health/readiness, client access and one configured-model request.
That request uses the selected provider, so a real-provider configuration can incur one API call.
Its safe JSON report and exit 0 supply the core-task result; also record which provider/configuration was selected without dumping the configuration or environment.
When the live profile is selected, its installed configuration can be checked without printing credentials:

```sh
docker compose -p gateway7-production exec -T gateway gateway7 validate --config /etc/gateway7/gateway.yaml
```

Return a sanitized record with the date, full matching staging/production commit, selected provider name, container health, staging QRT command and output/counts/exit, and production smoke report/exit.
The CI links in the testing plan must identify that final candidate as well.
If production verification fails, follow the runbook's rollback and record the failed commit and last verified target; do not tag the failed candidate.

## Publication checkpoint

[v0.3.0](https://github.com/iteam7/gateway7/releases/tag/v0.3.0) was published on 31 October 2026.
The tag was checked to identify the full contributor-confirmed production commit `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`, and the protected release-tag rules remain active.
Its customer-facing body ends with the working [Full changelog link](https://github.com/iteam7/gateway7/blob/ae766927fc8a18a277192491e9376b7a13446526/CHANGELOG.md#030---2026-10-31) to the dated released section.
That documentation revision is separate from the runtime tag target; a later report-only revision is not substituted for the code running in production.

The first publication action was rejected by automated approval review because those runtime and documentation revisions differ.
The contributor subsequently gave explicit informed confirmation of that distinction and authorised publication and merging the checked report.
One publication attempt after that new authorisation succeeded, and GitHub API readback confirmed the published release and exact tag target.
The previous draft is therefore not the current release state; no protected tag was moved or deleted.
The initial approval-review event is separate from the still-unmet campus HTTP-access requirement.

## Customer-facing release note

The [published release note](https://github.com/iteam7/gateway7/releases/tag/v0.3.0) describes the guarded OpenAI-compatible agent flow, simpler OpenAI startup, proxy transport, smoke command and middleware authoring/diagnostic workflow.
It retains the buffered-streaming, single-function-call, recorded synthetic-harness and SSH-only deployment limitations, followed by the final Full changelog line.
The [REL-05 block](../../docs/project-plan.md#rel-05) owns the release's checked-requirement index; the testing plan owns each actual result.

## Release and submission order

1. Keep the contributor-confirmed production commit and its green main CI fixed; do not replace that runtime revision with a later report-only commit.
   The minimum testability-plus-other-High CI checks pass; the network restriction and the remaining declared QRTs remain explicit limitations.
2. The protected v0.3.0 tag is published on the verified production commit on main; keep that tag fixed.
3. The published customer-facing body and final Full changelog link were checked; merge the matching dated section in `CHANGELOG.md` with a new empty Unreleased section.
4. Merge the plan's REL-05 block: `Released` with the real tag link and date; `Checked QRs` with each QR having any test checked in SPRINT-05, even if another check failed or remains unverified, followed by one testing-plan link.
5. The confirmed retrospective and known accepted `8 SP` scope are recorded, and tasks #138/#139 were explicitly moved to SPRINT-06 on 31 October.
   SPRINT-05 has zero open issues but remains open after automated approval review prevented its close action; complete that specific action only after confirmation, without reconstructing the missing original commitment.
6. Merge the final Week 05 report after its release and linked artifacts, updating this checkpoint with the facts actually completed.
7. Take the report permalink and the ZIP snapshot from that same full merged main SHA; documentation after tagging means this submission SHA can be later than the production tag.
8. Produce the private PDF within two pages, including the verified team details, exact report permalink, current private addresses, SSH access instructions and recording access; the contributor has authorised the Gateway7 transcript as a private-only appendix, separate from the two-page limit.
   State that the direct campus-HTTP requirement is not fulfilled instead of claiming that the SSH arrangement satisfies it.
9. Verify the PDF and ZIP identify the same submission SHA, then upload both to Moodle and record only the upload actually performed.

An intermediate PDF and ZIP identifying a pull-request head are review candidates only.
They must say draft and unmerged, and be rebuilt after the final report and its evidence merge into main.
