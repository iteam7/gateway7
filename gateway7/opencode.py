"""OpenCode V2 connection profile for the Gateway7 Chat endpoint."""

from typing import Any


def opencode_config(base_url: str, model: str) -> dict[str, Any]:
    # Use the native V2 Chat runtime; limits keep the gateway contract bounded.
    selector = f"gateway7/{model}"
    permissions = [
        {"action": "*", "resource": "*", "effect": "deny"},
        {"action": "read", "resource": "*", "effect": "allow"},
    ]
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": selector,
        "policies": [
            {"action": "provider.use", "resource": "*", "effect": "deny"},
            {"action": "provider.use", "resource": "gateway7", "effect": "allow"},
        ],
        "providers": {
            "gateway7": {
                "package": "@opencode/ai/providers/openai-compatible",
                "name": "Gateway7",
                "settings": {
                    "baseURL": base_url,
                    "apiKey": "{env:GATEWAY7_CLIENT_TOKEN}",
                },
                "body": {"parallel_tool_calls": False},
                "models": {
                    model: {
                        "name": model,
                        "limit": {"context": 32768, "output": 1024},
                        "capabilities": {"tools": True, "input": ["text"], "output": ["text"]},
                    }
                },
            }
        },
        "agents": {"title": {"model": selector}},
        "permissions": permissions,
        "plugins": [],
    }
