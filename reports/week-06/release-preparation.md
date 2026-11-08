# REL-06 release preparation

The proposed next version is **v0.4.0**, following published [v0.3.0](https://github.com/iteam7/gateway7/releases/tag/v0.3.0).
Optional analytics and observability are new user-visible capabilities; the package and OpenAPI version correction also makes the installed build identifiable.
This file prepares the upgrade and publication steps; it records no tag, production deployment or completed REL-06.

## Candidate and scope

The package manifest and runtime version are `0.4.0`, and the HTTP application's version reads `gateway7.__version__`.
The installed-distribution/OpenAPI regression detects the earlier drift where newer tags still reported `0.1.0`.
The [Unreleased changelog](../../CHANGELOG.md#unreleased) owns the notable changes; earlier released sections and plugin API version 2 are unchanged.

The [readiness checkpoint](release-readiness.md) owns the operator evidence and remaining gaps.
US-04 supplies 5 completed SP at the 8 November checkpoint; the two 8-SP internal stories remain open.
Their proposed carryover to SPRINT-07 is a closeout proposal, not an applied milestone move or final Actual Velocity.
The old Windows [draft #78](https://github.com/iteam7/gateway7/pull/78) remains a carried retrospective action; its old workflow and frozen Week 3 edits are not part of this release-preparation change.

## Publication and submission checklist

1. Merge the reviewed candidate and verify its main checks, then select its full Git SHA.
   On staging, use the [manual deployment and image-revision checks](../../docs/deployment.md#manual-deployment); a checkout hash alone does not identify a running image.
2. Complete the private operator handoff in [readiness](release-readiness.md#operator-handoff-still-required).
   Retain raw query output privately and publish only the required sanitized evidence summary and captures.
   Do not populate a production dashboard by sending synthetic traffic.
3. Resolve the release decision with the acknowledged missing Customer Review.
   The course requires Review and rework before the release; a release cut without them must retain that unmet requirement and chronology deviation in the report.
4. Verify the selected production revision and release-tag protection, obtain publication authorization, and create the protected `v0.4.0` tag and same-titled release on that commit on main.
   This preparation does not perform those actions.
5. At the actual cut, move the included Unreleased entries into the real dated released section, then record the actual tag/date and checked QRs in the plan's REL-06 block.
   Until then that heading remains empty.
   Finalize the draft upgrade note's last link to that real released changelog section; its current link deliberately targets the existing Unreleased section.
6. Record the actual issue carryovers and completed-story sum before closing the sprint milestone.
   Preserve the original estimates and owners; the 21-SP later scope estimate is not the original commitment or Actual Velocity.
7. Merge the final public report and every linked repository artifact, select that final main SHA, and build the private Week 6 PDF and repository ZIP from exactly that SHA.
   The PDF has at most two main pages, carries the private access information and the truthful absence of a Review recording, and keeps the Week 5 files separate.
   File creation does not establish a Moodle upload; retain the actual upload result privately.

## Draft upgrade note

Gateway7 adds privacy-safe product events and structured request logs with a five-minute failure P95, so operators can follow core-task usage and diagnose failed requests.

From v0.3.0, redeploy the new image or wheel with its locked dependencies; no product-database migration is required.
Analytics and OTLP export remain opt-in.
To enable analytics, set `ANALYTICS_ENABLED=true`, the appropriate `GATEWAY7_ENVIRONMENT`, `OPENPANEL_API_URL`, and that environment's `OPENPANEL_CLIENT_ID`/`OPENPANEL_CLIENT_SECRET`.
Keep `ANALYTICS_SOURCE=web`; temporary smoke traffic belongs only in staging.
To enable observability, set `TELEMETRY_ENABLED=true`, `GATEWAY7_ENVIRONMENT=staging` or `GATEWAY7_ENVIRONMENT=production`, and that environment's `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS`.
Use the [telemetry deployment procedure](https://github.com/iteam7/gateway7/blob/main/docs/deployment.md#telemetry-pipelines) for the isolated backend scopes, credentials, networks and verification.

Policy errors now identify the denying middleware on both chat APIs, and startup diagnostics identify the configured instance and bounded unsupported action.
Existing `block` and `log` configurations require no policy migration; invalid actions were already rejected by v0.3.0.
The package and public OpenAPI metadata now report the prepared version consistently.

[Full changelog](https://github.com/iteam7/gateway7/blob/main/CHANGELOG.md#unreleased)
