"""QR-03: credentials and message text stay out of logs, metrics and error bodies."""

from copy import deepcopy
import os
from pathlib import Path
import sys

import httpx
import yaml

from demo.run import _free_port, _gateway_command, _server, _write_config

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_KEY = "gateway7-synthetic-qr03-provider-key"
TOKENS = {
    "QR03_ALPHA_TOKEN": "gateway7-synthetic-qr03-client-alpha",
    "QR03_BETA_TOKEN": "gateway7-synthetic-qr03-client-beta",
}
ALPHA, BETA = TOKENS.values()
WRONG_TOKEN = "gateway7-synthetic-qr03-wrong-token"


def test_allowed_denied_and_failing_requests_expose_no_secret_or_message(tmp_path):
    reference = yaml.safe_load((ROOT / "config" / "reference.yaml").read_text(encoding="utf-8"))
    upstream_port = _free_port()
    upstream_url = f"http://127.0.0.1:{upstream_port}"
    reference["provider"]["base_url"] = upstream_url
    reference["auth"] = {"enabled": True, "clients": {
        "alpha": {"token_env": "QR03_ALPHA_TOKEN", "models": ["fake"]},
        "beta": {"token_env": "QR03_BETA_TOKEN", "models": ["other-model"]},
    }}
    faulty = deepcopy(reference)
    faulty["plugins"]["fault"] = {
        "module": "demo.fault_plugin", "required": True,
        "settings": {"mode": "error", "phase": "request"},
    }
    faulty["middleware"] = ["fault", *reference["middleware"]]
    late_fault = deepcopy(faulty)
    late_fault["plugins"]["fault"]["settings"]["phase"] = "response"
    unreachable = deepcopy(reference)
    unreachable["provider"]["base_url"] = f"http://127.0.0.1:{_free_port()}"

    # Only synthetic values and the interpreter's essentials reach the processes.
    env = {name: os.environ[name] for name in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if name in os.environ}
    env.update(TOKENS)
    env.update({
        "FAKE_LLM_API_KEY": PROVIDER_KEY,
        "DEMO_PROVIDER_KEY": PROVIDER_KEY,
        "PYTHONPATH": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    })
    logs: list[str] = []
    metrics: list[str] = []
    errors: list[str] = []
    messages: list[str] = []
    statuses: list[int] = []

    def chat(client, url, *, token=None, path="/chat", model=None, text=None, body=None):
        if body is None:
            text = text or ""
            message = f"qr03-synthetic-message-{len(messages)}"
            messages.append(message)
            body = {"messages": [{"role": "user", "content": f"{text}{message}"}]}
            if model is not None:
                body["model"] = model
        headers = {} if token is None else {"Authorization": "Bearer " + token}
        response = client.post(url + path, json=body, headers=headers)
        statuses.append(response.status_code)
        if response.status_code >= 400:
            errors.append(response.text)
        return response.status_code

    def gateway(config, name, exercise):
        path = tmp_path / f"{name}.yaml"
        _write_config(path, config)
        port = _free_port()
        url = f"http://127.0.0.1:{port}"
        with _server(_gateway_command(path, port), url, env, tmp_path, logs):
            with httpx.Client(trust_env=False, timeout=15) as client:
                exercise(client, url)
                metrics.append(client.get(url + "/metrics").text)

    def allowed_and_denied(client, url):
        assert chat(client, url, token=ALPHA) == 200
        assert chat(client, url, token=ALPHA, path="/v1/chat/completions", model="fake") == 200
        assert chat(client, url) == 401
        assert chat(client, url, token=WRONG_TOKEN) == 401
        assert chat(client, url, token=WRONG_TOKEN, path="/v1/chat/completions", model="fake") == 401
        assert chat(client, url, token=ALPHA, path="/v1/chat/completions", model="other-model") == 403
        assert chat(client, url, token=BETA) == 403
        assert chat(client, url, token=ALPHA, text="BLOCK-ME-TEST ") == 403
        message = f"qr03-synthetic-message-{len(messages)}"
        messages.append(message)
        invalid = {"messages": [{"role": "tool", "content": message}]}
        assert chat(client, url, token=ALPHA, body=invalid) == 422
        message = f"qr03-synthetic-message-{len(messages)}"
        messages.append(message)
        oversized = {"messages": [{"role": "user", "content": message + "x" * 70_000}]}
        assert chat(client, url, token=ALPHA, body=oversized) == 413

    upstream = [
        sys.executable, "-m", "uvicorn", "demo.upstream:app", "--host", "127.0.0.1",
        "--port", str(upstream_port), "--no-access-log", "--log-level", "warning",
    ]
    with _server(upstream, upstream_url, env, tmp_path, logs):
        gateway(reference, "reference", allowed_and_denied)
        gateway(faulty, "faulty", lambda client, url: chat(client, url, token=ALPHA))
        gateway(late_fault, "late-fault", lambda client, url: chat(client, url, token=ALPHA))
        gateway(unreachable, "unreachable", lambda client, url: chat(client, url, token=ALPHA))

    assert statuses[-3:] == [500, 500, 502]
    assert len(errors) == len(statuses) - 2 and len(metrics) == 4
    assert all("gateway7_http_requests_total" in output for output in metrics)
    assert sum("outcome=http_" in output for output in logs) == 4
    secrets = [PROVIDER_KEY, *TOKENS.values(), WRONG_TOKEN, *messages]
    for output in logs + metrics + errors:
        assert not [secret for secret in secrets if secret in output]
