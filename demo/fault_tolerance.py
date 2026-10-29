"""QR-01: repeat each request-side middleware failure and count what reaches the provider."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import os
from pathlib import Path
import platform
import sys
import tempfile

import httpx
import yaml

from demo.run import SYNTHETIC_KEY, _free_port, _gateway_command, _server, _write_config

SAFE_STATUSES = {403, 500, 504}
FAULT = {"module": "demo.fault_plugin", "enabled": True, "required": True}
GUARD = {
    "module": "gateway7.plugins.content_policy", "enabled": True, "required": True,
    "settings": {"terms": ["BLOCK-ME-TEST"], "phase": "request", "action": "block"},
}
# Each case: the request-side plugin, the client text, and the safe error it must produce.
CASES = (
    ("raise", {**FAULT, "settings": {"mode": "error"}}, "synthetic failure", 500, "plugin_error"),
    ("deny", GUARD, "BLOCK-ME-TEST synthetic", 403, "policy_denied"),
    ("overrun", {**FAULT, "settings": {"mode": "timeout"}}, "synthetic timeout", 504, "timeout"),
    ("late", {**FAULT, "settings": {"mode": "late"}}, "synthetic late result", 504, "timeout"),
)


def run(runs: int) -> bool:
    repository = Path(__file__).resolve().parents[1]
    baseline = yaml.safe_load((repository / "config" / "demo.yaml").read_text(encoding="utf-8"))
    upstream_port = _free_port()
    upstream_url = f"http://127.0.0.1:{upstream_port}"
    baseline["provider"]["base_url"] = upstream_url
    baseline["limits"]["hook_timeout_seconds"] = 0.05
    env = {name: os.environ[name] for name in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if name in os.environ}
    env.update({
        "FAKE_LLM_API_KEY": SYNTHETIC_KEY,
        "DEMO_PROVIDER_KEY": SYNTHETIC_KEY,
        "PYTHONPATH": str(repository),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    })
    print(f"QR-01 runs={runs} platform={platform.system()} python={platform.python_version()}")
    passed = True
    logs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="gateway7-qr01-") as temporary:
        sandbox = Path(temporary)
        upstream = [
            sys.executable, "-m", "uvicorn", "demo.upstream:app", "--host", "127.0.0.1",
            "--port", str(upstream_port), "--no-access-log", "--log-level", "warning",
        ]
        with _server(upstream, upstream_url, env, sandbox, logs):
            for name, plugin, text, status, code in CASES:
                config = deepcopy(baseline)
                config["plugins"]["failing"] = plugin
                config["middleware"] = ["mask", "failing"]
                path = sandbox / f"{name}.yaml"
                _write_config(path, config)
                port = _free_port()
                url = f"http://127.0.0.1:{port}"
                outcomes: Counter[tuple[int, str]] = Counter()
                with _server(_gateway_command(path, port), url, env, sandbox, logs):
                    with httpx.Client(trust_env=False, timeout=12) as client:
                        before = len(client.get(upstream_url + "/requests").json()["requests"])
                        for _ in range(runs):
                            response = client.post(url + "/chat", json={
                                "messages": [{"role": "user", "content": text}],
                            })
                            error = response.json().get("error") or {}
                            outcomes[(response.status_code, str(error.get("code")))] += 1
                        after = len(client.get(upstream_url + "/requests").json()["requests"])
                forwarded = after - before
                ok = (
                    forwarded == 0
                    and set(outcomes) == {(status, code)}
                    and status in SAFE_STATUSES
                )
                passed = passed and ok
                observed = ", ".join(f"HTTP {s} {c} x{n}" for (s, c), n in sorted(outcomes.items()))
                print(
                    f"{'PASS' if ok else 'FAIL'} {name}: upstream requests={forwarded}; {observed}"
                )
    print(("PASS" if passed else "FAIL") + " QR-01: no failure case reached the provider")
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=50, help="Requests per failure case")
    arguments = parser.parse_args()
    if arguments.runs < 1:
        parser.error("--runs must be at least 1")
    return 0 if run(arguments.runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
