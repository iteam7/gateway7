# REL-06 readiness checkpoint

Updated on 8 November 2026 from [main source checkpoint `8c01844489eff52b3211869a68e9f7f6576cb019`](https://github.com/iteam7/gateway7/tree/8c01844489eff52b3211869a68e9f7f6576cb019), the recorded operator observations and the contributor's confirmed retrospective.
The [release preparation](release-preparation.md) proposes `v0.4.0` and carries its upgrade-note draft; no REL-06 tag, final production revision or release publication is asserted.

## Source completion

- US-04 [#33](https://github.com/iteam7/gateway7/issues/33) is completed: [PR #209](https://github.com/iteam7/gateway7/pull/209) verifies all three unchanged policy criteria, and [DEC-020](../../docs/decisions.md#dec-020) retains its earlier Customer acceptance.
- The completed source and documentation tasks [#181](https://github.com/iteam7/gateway7/issues/181), [#183](https://github.com/iteam7/gateway7/issues/183) and [#186](https://github.com/iteam7/gateway7/issues/186) now carry checked criteria and their actual FR/ADR links.
  These narrow completions do not complete the regular pipelines in #178/#182, deployed check #185 or new internal stories #174/#175.
- The completed-story snapshot is **5 SP**, US-04 only; the later selected-scope estimate is 21 SP.
  [The plan](../../docs/project-plan.md#sprint-06) keeps this snapshot separate from unavailable original Planned Velocity and pending final Actual Velocity.
- Package and runtime metadata are prepared as `0.4.0`; public OpenAPI reads the runtime version, and the regression compares the project, installed distribution and public metadata.
  A prepared package version is not a published release or proof of the version running on the VM.

## Operator evidence retained

The candidate commit remains `22ecc152f57ad096cd942050cd46d6d3457fb93d`; the regular staging and production gateways have not been confirmed promoted to the final reviewed revision.

- The [candidate QRT record](qrt-05-preview.md) reports QR-05 QRT-01 PASS: the failed-request log appeared in 1.046 seconds and its five-minute failure P95 in 4.144 seconds; a repeat reports 1.101 and 6.218 seconds.
  Those are query-availability delays, not the P95 request duration.
- OpenPanel's separate staging/production projects and the four sanitized dashboard captures are recorded in [the weekly index](README.md#dashboard-and-candidate-evidence).
  Staging smoke was excluded from the analytics chart, and no smoke event was sent to production; an empty chart is not a measured zero.
- TLS backend health checks passed from the deployment machine and a team member’s Windows machine using the internal CA.
  Customer access and the private CA/credential handoff remain unverified in this submission record.
- The [team retrospective](sprint-retrospective.md), its observations and four carried actions were confirmed by azamatbayramov.
  Its recorded occurrence precedes formal sprint closeout; the report declares that ceremony-order deviation.

## Operator handoff still required

1. Establish a working provider network path and verify the core task on the selected staging revision.
   The recorded regional restriction does not establish that the API key is invalid; the configured [HTTP(S) proxy transport](../../docs/provider-transports.md#configure-the-built-in-proxy) is one available operator option.
2. Supply the full QRT stdout, matching request-ID log row/query and SLI result privately to the submission owner.
   Record the final staging URL, full deployed SHA and running image identity; the earlier candidate summary alone does not promote the regular deployment.
   The forbidden-model QRT makes no provider call, so it can be completed independently of provider network access.
3. Record a numerical result from a defined non-smoke analytics query and confirm retention configuration of at least seven days.
   This requires the configured retention, not waiting for seven days of history.
4. Complete the private CA/fingerprint, four dashboard URLs, two gateway URLs and environment-specific backend/query access handoff.
   Raw telemetry, credentials and infrastructure addresses stay private; only the required sanitized summary and screenshots belong in the public report.

## Release and submission

No Customer Review will take place before the deadline, as the contributor confirmed on 8 November; #188 remains unfulfilled.
The course places REL-06 after that Review and resulting rework.
Publishing without it would be a declared chronology deviation, not fulfillment of the missing Review or that sequence.

Once the operator evidence and final release decision are available, follow the [release and snapshot checklist](release-preparation.md#publication-and-submission-checklist).
The protected tag, production verification, final Actual Velocity, issue carryovers, sprint closure and private PDF/ZIP are still separate actions.
