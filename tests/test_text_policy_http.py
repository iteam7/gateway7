"""Native policy denials retain only the safe runner-owned instance name."""

import importlib
import logging

import pytest
from fastapi.testclient import TestClient

from gateway7.app import create_app
from gateway7.config import GatewayConfig

SECRET = "synthetic-private-policy-message"


@pytest.mark.parametrize(
    "phase,stream,early",
    [
        ("request", False, False),
        ("request", True, False),
        ("request", True, True),
        ("response", False, False),
        ("response", True, False),
    ],
)
def test_native_denial_names_the_runner_owned_instance(monkeypatch, caplog, phase, stream, early):
    from gateway7.responses_models import ResponsesResponse

    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-native-diagnostics-provider")
    monkeypatch.setenv("NATIVE_DIAGNOSTICS_CLIENT", "synthetic-native-diagnostics-client")

    class NativeProvider:
        def __init__(self):
            self.calls = []

        async def complete_responses(self, request, **options):
            self.calls.append(request)
            return ResponsesResponse.model_validate(
                {
                    "id": "resp_fixture",
                    "created_at": 1800000000,
                    "model": "model-a",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "id": "msg_fixture",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "BLOCK-ME-TEST " + SECRET}],
                        }
                    ],
                    "usage": {"input_tokens": 7, "output_tokens": 3},
                }
            )

        async def complete_responses_early(self, request, **options):
            pytest.fail("Denied early request must not reach the provider")

        async def aclose(self):
            pass

    provider = NativeProvider()
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
    )
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": "openai", "model": "model-a"},
            "auth": {
                "enabled": True,
                "clients": {
                    "fixture": {"token_env": "NATIVE_DIAGNOSTICS_CLIENT", "models": ["model-a"]}
                },
            },
            "plugins": {
                "company-policy": {
                    "module": "gateway7.plugins.content_policy",
                    "settings": {"terms": ["BLOCK-ME-TEST"], "phase": phase, "action": "block"},
                }
            },
            "middleware": ["company-policy"],
        }
    )
    headers = {"Authorization": "Bearer synthetic-native-diagnostics-client"}
    if early:
        headers["X-Gateway7-Stream-Mode"] = "early"
    with (
        caplog.at_level(logging.INFO, logger="gateway7"),
        TestClient(create_app(config=config)) as client,
    ):
        response = client.post(
            "/v1/responses",
            headers=headers,
            json={
                "model": "model-a",
                "input": "BLOCK-ME-TEST " + SECRET if phase == "request" else "safe",
                "store": False,
                "stream": stream,
            },
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "policy_denied"
    assert response.json()["error"]["middleware"] == "company-policy"
    assert len(provider.calls) == (1 if phase == "response" else 0)
    assert SECRET not in response.text + caplog.text
