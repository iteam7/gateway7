# Staging observability dashboard evidence

On 7 November 2026, a VM-hosted staging preview exported a deliberately denied synthetic request to the staging OpenObserve organization.
The [sanitized dashboard](images/observability-staging.png) shows `SLI-01 API request P95 by outcome` and the numeric `openai_chat / client_error` series.
The chart runs the SLI-01 query from the observability plan.
This preview is not the regular staging gateway; its promotion and verification remain outstanding.
