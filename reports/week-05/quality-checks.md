# Week 05 quality check evidence

Recorded on 31 October 2026 for [task #133](https://github.com/iteam7/gateway7/issues/133).
The [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan) remains the result index; this file states what the checks actually covered.

## CI checks

All five required workflows passed on main commit `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`.
The published [v0.3.0 tag](https://github.com/iteam7/gateway7/releases/tag/v0.3.0) identifies this same runtime commit.
The [Python check job](https://github.com/iteam7/gateway7/actions/runs/41130602373/job/124320199306) reports `1088 passed in 46.82s`, including both testability tests and the confidentiality test.
Its `Run tests` step took 48 seconds and the separate HTTP demo step took 12 seconds.
Those checks support **Passes** for QR-02 QRT-01 and QR-03 QRT-01 at their declared CI level; they do not establish a university-VM result.

## QR-01 Linux execution

- **Runtime source:** main commit `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`; 37 runtime, configuration and lockfile blobs matched the remote source with zero mismatches.
- **Environment:** Linux, CPython 3.12.14, cached locked dependencies and an isolated virtual environment outside the checkout.
- **Command:** `uv run --offline --locked python -m demo.fault_tolerance --runs 50`.
- **Exit:** `0`.

| Case | Observed HTTP result | Repetitions | Upstream requests |
| --- | --- | --- | --- |
| Exception | `500 plugin_error` | 50 | 0 |
| Policy denial | `403 policy_denied` | 50 | 0 |
| Timeout overrun | `504 timeout` | 50 | 0 |
| Late result | `504 timeout` | 50 | 0 |

The harness reported `PASS QR-01: no failure case reached the provider` for this Linux run.
No real provider, paid API or university VM was contacted.
At this Linux-only checkpoint, the complete declared QRT also required Windows; the older Windows deadline-test repetitions in #84 are a different test set.
The plan row therefore remained **Not verified / Checked: None / Evidence: None** at that checkpoint.
The later native CI record below supplies the full cross-platform execution at CI level; this historical Linux run is retained separately.

## QR-01 native CI execution on 31 October

After [PR #162](https://github.com/iteam7/gateway7/pull/162) merged, the [Quality requirements run on main](https://github.com/iteam7/gateway7/actions/runs/41193629459) executed the unchanged fault-tolerance harness on native Windows and Linux.
QR-01 QRT-01 is maintained at CI level to match this automated execution; its four failure cases, both operating systems, 50 repetitions per case and safe-error/zero-forwarding criterion are unchanged.

- **Source:** both jobs recorded `6d3555247bfe8007a9963b14394434643dde0652`, the actual main checkout under test.
- **Command:** `uv run --locked python -m demo.fault_tolerance --runs 50` after `uv sync --locked --python 3.12`.
- **Environment:** the integration environment, using local recording-upstream and gateway processes with synthetic credentials.
- **Exit:** `0` in both jobs; the workflow preserves the command's exit code.

| Native runner | Observed runtime | Evidence |
| --- | --- | --- |
| Ubuntu | Linux, Python 3.12.3 | [Successful Ubuntu job](https://github.com/iteam7/gateway7/actions/runs/41193629459/job/124515294396) |
| Windows Server 2022 | Windows, Python 3.12.10 | [Successful Windows job](https://github.com/iteam7/gateway7/actions/runs/41193629459/job/124515294656) |

Both jobs printed the following case results:

```text
PASS raise: upstream requests=0; HTTP 500 plugin_error x50
PASS deny: upstream requests=0; HTTP 403 policy_denied x50
PASS overrun: upstream requests=0; HTTP 504 timeout x50
PASS late: upstream requests=0; HTTP 504 timeout x50
PASS QR-01: no failure case reached the provider
```

This is 200 requests per operating system, with no failure-case request reaching the recording upstream.
No real provider, paid API or university VM was contacted by this workflow.
The check happened after the v0.3.0 release cut, on the main commit stated above; it does not identify a new deployed VM revision or change the protected runtime tag.

## Staging check

The contributor reports OpenAI deployments in both staging and production in the [31 October follow-up](meeting-follow-up.md#planning-deployment-and-submission).
Later on 31 October, azamatbayramov explicitly confirmed seeing `PASS QR-03 QRT-02` for the full staging confidentiality check.

- **Environment:** the staging deployment on the university VM, run by the contributor.
- **Tool:** `scripts/check_confidentiality.py`, whose documented command is `python3 scripts/check_confidentiality.py --gateway "$STAGING_URL" --project gateway7-staging`.
- **Reported output:** `PASS QR-03 QRT-02`; no raw log, run identifier, timestamp suffix or individual search counts were supplied.
- **Measurement meaning:** the shipped script emits that PASS only when all expected HTTP-status comparisons hold, the combined logs/metrics/error-body search finds zero synthetic values and request metrics are present; it then exits 0.
- **Tested revision:** `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`; the contributor explicitly confirmed that the run used the same staging v0.3.0 deployment, rather than the later CI checkout.

The successful result is an operator report; the measurement meaning above follows from the [script at the confirmed tested revision](https://github.com/iteam7/gateway7/blob/a15b1cd14618ee7b5ac423f4aed5ed2f496f405d/scripts/check_confidentiality.py) rather than copied per-surface output.
The current script requests the model `fake`, and this record does not infer which provider configuration produced the reported result.
The reported staging PASS and explicit tested revision supply the deployed evidence linked from the plan; [release preparation](release-preparation.md#operator-evidence-handoff) retains the reproducible command and configuration precondition for future runs.

## Reported VM core verification

The contributor's [later 31 October confirmation](meeting-follow-up.md#later-deployment-and-private-submission-confirmation) identifies the same source commit for both environments and confirms that health, readiness and an OpenAI chat request succeeded in each.

| Environment | Source commit | Provider | Core result and source |
| --- | --- | --- | --- |
| Staging | `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d` | OpenAI | Passes, reported by azamatbayramov on 31 October. |
| Production | `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d` | OpenAI | Passes, reported by azamatbayramov on 31 October. |

No raw remote command output or independent image inspection is claimed by this record.
These functional checks do not exercise the deployed confidentiality QRT; its separately reported PASS and tested revision are recorded in [the staging check](#staging-check).
The contributor's [later HTTP access clarification](meeting-follow-up.md#http-access-clarification-on-31-october) supersedes the earlier SSH-only description and reports campus HTTP availability.
The access clarification is not an independent network probe or a new QRT result; the private submission holds the actual addresses and access instructions.
