"""QR-03 QRT-02: search a deployed gateway's output for synthetic credentials and messages."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

# The synthetic demo stack generates its provider key in this shape at start.
DEMO_KEY = re.compile(r"gateway7-synthetic-[0-9a-f]{48}")


def post(url: str, body: bytes, token: str | None) -> tuple[int, str]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, body, headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read(2_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read(2_000_000).decode("utf-8", "replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", required=True, help="Gateway URL, such as $STAGING_URL")
    parser.add_argument("--project", required=True, help="Compose project, such as gateway7-staging")
    parser.add_argument("--token-env", default="GATEWAY7_CLIENT_TOKEN", help="Variable holding a valid client token")
    parser.add_argument("--provider-key-env", help="Variable holding the deployment's provider key, if any")
    arguments = parser.parse_args()
    token = os.environ.get(arguments.token_env, "")
    if not token:
        parser.error(f"{arguments.token_env} must hold a valid client token")
    gateway = arguments.gateway.rstrip("/")
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run = uuid.uuid4().hex[:12]
    wrong = f"gateway7-synthetic-qr03-wrong-{run}"
    messages: list[str] = []
    errors: list[str] = []

    def chat(path: str, credential: str | None, *, model: str | None = None,
             prefix: str = "", role: str = "user", padding: int = 0) -> int:
        message = f"qr03-synthetic-message-{run}-{len(messages)}"
        messages.append(message)
        body: dict[str, object] = {
            "messages": [{"role": role, "content": prefix + message + "x" * padding}],
        }
        if model is not None:
            body["model"] = model
        status, text = post(gateway + path, json.dumps(body).encode(), credential)
        if status >= 400:
            errors.append(text)
        print(f"{path} -> HTTP {status}")
        return status

    expected = [
        chat("/chat", token) == 200,
        chat("/v1/chat/completions", token, model="fake") == 200,
        chat("/chat", None) == 401,
        chat("/chat", wrong) == 401,
        chat("/v1/chat/completions", wrong, model="fake") == 401,
        chat("/v1/chat/completions", token, model="qr03-forbidden-model") == 403,
        chat("/chat", token, prefix="BLOCK-ME-TEST ") == 403,
        chat("/chat", token, role="tool") == 422,
        chat("/chat", token, padding=70_000) == 413,
    ]
    with urllib.request.urlopen(gateway + "/metrics", timeout=15) as response:
        metrics = response.read().decode("utf-8", "replace")
    logs = subprocess.run(
        ["docker", "compose", "-p", arguments.project, "logs", "--no-color", "--since", started,
         "gateway"],
        capture_output=True, text=True, timeout=60, check=True,
    ).stdout
    secrets = [token, wrong, *messages]
    if arguments.provider_key_env:
        secrets.append(os.environ.get(arguments.provider_key_env, ""))
    found = 0
    for name, output in (("logs", logs), ("metrics", metrics), ("error bodies", "\n".join(errors))):
        count = sum(output.count(secret) for secret in secrets if secret)
        count += len(DEMO_KEY.findall(output))
        found += count
        print(f"{name}: {len(output)} characters searched, {count} synthetic values found")
    passed = all(expected) and found == 0 and "gateway7_http_requests_total" in metrics
    print(f"{'PASS' if passed else 'FAIL'} QR-03 QRT-02: since={started}, run={run}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
