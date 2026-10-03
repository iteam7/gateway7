# Alternative analysis: documentation evidence gallery

The source package records these public-documentation screenshots as captured on **2026-09-30 (UTC)**. The original image bytes were restored unchanged and all ten original images were visually rechecked on **2026-10-03 (UTC)**. They establish documented capabilities and constraints, **not executed runtime tests**, measured performance, or proof of compliance. No visible account identity, private personal data, or credentials were found in the image pixels.

This public gallery contains seven screenshots for ALT-02–ALT-04. ALT-01 screenshots are withheld until rights-cleared replacement evidence is available; the two-per-alternative requirement is not yet met. The preserved Kong crops show limitations and dependencies without shrinking an entire page into unreadable text. Source links identify the original documentation; captions summarize only assertions visible in each crop. Pricing pages were not used.

## Evidence map

| Alternative | Properties / observations supported | Screenshots |
| --- | --- | --- |
| [ALT-01](../../docs/research/alternatives.md#alt-01-portkey-ai-gateway-direct-competitor) | P3/P4/P6/P7; O2–O4 | Withheld: two rights-cleared screenshots still required |
| [ALT-02](../../docs/research/alternatives.md#alt-02-presidio-with-application-middleware-adjacent-substitute) | P2/P4/P6/P7; O1/O2/O5 | Features/warning, decision trace |
| [ALT-03](../../docs/research/alternatives.md#alt-03-litellm-proxy-with-presidio-open-source--self-hosted-competitor) | P2/P3/P5/P7; O2/O3 | Deployment dependencies, hook timing |
| [ALT-04](../../docs/research/alternatives.md#alt-04-kong-ai-gateway-on-prem-with-ai-pii-sanitizer-enterprise-competitor) | P2/P3/P5/P7; O1–O3 | License/sanitization, service flow, on-prem configuration |

Source owners retain rights in the documentation and product names shown; these excerpts are attributed Week 1 research evidence, not gateway7 product assets. See [attribution and reuse limits](../../ATTRIBUTION.md).

## ALT-01 — Portkey

Two public screenshots are still required. Three documentation crops were inspected privately, but their documentation redistribution license was not established. They are not included in this public tree. The official [PII redaction documentation](https://portkey.ai/docs/product/guardrails/pii-redaction) and [guardrails guide](https://portkey.ai/docs/product/guardrails) remain the primary sources for ALT-01 O2–O4. The MIT license of the separate gateway software repository is not assumed to cover those pages.

## ALT-02 — Presidio

### 01 — Inspect detection capabilities and warning

![Presidio main features and automated-detection warning](images/alternatives/ALT-02-01-features-warning.jpg)

- **Source:** [Presidio: Main features](https://presidio.dataprivacystack.org/#main-features)
- **Visible evidence:** Predefined/custom recognizers, NER, regex, rule-based logic, checksums, multiple languages, external detection models, Python/PySpark/Docker/Kubernetes usage, customizable identification/anonymization and image-text redaction. The warning explicitly says automated detection does not guarantee finding all sensitive information and additional protections are needed.
- **Interpretation:** A strong customizable engine is documented, but no zero-miss security guarantee is supported.

### 02 — Inspect decision traceability

![Presidio analyzer decision-process explanation](images/alternatives/ALT-02-02-decision-trace.jpg)

- **Source:** [The Presidio-analyzer decision process](https://presidio.dataprivacystack.org/analyzer/decision_process/)
- **Visible evidence:** Explanations can identify the recognizer, regex, ML interpretability mechanism, contextual words and confidence changes. The beginning of the usage section describes logging the decision process to investigate a request. The bottom of this crop is cut off, so correlation-ID details are not legibly shown.
- **Interpretation:** Detection explanations are a documented building block for an audit trail. The linked source additionally describes request correlation, but that detail must not be attributed to this crop. This is not evidence of a complete gateway product or a deployed audit system.

## ALT-03 — LiteLLM + Presidio

### 01 — Configure dependency endpoints

![LiteLLM Presidio deployment prerequisites and endpoint configuration](images/alternatives/ALT-03-01-deployment.jpg)

- **Source:** [PII, PHI Masking — Presidio: Deployment options](https://docs.litellm.ai/docs/proxy/guardrails/pii_masking_v2#deployment-options)
- **Visible evidence:** The integration requires deployed Presidio Analyzer and Anonymizer containers. The UI setup instructions select Presidio PII and enter the analyzer/anonymizer endpoints.
- **Interpretation:** LiteLLM provides gateway integration while detection and anonymization depend on separately deployed services. This crop does not show or verify a running localhost endpoint.

### 02 — Select hook timing and inspect streaming limitations

![LiteLLM custom guardrail modes and streaming audit-only caveat](images/alternatives/ALT-03-02-modes-streaming.jpg)

- **Source:** [Custom Guardrail](https://docs.litellm.ai/docs/proxy/guardrails/custom_guardrail)
- **Visible evidence:** The mode table distinguishes pre-call, during-call and post-call. Pre-call is recommended for masking or rewriting; during-call edits may arrive too late. The streaming note says ordinary post-call checks run after chunks reach the client and are audit-only. A streaming-iterator hook is named for real-time chunk filtering/blocking.
- **Interpretation:** A non-streaming post-call check is not sufficient evidence of safe streaming interception. Hook selection is an important integration requirement.

## ALT-04 — Kong AI Gateway / AI PII Sanitizer

### 01 — Inspect product scope and licensing

![Kong AI PII Sanitizer license and documented sanitization features](images/alternatives/ALT-04-01-license-sanitization.jpg)

- **Source:** [AI PII Sanitizer](https://developer.konghq.com/plugins/ai-sanitizer/)
- **Visible evidence:** An AI-license badge and enterprise-only notice are shown. The description covers request/response sanitization, placeholder or synthetic replacements and optional restoration. AI Proxy or AI Proxy Advanced must be configured first.
- **Interpretation:** Documented restoration is a differentiator, but licensing and prerequisite plugins constrain a student prototype. The source also points readers to a newer AI Gateway 2.0 policy; version-specific behavior needs checking.

### 02 — Inspect external-service flow

![Kong sanitizer external PII service and request response flow](images/alternatives/ALT-04-02-service-flow.jpg)

- **Source:** [AI PII Sanitizer](https://developer.konghq.com/plugins/ai-sanitizer/)
- **Visible evidence:** The AI PII Anonymizer Service can run in Docker. Input and output application is documented, with response/both modes marked v3.12+. The visible flow intercepts a request, passes it to an external PII service, then forwards the sanitized request using AI Proxy or AI Proxy Advanced.
- **Interpretation:** Deployment and privacy analysis must include that service boundary and the applicable Kong version.

### 03 — Configure on-prem primitives

![Kong on-prem configuration and Konnect entity translation](images/alternatives/ALT-04-03-on-prem.jpg)

- **Source:** [Configure Kong AI Gateway on-prem](https://developer.konghq.com/ai-gateway/configure-on-prem/)
- **Visible evidence:** Konnect uses higher-level AI entities absent from self-hosted Kong. The page describes configuring plugins on Services/Routes or converting an existing entity-model configuration. Both modes run Services, Routes, Plugins and Consumers; on-prem operators produce these primitives themselves.
- **Interpretation:** Self-hosting is documented, but it adds explicit configuration work. This is not proof that every Konnect capability has a self-hosted equivalent.

## Verification and limits

- All seven included JPEGs decode successfully and were visually checked against their captions. Their bytes match the restored source archive; none was generated or edited during this review.
- Pixel inspection found no private identities or secrets. JPEG inspection found no EXIF metadata. Standard JPEG fields and, in three files, color profiles remain.
- All eight unique source pages were accessible when rechecked on 2026-10-03. Public product documentation can change; the original package's capture date applies to every image above.
- ALT-02-02 has a bottom-edge crop limitation. Its caption intentionally limits visible evidence to readable text.
- No effectiveness, false-negative rate, latency, cost, deployment success, or legal/compliance claim was independently tested here.
