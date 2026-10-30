# REL-05 preparation

Prepared on 30 October 2026 under [task #133](https://github.com/iteam7/gateway7/issues/133).
**Status: incomplete; no REL-05 tag, release, final production verification or Moodle upload is claimed.**
The [Week 05 report](README.md) indexes the public evidence; this file keeps the remaining release handoffs explicit.

## Verified checkpoint

The latest inspected main commit is [`b0b91399f5c9c0eb5d285adbfce7d5f875c6192e`](https://github.com/iteam7/gateway7/commit/b0b91399f5c9c0eb5d285adbfce7d5f875c6192e).
Its [Python check job](https://github.com/iteam7/gateway7/actions/runs/41069175092/job/124108430488) reports `1088 passed in 46.72s`, including `tests/test_testability.py` and `tests/test_confidentiality.py`.
The named `Run tests` step took 48 seconds and `Exercise separate HTTP processes` took 12 seconds, satisfying QR-02's five-minute bounds.
The [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan) records the two CI results at that commit.
No cross-platform QR-01 or staging QR-03 QRT-02 result is inferred from this CI run.

[PR #147](https://github.com/iteam7/gateway7/pull/147) records staging and production health/chat verification at `26dab3122dbc2f4247533d0c57cdb0f83e5073cf` with the synthetic provider.
It says the VM was available; lack of access from this preparation environment does not establish the assignment's VM-unavailable exception.
The newer release candidate still needs deployment evidence.

## Handoffs before publication

| Handoff | Required completion |
| --- | --- |
| Review and human records, [#132](https://github.com/iteam7/gateway7/issues/132) | Obtain actual story verdicts and participant confirmation, conclude the real retrospective and add human AI assessments; preserve unanswered points. |
| Final candidate, [#133](https://github.com/iteam7/gateway7/issues/133) | Merge the intended work and identify its exact main commit; record any genuinely agreed rework deferral. |
| Deployment, [#134](https://github.com/iteam7/gateway7/issues/134) | Deploy the candidate to staging, run the declared staging QRT, then promote the same commit to production and verify the core task from the campus network. |
| Quality evidence, [#136](https://github.com/iteam7/gateway7/issues/136) and [#137](https://github.com/iteam7/gateway7/issues/137) | Refresh the CI proof on the final candidate; record scripted/deployed output at its declared level and keep every unknown or failed result explicit. |
| Sprint closeout, [#138](https://github.com/iteam7/gateway7/issues/138) and [#139](https://github.com/iteam7/gateway7/issues/139) | Verify refinement links and scheduling, record genuine Customer-accepted completed points, and explicitly move unfinished issues before closing the milestone. |
| Private submission, [#133](https://github.com/iteam7/gateway7/issues/133) | Confirm the private team details, VM addresses, recording access and transcript permissions, then build the final PDF and source snapshot from the common merged report commit. |

## Operator evidence handoff

Use the existing [manual deployment runbook](../../docs/deployment.md#manual-deployment) and the environment's already prepared checkout and separate ports, configuration and credentials.
An on-campus operator runs the following commands on the VM; no hostname or checkout directory is supplied here.
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

## Customer-facing body draft

The following two paragraphs are the proposed customer-facing text; this is not a published release body.
The version and date are selected when the final production commit is verified.

> Gateway7 connects OpenAI-compatible agents through company middleware, with guarded function-tool turns, server-held credentials and configurable policies for both requests and answers. OpenAI startup is simpler, provider calls can use a proxy transport, and middleware diagnostics and examples help operators investigate failures and authors add their own policies.
>
> Streaming delivery is buffered until the complete response passes policy checks, and the supported tool subset permits one function call per turn. The recorded OpenCode integration uses a synthetic upstream; live-account harness verification and individual Customer story acceptance remain outstanding at this checkpoint.

Before publication, update the limitation paragraph to match the verified release state and append the required `Full changelog` Markdown link to its actual dated released section as the final line.
No prospective tag or nonexistent section is linked here.

## Release and submission order

1. Complete the Review/rework and final-candidate handoffs above, with green required CI and actual staging/production evidence naming the same commit.
2. Choose the SemVer version and create its protected tag on that verified production commit on main.
3. Publish the short customer-facing body with the final `Full changelog` line, and merge the dated released section in `CHANGELOG.md`; leave a new empty `Unreleased` section.
   Before considering publication complete, confirm that the final changelog link resolves.
4. Merge the plan's REL-05 block: `Released` with the real tag link and date; `Checked QRs` with each QR having any test checked in SPRINT-05, even if another check failed or remains unverified, followed by one testing-plan link.
5. Finish the actual retrospective and velocity record, explicitly reschedule open sprint issues and close the milestone after the release.
6. Merge the final Week 05 report after its release and linked artifacts, updating this checkpoint with the facts actually completed.
7. Take the report permalink and the ZIP snapshot from that same full merged main SHA; documentation after tagging means this submission SHA can be later than the production tag.
8. Produce the private PDF within two pages, including the required team details, exact report permalink, private addresses and recording/transcript explanation; an allowed private transcript appendix is separate from the two-page limit.
9. Verify the PDF and ZIP identify the same submission SHA, then upload both to Moodle and record only the upload actually performed.

An intermediate PDF and ZIP identifying a pull-request head are review candidates only.
They must say draft and unmerged, and be rebuilt after the final report and its evidence merge into main.
