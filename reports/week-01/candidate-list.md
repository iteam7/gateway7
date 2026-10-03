# Candidate List

**Original research problem space (2026-09-30):** Small application teams need to send text conversations to different LLM providers while applying inspectable, locally controlled rules that reduce accidental disclosure of sensitive information, without reimplementing those rules in every application.

**Search date:** 2026-09-30.
**Method:** desk research of official documentation and project repositories only.
No product was installed, tested or benchmarked, and no customer was interviewed for this list.

The October 2 kickoff subsequently broadened the direction to a corporate plugin host. This dated list preserves the privacy-focused search that actually happened; see the [current problem space and evaluation limits](../../docs/research/alternatives.md). Rejected managed services are not automatically unsuitable for that broader direction.

## Search trace

Queries used for discovery:

- "LiteLLM Presidio PII masking"
- "Portkey guardrails PII self hosted"
- "Kong AI PII Sanitizer"
- "Azure API Management LLM content safety"
- "Amazon Bedrock guardrails sensitive information"
- "LLM Guard anonymize"
- "Cloudflare AI Gateway data loss prevention"
- "NVIDIA NeMo Guardrails sensitive data"
- "Apache APISIX AI proxy"

The Envoy AI Gateway documentation was opened directly; it now redirects to Agent Router.
Third-party search results served only to find candidates; every source kept below is an official page or repository.

## Selection rules

A candidate was selected for detailed analysis when it handles the same workflow (sensitive text on its way to an LLM provider) and fills a category the shortlist did not yet cover:

1. a direct multi-provider gateway with built-in redaction;
2. an application-level substitute (library instead of gateway);
3. a self-hosted open-source gateway with local filtering;
4. an enterprise API gateway with a PII plugin.

At most four candidates go to [alternatives.md](../../docs/research/alternatives.md), so that each gets two screenshots and full observations.
The selection rules were refined during this search, not fixed before it; the team reviews them before any hands-on evaluation.

## Candidates

| # | Candidate | Official source | Why it might be relevant | Decision |
| --- | --- | --- | --- | --- |
| 1 | Portkey AI Gateway | [Gateway repository](https://github.com/Portkey-AI/gateway) | Multi-provider gateway with documented guardrails and PII redaction | Selected as ALT-01 (category 1) |
| 2 | Presidio + application middleware | [Project docs](https://presidio.dataprivacystack.org/) | Local detection and anonymization modules an application can call before its provider SDK | Selected as ALT-02 (category 2); compared as a substitute, not as a gateway |
| 3 | LiteLLM Proxy + Presidio | [Presidio integration](https://docs.litellm.ai/docs/proxy/guardrails/pii_masking_v2) | Self-hosted multi-provider proxy with a documented local Presidio guardrail | Selected as ALT-03 (category 3) |
| 4 | Kong AI Gateway on-prem + AI PII Sanitizer | [Sanitizer plugin](https://developer.konghq.com/plugins/ai-sanitizer/) | Enterprise API gateway with a configurable PII sanitization plugin | Selected as ALT-04 (category 4) |
| 5 | Agent Router (formerly Envoy AI Gateway) | [Overview](https://theagentrouter.ai/docs/) | Open-source Envoy-based routing and policy layer for AI traffic | Rejected: the overview documents access control and rate limiting but no PII filtering; category 3 is already covered by LiteLLM, which documents a ready Presidio path |
| 6 | Azure API Management | [Product page](https://azure.microsoft.com/en-us/products/api-management) | Managed gateway with AI governance and content-safety integration | Rejected: tied to an Azure estate; the customer's cloud is unknown. Revisit if the customer runs on Azure |
| 7 | Amazon Bedrock Guardrails | [Sensitive-information filters](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html) | Managed block/mask filters with custom regex | Rejected: managed cloud service, so text leaves the team's boundary, which conflicts with "locally controlled" in the problem space. Revisit if managed services are acceptable |
| 8 | LLM Guard | [Quickstart](https://protectai.github.io/llm-guard/get_started/quickstart/) | Application-level input/output scanners, including anonymization | Rejected: same category as Presidio (category 2); one library is enough for the comparison |
| 9 | NVIDIA NeMo Guardrails | [Guardrail catalog](https://docs.nvidia.com/nemo/guardrails/latest/configure-guardrails/guardrail-catalog) | Guardrail toolkit whose catalog includes PII detection and masking rails | Rejected: PII is one of nine catalog categories (with jailbreak, topic control, fact-checking and others); this search focuses on sensitive-text routing |
| 10 | Cloudflare AI Gateway DLP | [DLP documentation](https://developers.cloudflare.com/ai-gateway/features/dlp/) | Gateway-level sensitive-data checks | Rejected: managed Cloudflare service, which conflicts with local control; no sign the customer uses Cloudflare |
| 11 | Apache APISIX AI Gateway | [AI gateway overview](https://apisix.apache.org/ai-gateway/) | Open-source API gateway with multi-provider LLM proxying and prompt allow/deny plugins | Rejected: the overview lists no local PII redaction plugin; categories 3 and 4 are already covered by LiteLLM and Kong |

Rejected does not mean worse: the cut balances category coverage against research effort, it is not a ranking.
Rejected candidates stay here so a later week can reuse them.
