# Ask an agent to change a plugin

Give the agent a generated plugin folder and an environment with the reviewed Gateway7 wheel already installed.
The folder includes `AGENTS.md`, `CONTRACT.md`, package source, settings, synthetic fixtures and unit tests.
These files and public installed imports are enough for the first change; the agent does not need a Gateway7 core checkout.
Plugins are trusted Python, so review the agent's code before running it.

## Minimal task prompt

Copy this prompt into an agent opened in a generated request-guard project:

```text
Read AGENTS.md and CONTRACT.md. Add a rule blocking SYNTHETIC-BLOCK anywhere
in request text. First add one synthetic chat fixture expecting policy_denied
and zero provider calls, run it and show the failing result. Then change only
the pure transform, keep every original profile case passing, and run the
fixture suite, generated Ruff/strict mypy checks and unit tests. Use the public installed APIs; do not
edit Gateway7 core, weaken expectations, add network calls, or change tool IDs,
function names, provider usage or response/early policy boundaries. Report
actual commands, exit codes, and the positive tested profiles.
```

Add a concrete intended result whenever asking for a broader policy.
For redaction, specify request/response phases, protected-field behavior and examples of unchanged benign text.
Do not give the agent real prompts, production access tokens or provider keys for this task.

## Make a red then green change

Start from an unchanged `--template guard` project and run the following from that folder.
Save this portable Python snippet as `add_case.py` and execute `python add_case.py`:

```python
import json
from pathlib import Path

path = Path("fixtures.json")
suite = json.loads(path.read_text(encoding="utf-8"))
suite["cases"].append(
    {
        "name": "block new synthetic marker",
        "profile": "chat",
        "request": {"messages": [{"role": "user", "content": "SYNTHETIC-BLOCK"}]},
        "provider_response": {"text": "Must not be requested"},
        "expected": {"provider_calls": 0, "error": "policy_denied"},
    }
)
path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
```

```sh
gateway7 plugin inspect . --json
gateway7 plugin test . --json
```

The test exits **1**: the new case makes a provider call because the original guard only recognizes `PRIVATE-TEST`.
Keep this failure as evidence that the fixture exercises the new rule.
In the transform inside `plugin.py`, change:

```python
hits = text.count(settings.term)
```

To:

```python
hits = text.count(settings.term) + text.count("SYNTHETIC-BLOCK")
```

Then run:

```sh
gateway7 plugin test . --json
uv pip install --group dev
ruff format --check .
ruff check .
mypy
python -m unittest discover -s tests -v
gateway7 plugin dev . --port 0
```

Expect **13 passing fixture cases**, clean Ruff/strict mypy checks, **2 passing unit tests**, and all five positive profiles still listed.
Copy the printed client command: ordinary text returns 200; `PRIVATE-TEST` and `SYNTHETIC-BLOCK` return 403.
Ctrl-C stops both local listeners.
The installed-wheel smoke executes this red/green pattern against a fresh generated package and separately checks normal installed serving.
Adding only a denial fixture does not certify any new profile.

## Review the agent's result

Accept a change when its new example failed before implementation, passes afterward and every original case remains meaningful.
The report should identify source/fixture/settings changes, actual exit codes and the per-profile matrix.
Inspect the diff for removed assertions, widened consent, disabled middleware, bypassed response checks or mutable per-request state on shared instances.
Keep provider-call expectations, usage and typed identities explicit.
Inspection reports declarations and hooks; it never proves behavior.

| Request from the agent | Useful response |
| --- | --- |
| “I need the Gateway7 source” for a simple text rule | Point to local `CONTRACT.md`, the helper and generated typed fixtures |
| “Can I mark all profiles supported?” | Require a positive passing fixture for each profile, alongside negative cases |
| “Can I print the request to debug?” | Use a synthetic fixture and its expected/actual report instead |
| “Can I enable early mode for response redaction?” | Retain the explicit refusal; choose request-only behavior only when that matches the policy |
| “Can I install my source editable?” | Permit explicit local iteration, then require a normal wheel check before deployment |

## Final handoff

Build and normally install the plugin wheel using the generated README.
Validate from outside the source directory and review its runtime dependency range before deployment.
Record the plugin/Gateway7 versions, fixture matrix, unit results and the local HTTP outcome.
A green synthetic suite verifies those examples; it does not prove coverage of all real data, full upstream compatibility or a security sandbox.
See the [cookbook](plugin-cookbook.md) for the next policy recipe and the [plugin reference](plugins.md) for lower-level hooks.
