# Staging analytics dashboard evidence

On 7 November 2026, an isolated staging preview built from commit `22ecc152f57ad096cd942050cd46d6d3457fb93d` sent a synthetic unauthenticated chat request to the staging OpenPanel project.
The request returned HTTP 401 without a provider call.
The [smoke event detail](images/analytics-staging-smoke.png) shows its staging environment, smoke source and client-error outcome.

The [staging dashboard](images/analytics-staging.png) shows the `Task completion rate` report with no data after excluding smoke events; no production usage is inferred from this empty chart.
An OpenPanel count query for `chat_started` returned two when the filter was removed and no series when `properties.source is not smoke` was applied.
The staged preview is separate from the regular staging deployment, which still needs promotion and verification.
