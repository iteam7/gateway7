# Glossary

The words Gateway7 uses in one way only.

## Request Flow

### Client

An application or developer that calls Gateway7 with its own bearer token and may use only the models in its configured allowlist.

**Defined by:** [client authentication and model permissions](authentication.md#configure-clients).

### Operator Session

A server-stored browser login for a named operator, represented by an opaque HttpOnly cookie and a separate CSRF proof for administrative writes.
It expires independently of application client keys and can be ended by logout, password reset or operator revocation.

**Defined by:** [FR-031](functional-requirements/fr/FR-031.md).

### Managed Policy

A bounded text-policy definition created from a supported console template and activated globally or for selected clients after their configured middleware baseline.
Its settings are data rather than a new Python module or arbitrary executable code.

**Defined by:** [FR-032](functional-requirements/fr/FR-032.md).

### Provider

The one LLM service, OpenAI, Claude or Gemini, that a running gateway is configured at startup to forward allowed requests to.

**Defined by:** [CON-01](product-vision.md#con-01).

### Provider Adapter

The gateway component that translates a normalized request for the configured provider, attaches the server-held provider key and normalizes the provider's response or error.

**Defined by:** [the architecture](architecture/README.md).

### Model Allowlist

The list of model identifiers on the configured provider that one client may request, checked before any middleware or provider call.

**Defined by:** [client authentication and model permissions](authentication.md#configure-clients).

## Plugins

### Middleware

A trusted, company-authored Python module that can change or deny a chat request before it reaches the provider and the response on its way back.
In the middleware configuration and guide, "plugin" means this middleware, using the `PLUGIN` descriptor and API version 2.

**Defined by:** [DEC-016](decisions.md#dec-016) and [the plugin guide](plugins.md#descriptor-and-hooks).

### Middleware Chain

The single ordered list of enabled middleware instances in the configuration, run in that order on the request and in reverse order on the response.

**Defined by:** [the plugin guide](plugins.md#order-enable-and-required).

### Deny

The result a middleware returns to stop a request or response, which the client receives as the gateway's safe `policy_denied` error.

**Defined by:** [the plugin guide](plugins.md#descriptor-and-hooks).

### Own-Work Budget

The time one middleware instance may spend on its own request and response work, excluding the time it waits for the next handler, set by `limits.hook_timeout_seconds`.

**Defined by:** [the plugin guide](plugins.md#deadlines-and-diagnosis).

### Provider Transport

A trusted networking extension that supplies the provider adapter's outbound HTTP transport.
Its `TRANSPORT` descriptor uses API version 1 and creates one transport at startup; it is separate from the middleware chain and has no `call_next`.
The built-in proxy transport is one such extension.

**Defined by:** [the transport guide](provider-transports.md) and [ADR-004](architecture/adr/ADR-004.md).

## Operation

### Telemetry

The events about product use and signals about operation that Gateway7 sends to external backends, with analytics and operating-signal collection enabled separately by the operator.

**Defined by:** [the observability plan](observability.md#collected-data).

### Signal

One kind of telemetry the gateway reports about its own operation, either a metric or a log in this project, from which an operator reads how requests are served.

**Defined by:** [the observability plan](observability.md#the-signals).

### Service Level Indicator

A service level indicator, or SLI, is a numbered quality signal with a fixed definition, unit, window, source and query that a quality requirement test reads, such as [SLI-01](observability.md#sli-01).

**Defined by:** [the observability plan](observability.md#the-slis).

### Observability

The operator's ability to find out from the gateway's signals alone why a request failed or slowed, without reading request content or attaching a debugger.

**Defined by:** [FR-014](functional-requirements/fr/FR-014.md).

### Event

A fixed, typed record of a core-task action, such as a chat starting or completing, with a random task identifier and a server-owned traffic source.

**Defined by:** [the analytics event registry](analytics.md#the-events).

### Focus Metric

The one number the analytics plan uses to read the value expressed by [VP-01](research/value-proposition.md#vp-01-predictable-local-preflight-for-small-teams), distinct from operational request-duration signals.

**Defined by:** [the analytics metric tree](analytics.md#the-metric-tree).

### Counter-Metric

The metric that guards the focus metric against harmful growth rather than contributing to its count.

**Defined by:** [the analytics metric tree](analytics.md#the-metric-tree).

### Smoke Traffic

Synthetic traffic generated to check the staging pipeline, tagged `source=smoke` and excluded from every default analytics metric.

**Defined by:** [the analytics event registry](analytics.md#the-events).

### Analytics Pipeline

The optional path from gateway core-task events to an environment's analytics project and its charts.

**Defined by:** [the analytics plan](analytics.md#the-pipeline).

### Observability Pipeline

The optional path from gateway logs and duration observations to an environment's observability organization and its SLI chart.

**Defined by:** [the observability plan](observability.md#the-pipeline).

## Usability Testing

### Usability Test

A scripted session in which a participant outside the team runs the product's main task and two adjacent tasks, while an observer records the completion, the assistance, the time, the ratings, and the friction.

**Defined by:** [UT-01](usability-tests/ut-01/README.md).

### Participant

An adult aged 18 or older who matches the test's participant profile and is not a teammate, the Customer, an instructor, or course staff.

**Defined by:** [the participant profile](usability-tests/ut-01/README.md#participant-profile).

### Usability Session

One run of the test's tasks with one participant, from the welcome to the debrief, recorded under the participant's `P-nn` code.

**Defined by:** [the session template](usability-tests/ut-01/sessions/README.md).

### Consent

The durable, signed agreement a participant gives before a counted session, covering the adult declaration, the recording, the sanitized public results, the withdrawal, and the deletion after grading.

**Defined by:** [the consent template](usability-tests/ut-01/consent.md).

### Recording

The screen-and-audio capture of a counted session, mandatory for counting it, kept in the team's cloud folder and never published.

**Defined by:** [the consent template](usability-tests/ut-01/consent.md).

### Measure

A quantity the test records for one participant and one task, such as the SEQ rating or the time on task.

**Defined by:** [UT-01's measures](usability-tests/ut-01/README.md#measures).

### Metric

A product-analytics number computed from the gateway's events, such as successful gateway tasks per week; it is not a measure a usability session records.

**Defined by:** [the analytics plan](analytics.md#the-value-and-the-metrics).

### Statistic

The summary computed from a measure's recorded values, such as a count, a proportion, a median, or a mean; the analysis plan reports it, and a quality requirement's criterion uses one.

**Defined by:** [UT-01's analysis plan](usability-tests/ut-01/README.md#analysis-plan).

### SUS

The System Usability Scale: ten standard items answered from strongly disagree (1) to strongly agree (5), scored `SUS = 2.5 × (20 + sum(odd) - sum(even))` from the raw responses.

**Defined by:** [the surveys](usability-tests/ut-01/surveys.md#sus-after-all-the-tasks).

### SEQ

The Single Ease Question asked after each task: `Overall, how difficult or easy was the task to complete?`, answered from 1 (very difficult) to 7 (very easy).

**Defined by:** [the surveys](usability-tests/ut-01/surveys.md#seq-after-each-task).

## Demonstration

### Synthetic Provider

The deterministic local stand-in for a real provider that the demo and tests use, which checks plugin behavior but proves nothing about a real provider.

**Defined by:** [DEC-011](decisions.md#dec-011).

## Repository Configuration

### Configuration

The selected settings, versions and instructions that determine how Gateway7 is built, checked, deployed and maintained.

**Defined by:** [the configuration plan](configuration-plan.md).

### Configuration Management

The process of identifying, reviewing, changing and tracing Gateway7's configuration so a tested baseline can be reproduced and its differences explained.

**Defined by:** [the configuration plan's upkeep procedure](configuration-plan.md#how-to-maintain-the-inventory).

### Configuration Review

An inspection of the actual configuration items, their connections and fitness for their purposes, including mandatory-state checks and a goal-based evaluation; inaccessible settings are explicit limitations.

**Defined by:** [the configuration plan](configuration-plan.md#how-to-maintain-the-inventory).

### Configuration Plan

The maintained inventory that identifies Gateway7's configuration items, maintenance owners, locations, directed connections and expected good states.

**Defined by:** [the configuration plan](configuration-plan.md).

### Configuration Item

One identifiable, maintained unit of configuration assigned a stable CFG-nn section; a file family may be one unit, while an ordinary weekly report is an output instance.

**Defined by:** [the configuration plan](configuration-plan.md#how-to-maintain-the-inventory).

### Configuration Evaluation

An assessment of how convenient Gateway7's artifact set is for an explicit local goal, within mandatory course constraints; it is separate from checking whether each configuration item conforms to its declared good state.

**Defined by:** [the configuration plan](configuration-plan.md#how-to-maintain-the-inventory).

### Baseline

The frozen, identified source commit/tag state, resolved dependencies, tools and relevant environment against which Gateway7's configuration is evaluated; a release baseline additionally identifies its actual tag and deployment evidence.

**Defined by:** [the configuration plan](configuration-plan.md#how-to-maintain-the-inventory).

### Upkeep

The same-pull-request update of affected inventory entries, connections and related terms or risks when Gateway7's configuration changes.

**Defined by:** [the configuration plan's upkeep procedure](configuration-plan.md#how-to-maintain-the-inventory).

### Reproducible Build

A build whose source, resolved dependencies, tools and relevant environment are sufficiently fixed to reproduce the evaluated output; matching a version string or retaining uv.lock alone does not establish this.

**Defined by:** [CFG-08](configuration-plan.md#cfg-08) and [CFG-09](configuration-plan.md#cfg-09).

### Dependency Pinning

Constraining a dependency to an identified version, resolved lock entry or immutable digest rather than accepting an unspecified newer resolution.
A version tag can still move; Gateway7 distinguishes version-pinned container tags from digest-pinned images.

**Defined by:** [CFG-08](configuration-plan.md#cfg-08) and [CFG-09](configuration-plan.md#cfg-09).

### Secret

A private value granting access or protecting confidential state, such as a provider key, client/operator token, database password, ingestion credential or encryption key.
The public template records variable names and empty placeholders only.

**Defined by:** [CFG-07](configuration-plan.md#cfg-07).

## Agent Context

### Context Window

The finite amount of instructions, source and conversation an AI model can consider in one generation; earlier evidence may no longer be available after context reduction or a handoff.

**Defined by:** [CFG-11's instruction boundary](configuration-plan.md#cfg-11).

### Agent Instruction

A rule supplied to an AI agent that governs its permitted work, artifact conventions or verification steps; Gateway7's repository-wide instructions live in AGENTS.md and its role definitions.

**Defined by:** [CFG-11](configuration-plan.md#cfg-11).
