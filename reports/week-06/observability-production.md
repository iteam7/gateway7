# Production observability dashboard evidence

On 7 November 2026, the production OpenObserve organization contained an SLI-01 dashboard using the same query as the staging dashboard.
The [sanitized production dashboard](images/observability-production.png) shows no data; no synthetic failure was sent to the production organization for this check.
The regular production gateway still needs the updated telemetry configuration and verified deployment before its SLI can be demonstrated.
