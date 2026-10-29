# Customer demonstration

For a demonstration with an actual OpenAI account, use the [live provider recipe and rehearsal](setup.md#real-providers), including `gateway7 smoke` before the meeting.
The deterministic walkthrough below remains a separate way to inspect exact transformations and failure traces without paid calls.
Only a successful run against the selected real-provider deployment establishes that integration path; it does not itself record a Customer verdict.

The deterministic demonstration shows one running Python service, async middleware plugins and a separate deterministic HTTP upstream.
It includes three distinct middleware types, reverse response order and inspectable failure traces under [DEC-016](decisions.md#dec-016).
It follows [DEC-009](decisions.md#dec-009) and [DEC-011](decisions.md#dec-011); the actual model call in US-01 / AC-05 remains pending.
The [architecture customer view](architecture/README.md#customer-view) is the opening slide, and [setup](setup.md) contains the installation and manual curl commands.

## Interactive pilot and monitoring

Start `uv run --locked gateway7 demo`, or `docker compose -f compose.yaml up --build --detach --wait` for the complete monitoring stack.
Send these public synthetic fixtures through the CLI:

```sh
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
uv run --locked gateway7 chat --message 'Contact synthetic@example.com or +7 999 123-45-67; SECRET-TEST'
uv run --locked gateway7 chat --message 'BLOCK-ME-TEST'
```

The first answer contains `[EMAIL]`, `[PHONE]` and `[removed]`; the second returns a nonzero CLI exit with HTTP 403 and makes no provider call.
A missing/wrong gateway token returns 401; a model outside the client allowlist returns 403 before forwarding.
The [API guide](api.md) demonstrates the same middleware path through the official OpenAI SDK.
With Compose, show `http://127.0.0.1:3000/d/gateway7-overview` after several scrapes and relate HTTP outcomes, provider calls and middleware timings.
`python scripts/smoke_compose.py` verifies these behaviors and the monitoring connections automatically.
This interactive fixture echoes transformed input and retains no conversation history.
The original regression walkthrough below uses a separate synthetic recording fixture to verify the exact upstream boundary.
For an actual model, follow [real provider setup](setup.md#real-providers); do not describe a synthetic run as AC-05 evidence.

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
The matrix was compiled from `main` on 25 October 2026 for the next Customer Review.
"Automated (mock)" means a synthetic fake upstream or HTTP transport in `demo/run.py`, `tests/`, `scripts/smoke_compose.py` or `scripts/smoke_authoring.py`; it never stands for a live provider call or a Customer verdict.
"No exact check found" means the repository has related checks but none with the criterion's exact fixture; the dry-run must produce the observation before the criterion is shown as met.
"Known gap" means the current code or documentation contradicts the criterion, so it cannot be shown as met until the code or the criterion changes.
No story has a recorded Customer verdict: US-03, US-06 and US-09 were closed on GitHub without a verdict comment or `DEC-nnn`.

| Story / criterion | Demonstration and expected observation | Evidence on `main` | Still needed |
| --- | --- | --- | --- |
| [US-01](https://github.com/iteam7/gateway7/issues/30) / AC-01 | `python -m demo.run`: a request without a provider key receives `pong — deterministic upstream` with HTTP 200 | Automated (mock): `demo/run.py` sends `Reply with the word pong`, not the README request | Dry-run of the README `curl` request; Customer verdict |
| US-01 / AC-02 | Same run: the fake upstream accepts the configured synthetic key and rejects wrong or missing keys | Automated (mock): `demo/run.py` | Customer verdict |
| US-01 / AC-03 | Same run: startup without a key exits and names the missing setting | Automated (mock): `demo/run.py` | Customer verdict |
| US-01 / AC-04 | Same run: client responses and captured logs contain no key | Automated (mock): `demo/run.py` | Customer verdict |
| US-01 / AC-05 | [Real provider setup](setup.md#real-providers), then `gateway7 chat --message 'Reply with the word pong'`: HTTP 200 with `pong` | Adapters checked only against synthetic HTTP transports in `tests/test_providers.py` | **Live run with an authorized Claude or Gemini key, then Customer verdict** |
| [US-02](https://github.com/iteam7/gateway7/issues/31) / AC-01 | `python -m demo.run`: the three phone formats arrive upstream as three `[PHONE]` tokens | Automated (mock): `demo/run.py` | Customer verdict; production format policy remains open |
| US-02 / AC-02 | Same run: the first message of a three-message conversation is masked | Automated (mock): `demo/run.py` | Customer verdict |
| US-02 / AC-03 | Same run: `Order ORDER-2026-1001 shipped on 2026-10-08` arrives unchanged | Automated (mock): `demo/run.py` | Customer verdict |
| [US-03](https://github.com/iteam7/gateway7/issues/32) / AC-01 | Same run plus `git status --short`: after restart the message ends with `[checked-by-sample]`; only the plugin file and configuration changed | Automated (mock): `demo/run.py` | Human inspection of the two-path status and Customer verdict |
| US-03 / AC-02 | Same run: a listed missing plugin stops startup and is named | Automated (mock): `demo/run.py` | Customer verdict |
| US-03 / AC-03 | Same run: two instances produce A's marker before B's upstream | Automated (mock): `demo/run.py` | Customer verdict |
| [US-04](https://github.com/iteam7/gateway7/issues/33) / AC-01 | [Interactive pilot](#interactive-pilot-and-monitoring): `BLOCK-ME-TEST` returns HTTP 403 and the provider receives no call | Automated (mock) for HTTP 403 and zero provider calls: `tests/test_reference_middleware.py`, `scripts/smoke_compose.py`; **known gap**: the client error is always `Request denied by policy` and never names the plugin | Code change or Customer decision on the criterion; Customer verdict |
| US-04 / AC-02 | Policy configured with `action: log`: the message arrives unchanged; one log entry names the plugin and action without the text | Related automated (mock): `tests/test_reference_middleware.py` uses a different term; no exact check found | Dry-run with the exact fixture; Customer verdict |
| US-04 / AC-03 | Configuration with `action: explode`: startup exits naming the plugin and `explode` | **Known gap**: startup fails with `Invalid settings for plugin instance <name>` and, by design, never echoes `explode`; `tests/test_reference_middleware.py` checks that text | Code change or Customer decision on the criterion; Customer verdict |
| [US-05](https://github.com/iteam7/gateway7/issues/34) / AC-01 | Upstream answer `The code is SECRET-TEST` reaches the client as `The code is [removed]` | Related automated (mock): `tests/test_reference_middleware.py`, `scripts/smoke_compose.py`; no exact check found | Dry-run with the exact fixture; Customer verdict |
| US-05 / AC-02 | Upstream answer `Nothing to remove` reaches the client unchanged | Related automated (mock): `tests/test_reference_middleware.py`; no exact check found | Dry-run with the exact fixture; Customer verdict |
| [US-06](https://github.com/iteam7/gateway7/issues/35) / AC-01 | `python -m demo.run`: a raising plugin returns an error naming it, with zero upstream calls | Automated (mock) for the error and zero upstream calls: `demo/run.py`; **known gap**: the client error is always `Plugin processing failed`, and the plugin is named only in the log trace | Code change or Customer decision on the criterion; Customer verdict |
| US-06 / AC-02 | Same run: a slow plugin returns a time-limit error with zero upstream calls | Automated (mock) with the demo's own limits; no exact check found for 1 s limit, 3 s plugin and a 2 s bound | Dry-run with the criterion's timings; Customer verdict |
| US-06 / AC-03 | Same run: each failure trace names the plugin and request ID without the message text | Partial: `demo/run.py` prints the trace without asserting it; related checks in `tests/test_core.py` | Dry-run inspection of the log; Customer verdict |
| US-06 / AC-04 | A 0.5 s plugin under a 1 s limit: the request is forwarded and answered with HTTP 200 | No exact check found | Dry-run with the criterion's timings; Customer verdict |
| [US-07](https://github.com/iteam7/gateway7/issues/36) / AC-01 | Client token allowed `model-a`: `model-a` is answered; `model-b` gets HTTP 403 with no upstream request | Automated (mock): `tests/test_access.py` | Customer verdict |
| US-07 / AC-02 | Missing and unregistered tokens each get HTTP 401 with no upstream request | Automated (mock): `tests/test_access.py` | Customer verdict |
| [US-08](https://github.com/iteam7/gateway7/issues/37) / AC-01 | [`gateway7 plugin test`](authoring.md) offline: both fixtures listed with expected and actual text, passed, exit 0 | Automated (mock) for a generated plugin: `tests/test_tooling.py`, `scripts/smoke_authoring.py`; no exact check found for the phone-number plugin | Dry-run with the phone-number plugin; Customer verdict |
| US-08 / AC-02 | A mismatching fixture is marked failed with expected and actual text, nonzero exit | Automated (mock): `tests/test_tooling.py` | Customer verdict |
| [US-09](https://github.com/iteam7/gateway7/issues/38) / AC-01 | Example plugin copied from the instructions: after restart the message ends with `[example-plugin]` | **Known gap**: neither [the authoring guide](authoring.md) nor `examples/` contains a plugin that appends `[example-plugin]` | Add the example to the instructions; Customer verdict |
| US-09 / AC-02 | A copy missing a required entry point stops startup with the error the instructions give | No exact check found | Dry-run; Customer verdict |
| US-09 / AC-03 | A non-author asks Claude Code or Codex for an e-mail-masking plugin; it loads after one restart and `user@example.com` does not reach upstream | None: needs a recorded run by a team member who did not write the instructions | Non-author run; Customer verdict |

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
There is no restoration map, hot loading, streaming, retry/failover, persistent chat storage or billing ledger in this slice.
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
