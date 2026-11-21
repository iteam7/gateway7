"""External policy authors get checked API v2 contracts through public imports."""

import subprocess
import sys


GOOD = """from gateway7.models import ChatRequest, ChatResponse
from gateway7.plugin_api import (
    ChatMiddleware, EarlyChatMiddleware, ResponsesMiddleware,
    EarlyResponsesMiddleware, NextHandler, PluginContext, Deny,
)
from gateway7.text_policy import TextPolicyMiddleware


def transform(text: str) -> tuple[str, int]:
    return text.replace("PRIVATE-TEST", "[removed]"), text.count("PRIVATE-TEST")


policy = TextPolicyMiddleware(transform, phase="request", action="redact")
chat: ChatMiddleware = policy
early_chat: EarlyChatMiddleware = policy
native: ResponsesMiddleware = policy
early_native: EarlyResponsesMiddleware = policy


class AdvancedPolicy:
    async def handle(
        self, request: ChatRequest, context: PluginContext, call_next: NextHandler
    ) -> ChatResponse | Deny:
        return await call_next(request)


advanced: ChatMiddleware = AdvancedPolicy()
"""


def check(tmp_path, source):
    path = tmp_path / "company_policy.py"
    path.write_text(source)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--no-incremental",
            "--follow-imports=silent",
            "--cache-dir",
            str(tmp_path / "cache"),
            str(path),
        ],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_public_helper_and_advanced_contracts_type_check(tmp_path):
    result = check(tmp_path, GOOD)
    assert result.returncode == 0, result.stdout + result.stderr


def test_type_checker_catches_wrong_transform_and_wrong_handler_result(tmp_path):
    result = check(
        tmp_path,
        GOOD
        + """

def wrong_transform(text: str) -> str:
    return text


wrong_policy = TextPolicyMiddleware(wrong_transform)


class BrokenPolicy:
    async def handle(
        self, request: ChatRequest, context: PluginContext, call_next: NextHandler
    ) -> str:
        return "incorrect result"


broken: ChatMiddleware = BrokenPolicy()
""",
    )
    assert result.returncode == 1
    assert "wrong_transform" not in result.stderr
    assert "arg-type" in result.stdout and "assignment" in result.stdout
