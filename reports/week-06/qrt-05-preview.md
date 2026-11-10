# QR-05 QRT-01 staging preview

On 7 November 2026, a separate VM-hosted candidate built from commit `22ecc152f57ad096cd942050cd46d6d3457fb93d` used the existing staging gateway configuration and the staging OpenObserve organization.
The operator ran the current `scripts/check_sli.py` inside that candidate with the staging query credential and a staging client token.
The candidate's commit and target were operator assertions rather than remote attestation.

The synthetic forbidden-model request returned HTTP 403 and `model_forbidden` without a provider request.
The request log was queryable in 1.046 seconds and the five-minute `openai_chat / client_error` P95 series in 4.144 seconds; its observed value was 96.25 milliseconds and the histogram count increased by one.
The preview command returned `PASS QR-05 QRT-01`.

The operator repeated the check from the deployment machine through SSH forwarding at 18:54 UTC against the same candidate and staging organization.
That run returned `PASS`, with the log queryable in 1.101 seconds, the failure P95 in 6.218 seconds and the observed five-minute P95 at 4.75 milliseconds.
Both the commit and staging target remain operator assertions.

This is preview evidence, not a pass for the regular staging deployment or a replacement for the testing-plan row.
A separate synthetic core-task request against this candidate returned HTTP 502 with the gateway reporting a provider authentication diagnostic.
A direct provider API check from the VM returned a country or territory restriction and did not establish whether the key itself is valid.
The team must resolve provider access, promote the candidate and rerun the deployed verification before recording a staging pass or promoting to production.
