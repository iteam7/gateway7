# Alternatives

**Problem space:** Small application teams need to send text conversations to different LLM providers while applying inspectable, locally controlled rules that reduce accidental disclosure of sensitive information without reimplementing the rules in every application.

**Status:** Documentation research checked on 2026-09-30. This is a proposed user segment, not a customer-validated finding. No product was installed or benchmarked. gateway7 capabilities below are proposals, not implemented features. A library is compared as an application-level substitute, not misrepresented as a complete gateway.

**Research-board arrangement:** The [Markdown gallery](../../reports/week-01/evidence-gallery.md) contains nine documentation screenshots (at least two per alternative), with dates, captions and sources. It is proposed as the navigable, read-only evidence overview, with images in the weekly report. The research guide permits repository screenshot storage, but the assignment separately requests a board. This is a declared deviation requiring course/Customer acceptance; public access is available on the PR branch; course acceptance is not yet confirmed. No external board has been created.

See the [candidate search](../../reports/week-01/candidate-list.md), [comparison](comparison.md), [gap hypotheses](gap-analysis.md), and [proposed value](value-proposition.md).

**Kickoff update, 2026-10-03:** The [October 2 meeting](../../reports/week-01/meeting-report.md) clarified a corporate plugin host covering requests and responses; privacy filtering is one plugin. The privacy-focused research below is retained as one part of that broader direction, not treated as a complete evaluation of every gateway function.

## Properties

The evaluation framework is listed here for review. Because the initial research and criteria refinement occurred together, the team must not claim a separately committed, pre-evaluation criteria decision that did not happen.

1. **P1: Provider integration** — who implements the client interface and provider adapters?
2. **P2: Processing boundary** — where can raw text be inspected, and what extra services receive it?
3. **P3: Filtering scope and action** — what is checked, when, and can content be masked or blocked?
4. **P4: Domain-rule extensibility** — how are organization-specific identifiers or policies added?
5. **P5: Deployment and entitlement** — what must be operated, purchased, or checked for the chosen configuration?
6. **P6: Decision evidence** — what information helps explain and verify filtering behavior?
7. **P7: Failure and usability trade-offs** — what can cause missed protection, lost context, or additional latency?

## ALT-01: Portkey AI Gateway (direct competitor)

