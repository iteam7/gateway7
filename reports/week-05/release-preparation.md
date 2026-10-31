# REL-05 preparation

Prepared on 30 October and updated on 31 October 2026 under [task #133](https://github.com/iteam7/gateway7/issues/133), using the [contributor confirmation](meeting-follow-up.md).
**Status: a concrete v0.3.0 release proposal is prepared, but publication was blocked by automated approval review; no v0.3.0 tag or published REL-05 is claimed.**
Direct campus HTTP access remains an explicit deployment deviation, and no Moodle upload is claimed.
The [Week 05 report](README.md) indexes the public evidence; this file keeps the remaining release handoffs explicit.

## Verified checkpoint

The confirmed production-code commit on main is [`a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`](https://github.com/iteam7/gateway7/commit/a15b1cd14618ee7b5ac423f4aed5ed2f496f405d).
Its [Python check job](https://github.com/iteam7/gateway7/actions/runs/41130602373/job/124320199306) reports `1088 passed in 46.82s`, including `tests/test_testability.py` and `tests/test_confidentiality.py`.
The named `Run tests` step took 48 seconds and `Exercise separate HTTP processes` took 12 seconds, satisfying QR-02's five-minute bounds.
The [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan) records the two CI results at that commit.
The [supporting Linux run](quality-checks.md#qr-01-linux-execution) passed 50 repetitions of each of four failure cases with zero upstream requests.
The full QR-01 still needs the Windows procedure, and QR-03 QRT-02 still needs deployed output; neither is inferred from CI or the Linux-only run.

[PR #147](https://github.com/iteam7/gateway7/pull/147) records staging and production health/chat verification at `26dab3122dbc2f4247533d0c57cdb0f83e5073cf` with the synthetic provider.
It says the VM was available; lack of access from this preparation environment does not establish the assignment's VM-unavailable exception.
In the [later 31 October follow-up](meeting-follow-up.md#later-deployment-and-private-submission-confirmation), the contributor identifies `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d` for both OpenAI environments and confirms successful health, readiness and chat checks.
The [core-check record](quality-checks.md#reported-vm-core-verification) records these as member-reported results; raw remote output and independent image inspection are not claimed.
Access currently requires SSH forwarding, so direct HTTP access through the VM IPv4 address from the university network is not fulfilled.
This restriction must remain visible in the release limitation and private access instructions; the VM is not described as unavailable.

## Handoffs before publication

| Handoff | Required completion |
| --- | --- |
| Review and human records, [#132](https://github.com/iteam7/gateway7/issues/132) | Six story acceptances, the sole team attendee, the team retrospective and prior AI-output review are now confirmed in [the follow-up](meeting-follow-up.md); preserve the unclarified error criteria and per-meeting permissions. |
| Final candidate, [#133](https://github.com/iteam7/gateway7/issues/133) | The contributor-selected deployed candidate is exact main commit `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`; later report-only commits are not substituted for that production tag target. |
| Deployment, [#134](https://github.com/iteam7/gateway7/issues/134) | The matching OpenAI deployments and core checks are contributor-confirmed. Direct campus HTTP access still needs correction; the deployed privacy QRT remains unverified and is not inferred from the core checks. |
| Quality evidence, [#136](https://github.com/iteam7/gateway7/issues/136) and [#137](https://github.com/iteam7/gateway7/issues/137) | The actual candidate has two passing CI QRTs and a Linux reliability record; keep the missing Windows and deployed-privacy results explicit in the plan. |
| Sprint closeout, [#138](https://github.com/iteam7/gateway7/issues/138) and [#139](https://github.com/iteam7/gateway7/issues/139) | Verify refinement links and scheduling, record genuine Customer-accepted completed points, and explicitly move unfinished issues before closing the milestone. |
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

The proposed protected tag targets the contributor-confirmed production commit `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`.
Automated approval review rejected publication because the tag target and the proposed changelog link identify different commits: the runtime commit and a later prepared documentation commit.
A read-only tree comparison found changes only in nine Markdown files between those commits; runtime, configuration, lockfile, workflow and binary blobs are identical.
No second publish attempt, alternate tag target or published-release claim is made from that rejection.
An unpublished GitHub draft was saved for v0.3.0 with the full confirmed production target; its published date is empty and no v0.3.0 tag was created.
The draft is available to authorised collaborators, while this file supplies the publicly reviewable proposal.
The [prepared changelog at `ae766927fc8a18a277192491e9376b7a13446526`](https://github.com/iteam7/gateway7/blob/ae766927fc8a18a277192491e9376b7a13446526/CHANGELOG.md#030---2026-10-31) is a review proposal, not a released section on main or evidence that its prospective tag exists.
The branch's actual changelog retains Unreleased, and the plan's REL-05 heading remains empty until publication, as the course requires.
This publication blocker is separate from the deployment's unmet campus HTTP-access requirement.

## Customer-facing body proposal

The following is the concrete proposed body for v0.3.0, not a claim of publication.
Its final link resolves to the prepared dated changelog proposal; it will need the actual released record when publication completes.

> Gateway7 connects OpenAI-compatible agents through company middleware, with guarded function-tool turns and policies for requests and answers while provider credentials stay on the server. OpenAI startup is simpler, provider calls can use a proxy transport, and the installed smoke command, middleware diagnostics and authoring walkthrough help operators and plugin authors get started.
>
> Streamed delivery is buffered until the complete answer passes policy checks, and the supported tool subset permits one function call per turn. The recorded OpenCode harness check uses a synthetic upstream; live-account harness verification is not recorded. The VM deployment currently requires SSH access and port forwarding; direct HTTP access from the university network is not available.
>
> [Full changelog](https://github.com/iteam7/gateway7/blob/ae766927fc8a18a277192491e9376b7a13446526/CHANGELOG.md#030---2026-10-31)

## Release and submission order

1. Keep the contributor-confirmed production commit and its green main CI fixed; do not replace that runtime revision with a later report-only commit.
   The minimum testability-plus-other-High CI checks pass; the network restriction and the remaining declared QRTs remain explicit limitations.
2. Choose the SemVer version and create its protected tag on that verified production commit on main.
3. Publish the short customer-facing body with the final `Full changelog` line, and merge the dated released section in `CHANGELOG.md`; leave a new empty `Unreleased` section.
   Before considering publication complete, confirm that the final changelog link resolves.
4. Merge the plan's REL-05 block: `Released` with the real tag link and date; `Checked QRs` with each QR having any test checked in SPRINT-05, even if another check failed or remains unverified, followed by one testing-plan link.
5. Use the confirmed retrospective and known accepted `8 SP` scope, explicitly reschedule unfinished sprint issues as instructed by the contributor, and close the milestone after the release; do not reconstruct the missing original commitment.
6. Merge the final Week 05 report after its release and linked artifacts, updating this checkpoint with the facts actually completed.
7. Take the report permalink and the ZIP snapshot from that same full merged main SHA; documentation after tagging means this submission SHA can be later than the production tag.
8. Produce the private PDF within two pages, including the verified team details, exact report permalink, current private addresses, SSH access instructions and recording access; the contributor has authorised the Gateway7 transcript as a private-only appendix, separate from the two-page limit.
   State that the direct campus-HTTP requirement is not fulfilled instead of claiming that the SSH arrangement satisfies it.
9. Verify the PDF and ZIP identify the same submission SHA, then upload both to Moodle and record only the upload actually performed.

An intermediate PDF and ZIP identifying a pull-request head are review candidates only.
They must say draft and unmerged, and be rebuilt after the final report and its evidence merge into main.
