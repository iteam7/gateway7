# REL-06 readiness checkpoint

This checkpoint retains the technical observations from 7 November 2026 and the contributor's deadline and retrospective confirmations from 8 November; it is not a release or a Customer verdict.
The candidate commit is `22ecc152f57ad096cd942050cd46d6d3457fb93d`, and the regular staging and production deployments still run an earlier commit.

## Evidence available

- A separate staging candidate using the staging configuration passed QR-05 QRT-01 against the staging OpenObserve organization; the log appeared in 1.046 seconds and the failure P95 in 4.144 seconds.
- OpenPanel staging and production projects and the four telemetry dashboards exist; staging smoke events were excluded from the analytics metric and no smoke event was sent to the production project.
- TLS health checks for both backends passed from the deployment machine and a team member’s Windows machine using the internal CA; Customer access has not been checked.
- The [staging SLI capture](observability-staging.md) and [candidate QRT record](qrt-05-preview.md) retain their original preview scope; the Week 6 index links all four prepared dashboard captures through immutable source commits.
- azamatbayramov confirmed the held [team retrospective](sprint-retrospective.md), its observations and four carried actions; formal sprint closeout and Actual Velocity remain pending.

## Outstanding before release

- Restore provider access from staging: a synthetic core-task request returned HTTP 502, and a direct provider check returned a country or territory restriction; the key itself has not been validated.
- Establish an approved network path from the server to the provider, potentially a VPN service if permitted by provider terms and institutional policy, or use an authorized alternative; then rerun the core-task check.
- Verify that OpenPanel retains the events needed for the seven-day metric window.
- Execute and retain the defined non-smoke analytics metric query; empty charts and unfiltered smoke counts are not a measured production value.
- Promote the final reviewed commit to regular staging, run its required deployed checks and core task, then deploy the same commit to production and verify its core task.
- Customer Review remains a release dependency, and the contributor confirmed that none would take place before the assignment deadline; #188 is unfulfilled and the prepared script is unused.
- Merge the verified evidence, record the checked QRs, prepare the release notes and changelog, and tag the final production commit only after the required approvals.
- Complete the private Moodle PDF with the verified endpoints, credentials and full commit permalink, and create the snapshot from that same merged commit.

The candidate, preview checks and empty production charts do not by themselves satisfy REL-06.
