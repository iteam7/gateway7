# Customer demonstration

The demonstration shows one running Python service, async middleware plugins and a separate deterministic HTTP upstream.
It includes three distinct middleware types, reverse response order and inspectable failure traces under [DEC-016](decisions.md#dec-016).
It follows [DEC-009](decisions.md#dec-009) and [DEC-011](decisions.md#dec-011); the actual model call in US-01 / AC-05 remains pending.
The [architecture customer view](architecture/README.md#customer-view) is the opening slide, and [setup](setup.md) contains the installation and manual curl commands.

## Rehearsal and live demonstration

After `uv sync --locked`, run this from the repository root before the call:

```sh
uv run --locked pytest -q
uv run --locked python -m demo.run
```

Use the same demo command during the call; a nonzero exit is a failed check.
Keep the terminal, `config/demo.yaml`, `examples/sample_plugin.py` and the architecture page visible.
The runner uses disposable files, restarts the gateway for configuration changes and stops its child processes afterwards.

| Time | Show | Expected observation |
| --- | --- | --- |
| 0–2 min | Customer view and `config/demo.yaml` | Core orchestration, policy middleware and provider adapter are separate; one list defines both directions |
| 2–4 min | Start `uv run --locked python -m demo.run` | Real HTTP request gets `pong — deterministic upstream`; fake upstream verifies the configured key while client/log checks find no key |
| 4–6 min | Masking checks and recorder output | Three specified phone strings become `[PHONE]`; earlier history is processed; `Order ORDER-2026-1001 shipped on 2026-10-08` is unchanged |
| 6–9 min | Sample module and its instance configuration | Only the new plugin file and YAML change; after restart the upstream user message ends with `[checked-by-sample]` |
| 9–11 min | Two marker instances and restart checks | A then B appears upstream and B then A returns; changing one list changes both directions |
| 11–13 min | Three middleware types and safe trace | Phone mask, policy guard and sample transformation run together; the response trace unwinds in reverse |
| 13–15 min | Policy denial, request exception, timeout and response failure | The first three produce zero provider calls; a response-side failure produces one provider call and no delivered answer |
| 15–17 min | Checklist below and questions | Distinguish demonstrated behavior, actual-provider evidence still needed, and Customer verdicts still needed |

For an interactive manual installation, follow [Writing a plugin](plugins.md#smallest-installation), restart the manual gateway, send a user message and open the fake upstream `/requests` endpoint.
Use `git status --short --untracked-files=all` to inspect the literal US-03 / AC-01 two-file change constraint in a clean checkout.
The automated runner additionally checks its disposable file changes so normal rehearsal leaves your source unchanged.

## Acceptance checklist

These are implementation checks, not prewritten customer acceptance.
Dated evidence and outstanding submission work are recorded in the repository's `reports/week-03/README.md`.

| Story / criterion | Demonstration or automated evidence | Remaining gate |
| --- | --- | --- |
| [US-01](https://github.com/iteam7/gateway7/issues/30) / AC-01 | README request has no provider key and receives the fake answer over HTTP | Human review and Customer verdict |
| US-01 / AC-02 | Fake upstream rejects wrong/missing keys and accepts the configured synthetic key | Human review and Customer verdict |
| US-01 / AC-03–04 | Missing key prevents readiness; client responses and captured gateway output omit the synthetic key | Human review and Customer verdict |
| US-01 / AC-05 | Claude adapter prepared and checked offline | **Pending actual keyed Claude/Gemini HTTP 200 response containing `pong`** |
| [US-02](https://github.com/iteam7/gateway7/issues/31) / AC-01 | Exact three-format synthetic fixture becomes three `[PHONE]` tokens | Customer verdict; production format policy remains open |
| US-02 / AC-02 | First message of a three-message conversation is masked | Customer verdict |
| US-02 / AC-03 | Order/date fixture reaches the recorder unchanged | Customer verdict |
| [US-03](https://github.com/iteam7/gateway7/issues/32) / AC-01 | File/configuration-only installation, restart and sample marker | Human inspection of exact two-path status and Customer verdict |
| US-03 / AC-02 | Named missing module fails startup, including a disabled declaration | Customer verdict |
| US-03 / AC-03 | Two sample instances preserve configured A-before-B request order | Customer verdict |

## What this prototype establishes

The core nests async middleware in declared order, revalidates boundary values and stops on failures.
The provider sees only the request passed through each middleware's preprocessing.
The response unwinds in reverse: `[mask, alpha, beta]` forwards `ping[A][B]` and returns an answer ending `[B][A]`.
The next example composes three distinct types: phone masking, a synthetic marker guard and request/response transformation.
The demo prints safe request-correlated execution traces, and verifies zero provider calls for request-side denial, exception and timeout.
It separately verifies that response-side failure occurs after one provider call and prevents delivery.
These checks establish extension-contract behavior, not Customer acceptance of a separate response-filtering story.
No test claims a supported maximum plugin count or production throughput.

Modules are trusted code sharing one process and its environment; hiding the key from hook arguments does not sandbox a malicious plugin.
Async timeouts are cooperative and cannot forcibly kill CPU-blocking code or reverse an upstream request already sent.
There is no restoration map, hot loading, streaming, retry/failover, developer authentication, persistent chat storage or billing ledger in this slice.
The recorder is test-only and stores synthetic inputs so the operator can inspect what crossed the provider boundary.

## Questions to settle in the call

- Which step of the module/configuration/restart workflow is missing for the Customer's IT team?
- Which additional phone formats and benign examples should the policy cover?
- Which expected workload should a later capacity test measure, and which secret source should deployment use?
- What real-provider evidence remains before US-01 can be accepted, and which next work has priority?

Python and restart-based installation are already recorded decisions; the call should evaluate behavior rather than repeat those choices.
The meeting script is preserved separately in `reports/week-03/meeting-script.md` as preparation, not as evidence that each planned check was shown.

## Customer feedback follow-up

At the 16 October meeting, the presenter showed one phone-masking path through a mock upstream and walked through YAML configuration and the Python plugin interface.
[DEC-015](decisions.md#dec-015) requests three interacting plugins and a clear authoring/configuration walkthrough for the next usable demonstration.
[DEC-014](decisions.md#dec-014) also requires an explanation of execution, failure diagnosis and the chosen design's trade-offs.
The next demonstration must make the input/output effects and failures inspectable without exposing real messages or credentials.
The transcript does not establish that the complete rehearsal above was performed, and no candidate story received an explicit acceptance or rejection.
Existing automated checks remain separate evidence; US-01 AC-05 and all Customer story verdicts still need to be obtained.
