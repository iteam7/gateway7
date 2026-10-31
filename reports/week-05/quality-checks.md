# Week 05 quality check evidence

Recorded on 31 October 2026 for [task #133](https://github.com/iteam7/gateway7/issues/133).
The [testing plan](../../docs/project-plan.md#quality-requirement-testing-plan) remains the result index; this file states what the checks actually covered.

## CI checks

All five required workflows passed on main commit `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d`.
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
The complete declared QRT also requires Windows; the older Windows deadline-test repetitions in #84 are a different test set.
QR-01 therefore remains **Not verified / Checked: None / Evidence: None** in its plan row until the same required cross-platform procedure is evidenced.
This supporting Linux record does not substitute for the missing Windows half.

## Staging check

The contributor reports OpenAI deployments in both staging and production in the [31 October follow-up](meeting-follow-up.md#planning-deployment-and-submission).
The current `scripts/check_confidentiality.py` scenario requests the model `fake`.
No passing QR-03 QRT-02 run against that reported deployment has been supplied, so the plan retains **Not verified**; [release preparation](release-preparation.md#operator-evidence-handoff) describes the required output and configuration precondition.

## Reported VM core verification

The contributor's [later 31 October confirmation](meeting-follow-up.md#later-deployment-and-private-submission-confirmation) identifies the same source commit for both environments and confirms that health, readiness and an OpenAI chat request succeeded in each.

| Environment | Source commit | Provider | Core result and source |
| --- | --- | --- | --- |
| Staging | `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d` | OpenAI | Passes, reported by azamatbayramov on 31 October. |
| Production | `a15b1cd14618ee7b5ac423f4aed5ed2f496f405d` | OpenAI | Passes, reported by azamatbayramov on 31 October. |

No raw remote command output or independent image inspection is claimed by this record.
These functional checks do not exercise the deployed confidentiality QRT and do not replace its missing result.
Access currently requires SSH and port forwarding; direct HTTP access from the university network remains an explicit deployment deviation.
The private submission holds the actual addresses and access instructions.
