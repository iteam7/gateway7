# Gateway7 architecture

**Status:** Python prototype implemented for review, 2026-10-15; deterministic checks do not constitute customer acceptance or the complete MUP.

Gateway7 runs as one service with a small orchestration core, company-authored plugins and interchangeable provider adapters.
The core controls execution; plugins implement company policy; adapters handle provider protocols.
This gives [US-03](https://github.com/iteam7/gateway7/issues/32) a concrete extension boundary while keeping the first [US-01](https://github.com/iteam7/gateway7/issues/30) integration small.

## Basis and scope

The [product vision](../product-vision.md) and existing decisions are the source constraints:

- [DEC-009](../decisions.md#dec-009): demonstrate the plugin interface, message flow and integration workflow, with phone masking as one example.
- [DEC-010](../decisions.md#dec-010): installing a plugin may require a restart.
- [DEC-011](../decisions.md#dec-011) and [CON-01](../product-vision.md#con-01): use at most one provider initially; a deterministic upstream is allowed for the first plugin demonstration.
- [DEC-012](../decisions.md#dec-012): US-01, US-02 and US-03 are the approved candidate to build, not accepted implementations.
- [CON-04](../product-vision.md#con-04): keep the provider key in server configuration.
- [DEC-013](../decisions.md#dec-013): use Python for the first implementation.

The component split, contracts and failure semantics below describe the runnable prototype and its explicit limits.
They support [VP-01](../research/value-proposition.md#vp-01-predictable-local-preflight-for-small-teams) and [VP-02](../research/value-proposition.md#vp-02-testable-domain-filter-extensions); they do not establish the narrower competitive-gap hypotheses as facts.
The initial HTTP demonstration is repeatable through [setup](../setup.md) and the [customer demo](../demo.md).
No story's acceptance criteria are changed by implementing it.

## Components and dependencies

```mermaid
flowchart TB
    caller["Caller application"] --> api
    subgraph gateway["Gateway7: one service process"]
        api["HTTP API"] --> core["Request core"]
        core --> runner["Plugin runner"]
        runner --> plugins["Company plugins"]
        core --> adapter["Provider adapter"]
        startup["Configuration and startup"] -.-> runner
        startup -.-> adapter
    end
    adapter --> provider["Selected upstream"]
    secrets["Server secret source"] -.-> adapter
```

Solid arrows show calls; dotted arrows show startup configuration.
The lifecycle below shows replies and early exits.

| Component | Owns | Boundary |
| --- | --- | --- |
| HTTP API | Validate the supported chat input, create request context, serialize results and safe errors | No provider protocol or company policy logic |
| Request core | Request hooks, one upstream call, response hooks and termination | Depends on runner and adapter interfaces, not concrete plugins or provider SDKs |
| Plugin runner | Ordered invocation, result validation, error conversion and deadline checks | Does not detect phone numbers or choose company policy |
| Company plugins | Mask, allow or deny supported content | Depend on the plugin contract, not HTTP handlers or concrete adapters |
| Provider adapter | Translate normalized data, attach the server key, call upstream and normalize its response/errors | Receives only the request after request hooks; never returns credentials to callers |
| Configuration and startup | Load installed modules, validate settings, construct the runner and selected adapter | The composition point is allowed to know concrete implementations |

Contract types belong to `gateway7/models.py` and `gateway7/plugin_api.py`.
Adding a provider changes its adapter and configuration; adding a company plugin changes its module and configuration.
The first release needs neither a database nor a separate worker service to perform this flow.
Compared with separate plugin services, one process reduces deployment and protocol work but shares failures and resources.
Compared with hard-coded masking in the core, the plugin boundary lets the company replace its policy without a fork ([US-02](https://github.com/iteam7/gateway7/issues/31), US-03).

## Customer view

Gateway input, plugins and output are stages of one service; the request goes to the provider and the response returns to the same client.

```mermaid
flowchart TB
    requestClient["Client"] --> gatewayInput["Gateway input"]
    gatewayInput --> requestPlugins["Request plugins"]
    requestPlugins --> provider["LLM provider"]
    provider --> responsePlugins["Response plugins"]
    responsePlugins --> gatewayOutput["Gateway output"]
    gatewayOutput --> responseClient["Client"]
```

## Request lifecycle

This is the end-to-end path for one non-streaming chat request after startup has passed validation.
The two hook loops use separate configured lists; an empty list proceeds directly to the next stage.

```mermaid
flowchart TB
    client["Client HTTP request"] --> input{"1. Valid format and size?"}
    input -->|No| invalid["Safe input error"]
    input -->|Yes| context["2. Request context and deadline"]
    context --> requestNext{"3. Request hook left?"}
    requestNext -->|Yes| requestHook["Run and validate on_request"]
    requestHook -->|Continue: unchanged or modified| requestNext
    requestHook -->|Deny| denied["Safe policy error"]
    requestHook -->|Exception, invalid result or timeout| failed["Safe technical error"]
    requestNext -->|No| active{"4. Still active?"}
    active -->|Yes| adapt["Adapt request and add server key"]
    adapt --> upstream["Call configured upstream once"]
    adapt -->|Adaptation error| failed
    upstream -->|Error or timeout| upstreamError["Normalize upstream error"]
    upstreamError --> failed
    upstream -->|Success| normalize["5. Normalize response, capture usage"]
    normalize -->|Invalid response| failed
    normalize --> responseNext{"6. Response hook left?"}
    responseNext -->|Yes| responseHook["Run and validate on_response"]
    responseHook -->|Continue: unchanged or modified| responseNext
    responseHook -->|Deny| denied
    responseHook -->|Exception, invalid result or timeout| failed
    responseNext -->|No| encode["7. Encode response or safe error"]
    invalid --> encode
    denied --> encode
    failed --> encode
    context -.-> cancellation["Cancellation or deadline at any stage"]
    active -->|No| cancellation
    cancellation --> stop["Signal cooperative stop, discard late results"]
    stop --> encode
    encode --> send["Send to client if connected"]
    send --> finish["8. Safe outcome and scoped cleanup"]
```

1. **Validate input.** The HTTP API checks the supported text-chat format, message roles, generation options and configured input-size limit. Invalid or unsupported content returns a safe input error before any plugin or provider call.
2. **Create context.** The API creates a core-owned request ID and monotonic deadline; the runner supplies isolated state for each configured plugin instance. Async task cancellation and deadline checkpoints govern execution. A request identifier also accompanies input errors; rejected input needs no plugin state.
3. **Run request hooks.** For each configured position, the runner invokes `on_request` and validates its result against the contract. `Continue` passes the unchanged or modified payload to the next hook; each hook sees the preceding hook's output. `Deny` stops with a policy error. Exceptions, invalid results and timeouts stop with a technical error. These exits make **no upstream call**; the core never forwards by bypassing a failed hook.
4. **Forward once.** Immediately before forwarding, the core rechecks cancellation and deadline. The selected adapter translates only the fully processed request, inserts the server-configured key and calls one upstream. The transport demonstration uses the HTTP fake upstream; the Claude adapter is available for a separately configured real-provider check. No retries or failover occur. Adaptation failures and normalized upstream errors or timeouts take the technical-error exit.
5. **Capture the upstream outcome.** On success, the adapter produces a normalized response. A malformed or unsupported upstream response that cannot be normalized takes the technical-error exit without running response hooks. The core snapshots validated provider-reported usage before response hooks, and preserves it in the final successful response; absent or invalid usage remains unknown. Plugin changes to a response's usage field do not overwrite that snapshot. On denial or cancellation there is no durable usage record, and unknown usage does not mean zero. This is per-request metadata, not a usage ledger or billing feature ([BND-03](../product-vision.md#bnd-03)).
6. **Run response hooks.** The runner invokes and validates `on_response` in the separately configured response order. `Continue`, `Deny` and technical errors have the same stop/continue semantics as request hooks. A denial here prevents delivery of the completion **after the upstream call**; it cannot undo provider work or usage. This chain runs only for a successful upstream result. The sample marker exercises the hook interface; it is not a production output policy or acceptance of a separate response-filtering story.
7. **Return the result.** The API encodes the final allowed response or a safe input, policy or technical error with the request identifier, and sends it only while the client connection is available. Raw upstream bodies, exception messages and credentials are excluded from error responses. The [setup page](../setup.md#supported-http-contract) describes the text-chat wire contract.
8. **Finalize every exit.** Record the request ID, outcome, safe reason/component IDs and durations under the observation rules below, then release request-owned resources and discard plugin state when in-flight work has unwound. Finalization also runs on input rejection and client disconnect; it does not require successful delivery. It creates neither restoration storage nor a guarantee of secure memory erasure.

**Cancellation and deadlines apply throughout the path.** The dotted edge represents lifecycle signals, not another content-processing stage.
The core checks before each stage and after each hook returns, stops subsequent content stages, signals cooperative work to stop and ignores late results.
A connected caller may receive a safe timeout/cancellation error; a disconnected caller cannot receive one.
In-process code cannot be forcibly stopped: a blocking or uncooperative plugin can delay responsiveness and cleanup until it returns.
Cancelling an upstream call cannot prove that the provider stopped or reverse usage already incurred.
The diagram's terminal path describes controlled completion, not isolation from arbitrary plugin code.

## Data and plugin contract

These semantics are implemented with strict Pydantic models and a small Python plugin API.
The initial operation is one non-streaming text chat completion.
Reject unsupported content, such as attachments or tool payloads, rather than forwarding unexamined fields.

| Contract | Contents and rules |
| --- | --- |
| Chat request | An ordered conversation of messages with a supported role and plain-text content; a small validated set of generation options. All supported messages are visible to request hooks, including earlier history. Provider selection comes from server configuration. |
| Chat response | Assistant text and normalized completion metadata. Preserve provider-reported usage if present; absent usage is unknown, not zero. No provider credentials or raw upstream error body. |
| Plugin context | Core-owned request ID and deadline; a separate temporary `state` dictionary for each configured plugin instance and request. Identity can be added when authentication is implemented. |
| Plugin result | `Continue(payload)` or `Deny(code="policy_denied")`. Unchanged payload means allow; modified payload includes masking. Exceptions, invalid results and timeouts are technical errors, not policy denials. Client error text is core-owned. |

A module exports `PLUGIN`, declaring a stable type ID, contract version 1, strict settings model and a factory.
The YAML map key identifies a configured instance; different instances can use the same module with different settings.
The two hooks are `on_request(request, context)` and `on_response(response, context)`.
A plugin implements only the hooks it needs; naming a missing hook for an enabled instance in a configured chain is a startup error.
The runner validates returned payloads before continuing.
The public contract provides no core-forwarding callback or provider-key field.

**Ordering:** configuration contains separate ordered request and response lists of instance names.
Response order is not implicitly reversed from request order.
For example, request list A then B yields A's marker before B's; a response list B then A is independently configured.
Each referenced hook runs once at its listed position; no retries or parallel hooks within one request.
Reject duplicate IDs within one chain and unknown references at startup.
Ordering is part of policy: a later trusted plugin can modify earlier output, so the configured full chain must be checked on fixtures.

**State and concurrency:** different requests may run concurrently and share loaded plugin instances.
Instances keep immutable configuration or concurrency-safe service resources, never a shared mutable current request.
Per-request counters and similar hook state live in that request's plugin namespace and are discarded at completion.
Do not create restoration maps or persist original unmasked text; [BND-02](../product-vision.md#bnd-02) excludes restoration storage.
The contract does not promise secure erasure of transient process memory.

## Loading, readiness and errors

At startup, load YAML with `safe_load`, validate configuration, import declared trusted modules, check contract compatibility and settings, and construct both chains and the selected adapter.
Validate required credentials, including the test key in the fake-upstream configuration.
Only report ready and accept chat requests after all checks succeed.
A missing plugin, invalid chain, failed initialization or missing key aborts startup with a safe message naming the relevant plugin or setting.
Never silently skip a missing declared module or print configuration values.
Even disabled declarations must have an importable module and valid descriptor/settings; explicitly disabled optional instances are then omitted from effective execution.

The operator installs a Python module, lists its instance/module/settings and hook position, then restarts Gateway7.
No request may select arbitrary modules or supply an upstream URL.
The [one-file sample installation](../plugins.md#smallest-installation) satisfies the extension mechanism without a core edit or package rebuild when running from the checkout.
Hot loading and an untrusted plugin marketplace remain outside scope ([DEC-010](../decisions.md#dec-010), [BND-04](../product-vision.md#bnd-04)).

| Outcome | Behavior |
| --- | --- |
| Continue | Pass the processed payload to the next hook or next core stage |
| Policy denial | Stop the chain and return a stable policy error with safe metadata |
| Plugin exception, invalid result or timeout | Stop the request; every active hook fails closed, including optional instances. `required: true` separately prevents disabling or omitting a mandatory filter from an applicable chain. |
| Upstream failure | Return a normalized technical error; no response hooks, automatic retry or failover |
| Cancellation or expired deadline | Stop further stages, signal cooperative plugin/upstream work to stop, and discard late results |

The core checks cancellation/deadline before each stage and after a hook returns, including immediately before forwarding.
An in-process timeout cannot forcibly terminate arbitrary blocking or uncooperative plugin code, or guarantee that the API remains responsive while it blocks.
Nor does cancelling a provider call prove that the provider stopped processing it.
Trusted plugin authors must use cooperative cancellation and bounded work; stronger isolation would require a separate execution boundary.
The default total deadline is 10 seconds, each hook has 2 seconds, and the request-body cap is 65,536 bytes; YAML may set stricter or larger validated values.

## Provider and observation boundaries

The adapter exposes one completion operation over normalized request/response types.
Startup selects a single configured implementation: a deterministic fake-upstream adapter for fixtures, or the Claude Messages adapter for a separately authorized provider call.
The demo uses an HTTP fake upstream so request contents and test-key propagation can actually be observed.
A static in-memory response is useful for a hook demo but cannot establish those transport criteria.

Credentials go from a server secret source to the adapter; callers and ordinary plugin inputs do not receive them.
This interface boundary is **not a sandbox**: code installed in the same process can access process memory, environment, files or the network.
The operator must trust and review installed plugins; the design does not contain malicious plugin code.
Secret-manager integration remains open; the existing constraint permits server configuration such as an uncommitted `.env`.

Record request ID, outcome, safe reason code, component/plugin ID and durations.
Default logs and telemetry exclude prompts, responses, authorization headers, keys, plugin state and raw exception or upstream bodies.
Use sanitized error codes rather than logging arbitrary plugin exception text.
Keep metric labels bounded; request IDs belong in logs, not metric labels.
The isolated fake upstream may capture synthetic fixtures for verification, never production conversations.
Optional usage metadata is not a usage ledger or billing feature ([BND-03](../product-vision.md#bnd-03)).

## Traceability and first implementation slice

| Source | Implemented mechanism | Acceptance evidence |
| --- | --- | --- |
| [US-01](https://github.com/iteam7/gateway7/issues/30), AC-01–04; CON-04 | One configured adapter with a server-held key | Repeatable fake HTTP answer/key/startup/log checks; human review and Customer verdict remain |
| US-01, AC-05; DEC-011 | Claude Messages adapter and separate config | Actual keyed `pong` call remains pending; offline adapter tests do not pass AC-05 |
| [US-02](https://github.com/iteam7/gateway7/issues/31), AC-01–03; VP-01 | Phone masking before the adapter, over the conversation history | Exact fixture, history and order/date checks; Customer verdict remains |
| [US-03](https://github.com/iteam7/gateway7/issues/32), AC-01–03; VP-02; DEC-009–010 | Configured Python modules, startup validation and explicit order | File/configuration-only sample installation, missing module and A/B order checks; Customer verdict remains |
| DEC-012 | Keep the approved three-story candidate traceable | Implementation and customer acceptance against each story's AC; no story is completed by this document |

The runnable slice consists of the HTTP API, core, plugin runner, phone plugin, sample marker plugin and HTTP fake upstream.
Automated tests additionally exercise fail-closed errors, invalid results, request-state isolation and safe errors.
Run it with the [setup instructions](../setup.md); the actual provider check and Customer story verdicts are still separate gates.

Response hooks and the sample response marker avoid coupling the core to request-only policy, but US-03 covers request plugins.
No production response-filtering policy or separate response-story acceptance is claimed.
Authentication belongs before content handling, future routing before adapter dispatch, and durable usage accounting at the outcome boundary, including response denials and failed calls with unknown usage.
Those are extension points, not promises in this first slice.
Streaming, automatic retries/failover, persistent conversations, billing and user-supplied provider keys are not introduced by this implementation.

## Review questions and Week 2 follow-up

The architecture and runnable technical prototype prepare the next customer presentation.
Presentation and customer evaluation remain pending evidence.

Python and module packaging are settled for this implementation by DEC-013; the schema, limits and Claude integration path are now concrete.
Review the running hook/loading/error contract, confirm required phone formats and determine the deployment secret source.
The deterministic-demo versus complete-candidate distinction follows DEC-011 and the unchanged US-01 criteria.
The plugin capacity question remains open: two plugins are a demonstration, not a capacity ceiling.
Measure concurrent requests, plugin work and latency before stating a supported limit.