**Product / official source:** [Documentation or project repository](https://github.com/Portkey-AI/gateway).

**Audience / job (research framing):** Developers and platform teams needing multi-provider routing with configurable request and response checks.

**Evaluation depth:** Published documentation and screenshot inspection only; no installation, runtime test or benchmark.

**Property coverage:** P1: O1; P2: O1/O3; P3: O2/O3; P4: O2/O3; P5: O1/O2; P6: O4; P7: O2/O3. Each P1–P7 observation and its interpretation is compared in [the matrix](comparison.md); O references below are local to this alternative.

**Version / date checked:** Public product documentation and gateway main README, 2026-09-30; README setup/guardrail screenshots added 2026-10-03; no release installed. The product docs now display PRISMA AIRS AI Gateway branding, while the repository retains Portkey naming. The README describes a 2.0 pre-release; do not combine its promised feature set with the currently documented configuration.

### Observations

- **O1:** The repository shows a local Node.js gateway, an OpenAI-compatible client, provider routing, retries, and fallbacks. Enterprise and hosted capabilities are separately described. [Official gateway README](https://github.com/Portkey-AI/gateway/blob/main/README.md)
- **O2:** Product guardrails are tiered: BASIC on Developer, additional PARTNER/PRO on Production, and custom guardrails on Enterprise. The general guide states that checks evaluate only the final request message. [Guardrails guide](https://portkey.ai/docs/product/guardrails)
- **O3:** PII redaction can use provider integrations or BASIC Regex Match with a chosen replacement; both input and output hooks are documented. Redaction is irreversible, and original-data handling varies by provider. [PII redaction](https://portkey.ai/docs/product/guardrails/pii-redaction)
- **O4:** The PII guide exposes transformation indicators and check results. The captured limitations distinguish non-customizable pre-built patterns from the Regex Match route for custom patterns; do not generalize the pre-built limitation to all regex configuration. [PII redaction](https://portkey.ai/docs/product/guardrails/pii-redaction)

- **O5 (2026-10-03):** The README shows retry configuration and an output guardrail that denies a chosen word. This is documentation, not an executed test. [Gateway example](https://github.com/Portkey-AI/gateway#3-routing--guardrails)

### Strengths

- Combines integration and policy orchestration rather than requiring each application to build both (O1–O3).
- Existing custom regex redaction directly challenges a claim that gateway7 uniquely supports organization-specific formats (O3).

### Weaknesses

- The documented last-message scope needs verification for multi-turn histories containing earlier sensitive text; it is not evidence that all Portkey configurations are unsafe (O2).
- One-way replacement can remove information needed by downstream workflows; teams must also verify the chosen provider's data boundary and tier rather than assuming all checks execute locally (O2–O3).

## ALT-02: Presidio with application middleware (adjacent substitute)

**Product / official source:** [Documentation or project repository](https://presidio.dataprivacystack.org/).

**Audience / job (research framing):** Application developers who want to detect and transform sensitive text locally within an existing provider-call workflow.

**Evaluation depth:** Published documentation and screenshot inspection only; no installation, runtime test or benchmark.

**Property coverage:** P1: O1/O4; P2: O1/O2; P3: O2/O3; P4: O2/O3; P5: O1/O4; P6: O2/O5/O6; P7: O1/O4. Each P1–P7 observation and its interpretation is compared in [the matrix](comparison.md); O references below are local to this alternative.

**Version / date checked:** Current official documentation, 2026-09-30; no release installed. Former Microsoft project links redirect to Data Privacy Stack, and current documentation describes a community transition.

### Observations

- **O1:** Presidio supplies detection and anonymization modules, with Python, Docker, and Kubernetes usage options. Its own warning states automated detection cannot guarantee that every sensitive item is found. [Project documentation](https://presidio.dataprivacystack.org/)
- **O2:** Analyzer supports built-in and custom recognizers using rules and models. Results identify entity type and text span; the architecture exposes recognizers and an NLP engine. [Analyzer](https://presidio.dataprivacystack.org/analyzer/)
- **O3:** Anonymizer is a separate transformation component with configurable operators. The application chooses how its analysis results affect outgoing requests. [Anonymizer](https://presidio.dataprivacystack.org/anonymizer/)
- **O4:** The documented modules are privacy-processing components. In this substitute, provider routing, request interception, authentication, and application-wide enforcement are integration work, not properties demonstrated by those modules. This is an architectural inference from O1–O3, not a claim about every Presidio-based product.

- **O5:** Analyzer decision explanations can expose recognizers, regex, contextual words and confidence changes; documented logging uses correlation IDs. These are reusable detection-level building blocks, not a complete gateway audit trail. [Decision process](https://presidio.dataprivacystack.org/analyzer/decision_process/)
- **O6 (2026-10-03):** Presidio documents evaluation tooling and synthetic dataset generation. Presidio-Research evaluates the analyzer and individual recognizers; detector evaluation is already supported. [Evaluation documentation](https://presidio.dataprivacystack.org/evaluation/) and [Presidio-Research](https://github.com/data-privacy-stack/presidio-research)

### Strengths

- Direct control of the detector pipeline makes it a credible reusable foundation for gateway7, rather than a detector that must be reinvented (O1–O3).
- Suitable for an existing application that needs a local processing step rather than another shared gateway (O1, O4).

### Weaknesses

- The team still owns the interception and provider-integration code; separate applications can apply policies inconsistently unless the integration is centralized (O4, inference).
- Detection errors remain possible, so representative evaluation and explicit handling of unsupported content are required (O1).

## ALT-03: LiteLLM Proxy with Presidio (open-source / self-hosted competitor)

**Product / official source:** [Documentation or project repository](https://docs.litellm.ai/docs/proxy/quick_start).

**Audience / job (research framing):** Developers and platform teams seeking a self-hosted multi-provider proxy with reusable local privacy checks.

**Evaluation depth:** Published documentation and screenshot inspection only; no installation, runtime test or benchmark.

**Property coverage:** P1: O1; P2: O2; P3: O2/O3/O6; P4: O2/O3; P5: O2/O5; P6: O4/O6; P7: O3. Each P1–P7 observation and its interpretation is compared in [the matrix](comparison.md); O references below are local to this alternative.

**Version / date checked:** Current official documentation, 2026-09-30; no release installed. Feature claims concern the documented paths below, not every historical version or paid feature.

### Observations

- **O1:** The proxy exposes common LLM interfaces and supports multiple providers, including local model endpoints; its quickstart supports configuration-driven startup. [Proxy quickstart](https://docs.litellm.ai/docs/proxy/quick_start)
- **O2:** The Presidio integration uses analyzer and anonymizer services, including localhost endpoints. It supports entity-specific mask/block decisions, custom recognizers, output scanning, and optional restoration. `logging_only` does not sanitize the upstream request. [Presidio integration](https://docs.litellm.ai/docs/proxy/guardrails/pii_masking_v2)
- **O3:** Custom guardrail classes can edit or block content. The guide warns that `during_call` runs concurrently and edits may not precede transmission. Streaming behavior differs between hooks and buffered built-ins. [Custom guardrails](https://docs.litellm.ai/docs/proxy/guardrails/custom_guardrail)
- **O4:** Presidio tracing includes entity categories, scores, and execution duration. This is evidence that explainability is already supported, not unique to gateway7. [Presidio integration](https://docs.litellm.ai/docs/proxy/guardrails/pii_masking_v2)
- **O5:** The separately documented `hide-secrets` integration is labelled Enterprise-only and uses `detect-secrets`; this does not imply all custom secret filtering requires that tier. [Secret detection](https://docs.litellm.ai/docs/proxy/guardrails/secret_detection)
- **O6 (2026-10-03):** LiteLLM documents `default_on` guardrails that run even when callers supply an empty `guardrails` array, optional execution records in non-streaming responses, and `mock_response` testing without an LLM call. These are documentation observations, not executed results. [Guardrails quickstart](https://docs.litellm.ai/docs/proxy/guardrails/quick_start) and [Mock completions](https://docs.litellm.ai/docs/completion/mock_requests)

### Strengths

- Strongest reuse baseline: existing routing, local filtering, and extension hooks substantially overlap the proposed project (O1–O3).
- Existing filter traces and restoration make simplistic “no visibility” or “no reversible masking” claims indefensible (O2, O4).

### Weaknesses

- The documented Presidio route entails operating additional services, not merely starting a bare proxy (O2).
- Protection depends on hook timing and output-delivery configuration. A team must test the selected mode rather than treating every guardrail as preventive (O3).

## ALT-04: Kong AI Gateway on-prem with AI PII Sanitizer (enterprise competitor)

**Product / official source:** [Documentation or project repository](https://developer.konghq.com/ai-gateway/).

**Audience / job (research framing):** Teams already using or considering an enterprise API gateway who need provider access and centrally configured sanitization.

**Evaluation depth:** Published documentation and screenshot inspection only; no installation, runtime test or benchmark.

**Property coverage:** P1: O3/O4; P2: O1; P3: O2; P4: O2/O3; P5: O1/O3; P6: O4; P7: O2/O3. Each P1–P7 observation and its interpretation is compared in [the matrix](comparison.md); O references below are local to this alternative.

**Version / date checked:** Current documentation, 2026-09-30. AI PII Sanitizer minimum Kong Gateway 3.10; response scanning is marked 3.12+. The on-prem setup guide addresses AI Gateway 2.0 configuration translation. No deployment tested.

### Observations

- **O1:** The AI PII Sanitizer requires an AI license, extends AI Proxy/AI Proxy Advanced, and calls a separately deployed anonymizer service, available as Docker images. External to the gateway process does not mean outside the operator's network. [AI PII Sanitizer](https://developer.konghq.com/plugins/ai-sanitizer/)
- **O2:** The plugin documents request/response sanitization, placeholders or synthetic replacements, optional restoration, and custom regex patterns. [AI PII Sanitizer](https://developer.konghq.com/plugins/ai-sanitizer/)
- **O3:** On-prem configuration uses Services, Routes, and plugins; Konnect entity definitions can be translated into those primitives. Some entity mappings are not one-to-one. [On-prem configuration](https://developer.konghq.com/ai-gateway/configure-on-prem/)
- **O4:** Kong documents provider integration and observability through logs, metrics, and tracing. These general facilities do not establish that a particular deployment avoids recording raw prompts. [AI Gateway overview](https://developer.konghq.com/ai-gateway/)

### Strengths

- Appropriate for organizations already operating Kong because AI policy fits existing gateway primitives (O3, inference).
- Local deployment and configurable sanitization already exist; neither is a unique project feature (O1–O2).

### Weaknesses

- AI licensing and a separate PII service are explicit dependencies for this configuration (O1).
- Version distinctions and entity-to-plugin translation add configuration work; successful on-prem setup does not follow from copying any Konnect example unchanged (O3).

## Evidence limits

These observations establish documented capabilities, not measured accuracy, throughput, setup time, security certification, or suitability for the Customer. No claim that a competitor lacks an unmentioned capability is made. Use synthetic examples for future tests; do not submit actual secrets or personal data to demonstrations. Resolve discrepancies against a pinned release before implementing or benchmarking.
