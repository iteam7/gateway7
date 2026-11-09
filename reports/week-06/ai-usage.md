# AI usage — Week 06

## Tools

Codex with the GitHub connector prepared the provider-streaming and OpenCode increment in [task #153](https://github.com/iteam7/gateway7/issues/153).
Codex used separate Formater, TechLead, core-model/middleware, provider-streaming, API and harness-verification agents under the repository's agent workflow.
OpenCode V2.2.2 was the real external harness used for the local synthetic integration check; it did not generate the gateway implementation.

## What the tools were used for

Codex inspected the current Gateway7 and OpenCode protocol sources, prepared typed function-tool messages, collected and validated actual upstream OpenAI-format SSE, retained complete response middleware before downstream SSE, and extended the existing API, provider and policy tests.
The agents also updated the API and plugin documentation, proposed ADR-005, and added FR-013 for the guarded agent exchange.
Formater prepared an isolated checkout from main and ran the repository checks.
TechLead reviewed the integration and its boundaries.

The harness verifier ran OpenCode against a deterministic local OpenAI-format upstream with synthetic credentials and a synthetic local file.
The normal scenario required a function call, local tool execution, a matching tool-result request and a final answer containing the file's control string.
The blocked-argument scenario required a policy denial before any tool execution or final assistant text.
These checks establish those selected scenarios against the scripted upstream; they are not evidence of a live OpenAI account run or general compatibility with every OpenCode feature.

## What was done with the output

The agents retained full-message response checks and explicitly documented buffered downstream delivery, rather than claiming generation-time token delivery.
The review tightened structured policy coverage, tool history and capability checks, terminal stream validation, safe accounting, and native text API regression behavior.
The implementation reuses existing negative test parametrizations and adds positive stream and function-tool checks.
A full-suite-only admission-test failure was traced to a measured 66.61 ms generation-2 garbage collection inside its 30 ms request budget.
The test now collects unrelated setup cycles before scheduling that timed request; its timeout, capacity, cancellation and no-late-forwarding assertions remain unchanged.
The full automated suite passed with 1077 tests and 11 skips, and the local documentation checks passed.
The all-Markdown external link check remained incomplete after the execution network timed out on GitHub; no exclusions were added and no external availability pass was claimed.
No Customer verdict, team decision, live-provider result, release, deployment or acceptance of task criteria was inferred from generated code or a synthetic run.

## Pull request preparation

After the user's explicit request to create a pull request, Codex prepared publication against the updated main branch.
That branch had already published FR-012 for developer usage reporting, so the unpublished guarded-agent draft was assigned FR-013 before its first publication.
The published FR-012, project plan and Week 05 report were preserved byte for byte; both requirements remain in the index and navigation.
No runtime source changed during this documentation integration.

## Verification audit performed on 4 November 2026

### Tool use and scope

OpenCode was used for the read-only code audit, local verification, harness checks and this factual disclosure.
The initial runtime checks below ran on 4 November against commit `090106fa1cfd88cbeceb291975e5de7b645ea301` on branch `153-verify-proxy-stream-harness`; the completed scoped TechLead review is recorded separately.
The disclosure was prepared on 5 November after the session resumed; completed tests and provider requests were not repeated for this continuation.
No implementation changed, and no commit, push or pull request was authorized for this audit.
The earlier implementation results above are historical evidence, not the result of this verification run.

### Local checks and limitations

| Check | Recorded result |
| --- | --- |
| Full pytest suite | 1,076 passed, 11 skipped and 1 failed in 32.79 seconds. |
| Python checks | Ruff formatting and lint, mypy over 28 files, compileall and the demo passed. |
| Installed package | Wheel installation with 21 locked runtime packages, the plugin smoke and authenticated SDK/synthetic-gateway smoke passed. |
| Repository checks | Markdownlint checked 93 files and actionlint passed. |
| Documentation | Strict build and the site check passed for 53 pages and 5,919 link/asset checks. |
| Compose configuration | The standalone `docker-compose` command validated the base configuration and all three live-provider configurations; this is not runtime verification. |

The pytest failure is at `tests/test_proxy_transport.py:351,455-461`: the bound, non-listening macOS socket produced a timeout rather than the expected `TRANSPORT` failure category.
The failure was reproduced in narrow, full-file and isolated runs; no product or test fix was made.
The 11 skipped tests require the unavailable Docker Compose plugin.
Monitoring runtime verification remains incomplete: ports 8000, 9090 and 3000 were already occupied, and no existing stack was disturbed.

The documentation environment used Python 3.12.11 because the documented 3.12.14 was unavailable.
Node 25.9 differed from the required Node 24 and produced a dependency engine mismatch.
The successful documentation checks therefore do not establish verification in the documented toolchain.
Lychee was unavailable, so the external Markdown link check remains unverified.

### Actual harness results

The real OpenCode 2.2.5 binary ran `scripts/smoke_opencode.py` against a synthetic upstream.
Its SHA-256 was `cd03022601e4848a957999a2a7b1c1ccf18b94f9a084a44719f62abaacebe83c`.
The allowed scenario passed with two streamed provider requests, one `read` tool execution and final marker `GATEWAY7_AGENT_OK`.
The denied scenario passed with one streamed provider request, zero tool executions, one client error and one policy denial.
These results establish the selected synthetic tool round trip and policy case, not live OpenAI generation or general harness compatibility.
Upstream SSE is collected and checked before downstream SSE is delivered; the client does not receive generation-time tokens.

Codex 0.153.4 was also tested as a client in an isolated, ephemeral, read-only custom-provider session.
It requested `/v1/responses`, received HTTP 404 and made zero provider calls.
The repository does not currently support that Responses route; this client configuration is not compatible with the implemented Chat Completions route.

### Completed scoped TechLead review

The completed scoped TechLead review returned `CHANGES REQUIRED` and confirmed a P2 defect in handling valid OpenAI truncation responses with `finish_reason=length`.
`gateway7/providers.py:428-433` rejects a missing tool call for required or named `tool_choice` even when the response ended because of the length limit.
`gateway7/providers.py:177-180` also rejects empty text with that finish reason.
These checks turn valid truncated upstream responses into gateway HTTP 502, despite the preserved-truncation contract in `docs/api.md:137-140` and the existing length exception in `gateway7/pipeline.py:120-128`.

The review confirmed this with a bounded, network-free ASGI reproduction using the production `HTTPProvider` and `httpx.MockTransport`, covering JSON and SSE upstream responses.
An upstream HTTP 200 response with text `partial` and finish reason `length` returned gateway HTTP 200 with automatic tool choice, but HTTP 502 with required or named tool choice; empty-text length responses also returned HTTP 502.
Each case made exactly one synthetic upstream request.

The proposed follow-up is to preserve length-limited responses without tool calls, including empty text, while continuing to reject incomplete or invalid tool arguments, and add JSON and SSE regression tests.
No implementation or test fix was authorized or made in this audit.
The bounded review found no additional confirmed defects in its other examined areas; it is not general release approval.

### Live provider diagnostics and remaining blockers

The initial native `/chat` request with `gpt-4.1-mini` returned gateway HTTP 502 with safe failure category `authentication` and no reported usage.
Subsequent non-billable `GET /v1/models` diagnostics against the official OpenAI endpoint returned HTTP 403 with code `unsupported_country_region_territory`, both directly and through the built-in authenticated local CONNECT proxy.
The proxy diagnostic kept TLS verification enabled, recorded one CONNECT and zero proxy failures, and made no billable chat attempt.
This verifies the tested local CONNECT route, not access through an external proxy or successful model generation.
The user subsequently accepted continuing this audit without an external proxy, so an external proxy is not a closing requirement and no proxy file path is awaited.
Key and account validity, live generation, live SSE and a live-model OpenCode tool round trip remain unverified; the results do not establish that the key is invalid.

The user-authorized provider credential was used only in process memory.
This disclosure includes no credentials, credential-file paths, private names, private artifact paths or raw provider error bodies.
The audit retained the failures and environment limitations rather than treating partial checks as an overall pass.
The scoped TechLead review is complete, and Formater POST is finalized as `CHANGES REQUIRED`, not product approval: the confirmed truncation defect, pytest failure and recorded verification gaps remain unresolved.
No Customer acceptance or team assessment is inferred from these results.

## Team assessment

TODO: the team records which generated output it accepted, changed or rejected and why after its own review.

## Direct live recheck performed on 5 November 2026

OpenCode coordinated the user-authorized renewed direct check against the unchanged commit recorded above, using temporary verification scripts outside the checkout.
The real `gpt-4.1-mini` model was reached at the official OpenAI HTTPS endpoint with TLS verification, `trust_env=False` and the `config/openai.yaml` settings, without a configured transport extension or proxy.
The provider credential remained in process memory; no credential, private path, request identifier or raw request/response body is included here.
This run used all nine authorized provider attempts, with no automatic retries; no further provider calls were made for this disclosure.

### Verified live scenarios

| Scenario | Recorded result |
| --- | --- |
| Native `/chat` | HTTP 200, exact control-marker match, 16 input and 7 output tokens; one provider attempt. |
| OpenAI SDK 3.37.0 JSON | HTTP 200, exact control-marker match, 16 input and 7 output tokens; one provider attempt. |
| Text SSE | HTTP 200 with `text/event-stream`, five downstream events, `[DONE]`, usage and finish reason `stop`; 61 actual upstream fragments, 22 input and 88 output tokens; one provider attempt. |
| Real OpenCode 2.2.5 | Exit 0, exactly one completed `read` of an isolated synthetic fixture, its actual tool result in the second provider request, exact final control-marker match and zero errors; two streamed provider attempts, with input/output usage of 624/16 and 669/8 tokens. |

The harness used a real model, not a scripted upstream; its two provider steps stayed within the three-step and 1024-output-token-per-step limits.
For the text SSE check, the first client event arrived after approximately 1214 ms and all downstream events spanned 0.06 ms, entirely after provider completion.
This confirms actual upstream streaming and buffered, checked downstream SSE, not generation-time client token delivery.
These successes supersede the earlier unverified direct live-generation and live-harness results; the November 4 regional HTTP 403 remains historical evidence, not a current network blocker.
No external proxy was required or tested in this renewed run; the earlier local CONNECT result establishes only its tested route's reachability.

### Confirmed named-tool compatibility failure

The other four provider attempts were explicit forced-named-tool diagnostics and each returned gateway HTTP 502 with safe category `invalid_response`.
The final JSON and SSE diagnostics, provider attempts eight and nine, isolated a new confirmed P2 compatibility defect at `gateway7/providers.py:182`.
Each actual upstream response ended with `finish_reason=stop` and contained one structurally valid tool call matching the advertised named function and expected synthetic arguments, but the assembled response was rejected there.
For the SSE case, parser finalization succeeded: `accepted=True`, `invalid=False`, `done=True`; rejection occurred during assembled-response validation rather than SSE parsing.
The observed live-provider responses therefore fail despite the successful automatic-tool OpenCode round trip.
Follow-up is to reconcile finish-reason validation with these valid tool-call responses and add JSON/SSE regression coverage without weakening named-choice or argument validation.
No implementation or test fix was authorized or made.

The earlier truncation P2 and macOS proxy-test failure remain unresolved.
The November 4 broad QA results, toolchain/Compose/monitoring/Lychee limitations and Codex Responses-route HTTP 404 were not rerun in this bounded live recheck and are not newly verified results.
The final scoped TechLead review of this renewed run was not yet available when this disclosure was prepared; no review approval is inferred from the live evidence.
Formater POST remains `CHANGES REQUIRED` because of the confirmed compatibility defects and unresolved test/verification gaps, not because direct live generation or OpenCode connectivity is still unverified.
The team's assessment above remains `TODO`; no acceptance, release or publication is inferred.

## Read-only remediation planning on 5 November 2026

OpenCode was used to prepare a prioritized remediation proposal from the completed audit and existing source, with proposed regression coverage and acceptance criteria.
The proposal separates named-tool/truncation fixes and deterministic proxy tests from the offline nullable-tool-delta observation, reproducible native V2 harness checks and outstanding verification gates.
Real-time downstream streaming requires a safe streaming-policy design; Responses/Codex support remains a scope choice only if that client is targeted.
No implementation, product tests or provider requests were performed for this planning task; the completed live-audit budget remains closed at nine of nine attempts.
The list is a proposal, not an adopted architecture decision, implemented fix or product-readiness approval.
Team assessment of this planning output: `TODO`.
