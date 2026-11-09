"""Native builtins inspect plaintext beside opaque data without executable rewrites."""

from copy import deepcopy

import pytest

from gateway7.config import GatewayConfig, LimitsConfig
from gateway7.errors import GatewayError
from gateway7.loader import load_plugins
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import Deny, ResponsesContext, ResponsesUnsupported
from gateway7.plugins import content_policy, email_mask, phone_mask
from gateway7.responses_models import (
    ResponsesConsent,
    ResponsesRequest,
    ResponsesResponse,
    validate_request,
)

ALL = ResponsesConsent(allow_opaque=True, allow_hosted=True)
FUNCTION = {"type": "function", "name": "read", "parameters": {}}
CUSTOM = {
    "type": "custom",
    "name": "patch",
    "format": {
        "type": "grammar",
        "syntax": "lark",
        "definition": "start: /safe/",
    },
}


def message(text="safe", role="user", **changes):
    return {"type": "message", "role": role, "content": text, **changes}


def call(**changes):
    return {
        "type": "function_call",
        "id": "fc_old",
        "call_id": "call_old",
        "name": "read",
        "arguments": "{}",
        **changes,
    }


def history(item=None, output="safe", **result_changes):
    item = item or call()
    result = {
        "type": item["type"] + "_output",
        "call_id": item["call_id"],
        "output": output,
        **result_changes,
    }
    return [item, result]


def search_history(tools=None, arguments=None):
    return [
        {
            "type": "tool_search_call",
            "call_id": "search_old",
            "execution": "client",
            "arguments": arguments or {},
        },
        {
            "type": "tool_search_output",
            "call_id": "search_old",
            "execution": "client",
            "status": "completed",
            "tools": tools or [],
        },
    ]


def request(**changes):
    return ResponsesRequest.model_validate({"input": "safe", **changes}, context={"consent": ALL})


def response(**changes):
    return ResponsesResponse.model_validate(
        {
            "id": "resp_native",
            "created_at": 1800000000,
            "model": "synthetic-model",
            "status": "completed",
            "output": [
                message(
                    [
                        {"type": "output_text", "text": "safe"},
                    ],
                    role="assistant",
                    id="msg_new",
                )
            ],
            **changes,
        }
    )


def context():
    return ResponsesContext("synthetic-native", 999999999999, {}, "native-policy")


class Provider:
    def __init__(self, result=None):
        self.calls = 0
        self.result = result or response()

    async def complete_responses(self, request, **options):
        self.calls += 1
        return self.result

    async def complete_responses_early(self, request, *, on_text, **options):
        self.calls += 1
        await on_text(self.result.output_text)
        return self.result


def pipeline(module, settings, result=None):
    config = GatewayConfig.model_validate(
        {
            "plugins": {"guard": {"module": "gateway7.plugins." + module, "settings": settings}},
            "middleware": ["guard"],
        }
    )
    provider = Provider(result)
    return Pipeline(
        load_plugins(config), provider, LimitsConfig(), provider_name="openai"
    ), provider


def request_surfaces():
    cases = [("input", {"input": "BLOCK"}), ("instructions", {"instructions": "BLOCK"})]
    for role in ("user", "system", "developer", "assistant"):
        cases += [
            ("message-" + role, {"input": [message("BLOCK", role)]}),
            ("part-" + role, {"input": [message([{"type": "input_text", "text": "BLOCK"}], role)]}),
        ]
    for phase in ("commentary", "final_answer"):
        cases.append(
            (
                phase,
                {
                    "input": [
                        message(
                            [{"type": "output_text", "text": "BLOCK"}], "assistant", phase=phase
                        )
                    ]
                },
            )
        )
    cases += [
        ("refusal", {"input": [message([{"type": "refusal", "refusal": "BLOCK"}], "assistant")]}),
        (
            "reasoning-summary",
            {
                "input": [
                    {"type": "reasoning", "summary": [{"type": "summary_text", "text": "BLOCK"}]}
                ]
            },
        ),
        (
            "reasoning-content",
            {
                "input": [
                    {"type": "reasoning", "content": [{"type": "reasoning_text", "text": "BLOCK"}]}
                ]
            },
        ),
        ("cache-key", {"prompt_cache_key": "BLOCK"}),
        ("metadata-key", {"client_metadata": {"BLOCK": "safe"}}),
        ("metadata-value", {"client_metadata": {"safe": "BLOCK"}}),
        ("function-name", {"tools": [{**FUNCTION, "name": "BLOCK"}]}),
        ("function-description", {"tools": [{**FUNCTION, "description": "BLOCK"}]}),
        ("schema-key", {"tools": [{**FUNCTION, "parameters": {"BLOCK": "safe"}}]}),
        ("schema-value", {"tools": [{**FUNCTION, "parameters": {"safe": ["BLOCK"]}}]}),
        (
            "schema-not-opaque",
            {"tools": [{**FUNCTION, "parameters": {"encrypted_content": "BLOCK"}}]},
        ),
        ("custom-name", {"tools": [{**CUSTOM, "name": "BLOCK"}]}),
        ("custom-description", {"tools": [{**CUSTOM, "description": "BLOCK"}]}),
        (
            "grammar",
            {
                "tools": [
                    {
                        **CUSTOM,
                        "format": {"type": "grammar", "syntax": "regex", "definition": "BLOCK"},
                    }
                ]
            },
        ),
        (
            "namespace-name",
            {
                "tools": [
                    {
                        "type": "namespace",
                        "name": "BLOCK",
                        "description": "safe",
                        "tools": [FUNCTION],
                    }
                ]
            },
        ),
        (
            "namespace-description",
            {
                "tools": [
                    {"type": "namespace", "name": "ns", "description": "BLOCK", "tools": [FUNCTION]}
                ]
            },
        ),
        (
            "namespace-child",
            {
                "tools": [
                    {
                        "type": "namespace",
                        "name": "ns",
                        "description": "safe",
                        "tools": [{**FUNCTION, "description": "BLOCK"}],
                    }
                ]
            },
        ),
        ("decoded-argument-key", {"input": history(call(arguments='{"\\u0042LOCK":"safe"}'))}),
        ("decoded-argument-value", {"input": history(call(arguments='{"key":"\\u0042LOCK"}'))}),
        ("call-name", {"input": history(call(name="BLOCK"))}),
        ("call-id", {"input": history(call(call_id="BLOCK"))}),
        ("item-id", {"input": history(call(id="BLOCK"))}),
        ("call-namespace", {"input": history(call(namespace="BLOCK"))}),
        (
            "custom-raw",
            {
                "input": history(
                    {
                        "type": "custom_tool_call",
                        "call_id": "custom_old",
                        "name": "patch",
                        "input": "BLOCK",
                    }
                )
            },
        ),
        ("result-text", {"input": history(output="BLOCK")}),
        ("result-parts", {"input": history(output=[{"type": "input_text", "text": "BLOCK"}])}),
        (
            "custom-result",
            {
                "input": history(
                    {
                        "type": "custom_tool_call",
                        "call_id": "custom_old",
                        "name": "patch",
                        "input": "safe",
                    },
                    output="BLOCK",
                )
            },
        ),
        (
            "custom-result-parts",
            {
                "input": history(
                    {
                        "type": "custom_tool_call",
                        "call_id": "custom_old",
                        "name": "patch",
                        "input": "safe",
                    },
                    output=[{"type": "input_text", "text": "BLOCK"}],
                )
            },
        ),
        (
            "search-parameters",
            {
                "tools": [
                    {"type": "tool_search", "execution": "client", "parameters": {"key": "BLOCK"}}
                ]
            },
        ),
        (
            "search-description",
            {"tools": [{"type": "tool_search", "execution": "client", "description": "BLOCK"}]},
        ),
        ("search-arguments", {"input": search_history(arguments={"query": "BLOCK"})}),
        ("search-argument-key", {"input": search_history(arguments={"BLOCK": "safe"})}),
        (
            "deferred-definition",
            {
                "input": search_history(
                    tools=[{**FUNCTION, "description": "BLOCK", "defer_loading": True}]
                )
            },
        ),
        (
            "deferred-grammar",
            {
                "input": search_history(
                    tools=[
                        {
                            **CUSTOM,
                            "format": {"type": "grammar", "syntax": "lark", "definition": "BLOCK"},
                        }
                    ]
                )
            },
        ),
        (
            "deferred-namespace",
            {
                "input": search_history(
                    tools=[
                        {
                            "type": "namespace",
                            "name": "ns",
                            "description": "BLOCK",
                            "tools": [FUNCTION],
                        }
                    ]
                )
            },
        ),
        (
            "format-name",
            {
                "text": {
                    "format": {"type": "json_schema", "name": "BLOCK", "strict": True, "schema": {}}
                }
            },
        ),
        (
            "format-schema",
            {
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "schema",
                        "strict": True,
                        "schema": {"key": "BLOCK"},
                    }
                }
            },
        ),
    ]
    for field in ("country", "city", "region", "timezone"):
        cases.append(
            (
                "hosted-location-" + field,
                {
                    "tools": [
                        {
                            "type": "web_search",
                            "user_location": {"type": "approximate", field: "BLOCK"},
                        }
                    ]
                },
            )
        )
    cases.append(
        (
            "hosted-filter",
            {"tools": [{"type": "web_search", "filters": {"allowed_domains": ["BLOCK"]}}]},
        )
    )
    for label, action in [
        ("query", {"type": "search", "query": "BLOCK"}),
        ("queries", {"type": "search", "queries": ["BLOCK"]}),
        ("source", {"type": "search", "sources": [{"type": "url", "url": "BLOCK"}]}),
        ("open", {"type": "open_page", "url": "BLOCK"}),
        ("find-url", {"type": "find_in_page", "url": "BLOCK", "pattern": "safe"}),
        ("find-pattern", {"type": "find_in_page", "url": "safe", "pattern": "BLOCK"}),
    ]:
        cases.append(
            ("hosted-" + label, {"input": [{"type": "web_search_call", "action": action}]})
        )
    for field in ("title", "url"):
        annotation = {
            "type": "url_citation",
            "start_index": 0,
            "end_index": 4,
            "title": "safe",
            "url": "safe",
            field: "BLOCK",
        }
        cases.append(
            (
                "annotation-" + field,
                {
                    "input": [
                        message(
                            [{"type": "output_text", "text": "safe", "annotations": [annotation]}],
                            "assistant",
                        )
                    ]
                },
            )
        )
    return [pytest.param(changes, id=label) for label, changes in cases]


@pytest.mark.parametrize("changes", request_surfaces())
async def test_all_accepted_request_plaintext_is_checked_before_any_provider_attempt(changes):
    runner, provider = pipeline("content_policy", {"terms": ["BLOCK"], "phase": "request"})
    with pytest.raises(GatewayError) as caught:
        await runner.run_responses(request(**changes), consent=ALL)
    assert caught.value.code == "policy_denied" and provider.calls == 0


def response_surfaces():
    cases = [
        (
            "message",
            {
                "output": [
                    message([{"type": "output_text", "text": "BLOCK"}], "assistant", id="msg_new")
                ]
            },
        ),
        (
            "refusal",
            {
                "output": [
                    message([{"type": "refusal", "refusal": "BLOCK"}], "assistant", id="msg_new")
                ]
            },
        ),
        (
            "summary",
            {
                "output": [
                    {
                        "type": "reasoning",
                        "id": "rs_new",
                        "summary": [{"type": "summary_text", "text": "BLOCK"}],
                    }
                ]
            },
        ),
        (
            "reasoning",
            {
                "output": [
                    {
                        "type": "reasoning",
                        "id": "rs_new",
                        "content": [{"type": "text", "text": "BLOCK"}],
                    }
                ]
            },
        ),
        ("function-arguments", {"output": [call(arguments='{"key":"\\u0042LOCK"}')]}),
        (
            "custom-raw",
            {
                "output": [
                    {
                        "type": "custom_tool_call",
                        "id": "custom_new",
                        "name": "patch",
                        "call_id": "call_new",
                        "input": "BLOCK",
                    }
                ]
            },
        ),
        (
            "search-arguments",
            {
                "output": [
                    {
                        "type": "tool_search_call",
                        "id": "search_new",
                        "call_id": "call_search",
                        "execution": "client",
                        "arguments": {"key": "BLOCK"},
                    }
                ]
            },
        ),
        (
            "search-loaded",
            {
                "output": [
                    {
                        "type": "tool_search_output",
                        "id": "search_new",
                        "execution": "server",
                        "status": "completed",
                        "tools": [{**FUNCTION, "description": "BLOCK"}],
                    }
                ]
            },
        ),
        (
            "web-query",
            {
                "output": [
                    {
                        "type": "web_search_call",
                        "id": "web_new",
                        "action": {"type": "search", "query": "BLOCK"},
                    }
                ]
            },
        ),
        ("metadata-key", {"metadata": {"BLOCK": "safe"}}),
        ("metadata-value", {"metadata": {"key": "BLOCK"}}),
        ("echo-instructions", {"instructions": "BLOCK"}),
        ("echo-tools", {"tools": [{**FUNCTION, "description": "BLOCK"}]}),
        ("cache-key", {"prompt_cache_key": "BLOCK"}),
        ("error-message", {"status": "failed", "error": {"code": "synthetic", "message": "BLOCK"}}),
    ]
    for field in ("id", "name", "call_id", "namespace"):
        cases.append(("function-" + field, {"output": [call(**{field: "BLOCK"})]}))
    for field in ("title", "url"):
        cases.append(
            (
                "annotation-" + field,
                {
                    "output": [
                        message(
                            [
                                {
                                    "type": "output_text",
                                    "text": "safe",
                                    "annotations": [
                                        {
                                            "type": "url_citation",
                                            "start_index": 0,
                                            "end_index": 4,
                                            "title": "safe",
                                            "url": "safe",
                                            field: "BLOCK",
                                        }
                                    ],
                                }
                            ],
                            "assistant",
                            id="msg_new",
                        )
                    ]
                },
            )
        )
    return [pytest.param(changes, id=label) for label, changes in cases]


@pytest.mark.parametrize("changes", response_surfaces())
async def test_native_response_hook_inspects_all_plaintext_surfaces(changes):
    plugin = content_policy.create(content_policy.Settings(terms=("BLOCK",), phase="response"))
    assert isinstance(await plugin.check_responses(response(**changes), context()), Deny)


@pytest.mark.parametrize(
    "module,settings,token,replacement",
    [
        (email_mask, email_mask.Settings(phase="both"), "fixture@example.invalid", "[EMAIL]"),
        (phone_mask, phone_mask.Settings(phase="both"), "+79000000000", "[PHONE]"),
        (
            content_policy,
            content_policy.Settings(terms=("BLOCK",), action="redact"),
            "BLOCK",
            "[removed]",
        ),
    ],
)
async def test_free_text_masks_preserve_roles_phases_order_controls_and_raw_arguments(
    module, settings, token, replacement
):
    original = request(
        input=[
            message(token, "developer"),
            message([{"type": "input_text", "text": token}], "user"),
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": token}],
                "content": [{"type": "reasoning_text", "text": token}],
            },
            *history(
                call(arguments=' {"path": "safe.txt"} '),
                output=[{"type": "input_text", "text": token}],
            ),
        ],
        instructions=token,
        tools=[{**FUNCTION, "description": token}],
        max_output_tokens=4096,
        parallel_tool_calls=True,
        reasoning={"effort": "high"},
        stream_options={"include_obfuscation": False},
    )
    before = deepcopy(original.wire_dict())
    plugin = module.create(settings)
    result = await plugin.prepare_responses(original, context())
    assert type(result) is ResponsesRequest
    result = validate_request(result, consent=ALL)
    expected = deepcopy(before)
    expected["instructions"] = replacement
    expected["tools"][0]["description"] = replacement
    expected["input"][0]["content"] = replacement
    expected["input"][1]["content"][0]["text"] = replacement
    expected["input"][2]["summary"][0]["text"] = replacement
    expected["input"][2]["content"][0]["text"] = replacement
    expected["input"][4]["output"][0]["text"] = replacement
    assert result.wire_dict() == expected and original.wire_dict() == before
    answer = response(
        output=[
            message(
                [{"type": "output_text", "text": token}],
                "assistant",
                id="msg_new",
                phase="commentary",
            )
        ]
    )
    checked = await plugin.check_responses(answer, context())
    assert checked.output_text == replacement and checked.output[0].phase == "commentary"


@pytest.mark.parametrize(
    "module,settings,token",
    [
        (email_mask, email_mask.Settings(phase="request"), "fixture@example.invalid"),
        (phone_mask, phone_mask.Settings(phase="request"), "+79000000000"),
        (
            content_policy,
            content_policy.Settings(terms=("BLOCK",), phase="request", action="redact"),
            "BLOCK",
        ),
    ],
)
@pytest.mark.parametrize(
    "surface",
    [
        "schema-key",
        "schema-value",
        "function-argument",
        "custom-raw",
        "grammar",
        "metadata",
        "cache",
    ],
)
async def test_structured_matches_are_denied_not_rewritten(module, settings, token, surface):
    changes = {
        "schema-key": {"tools": [{**FUNCTION, "parameters": {token: "safe"}}]},
        "schema-value": {"tools": [{**FUNCTION, "parameters": {"key": token}}]},
        "function-argument": {"input": history(call(arguments='{"key":"' + token + '"}'))},
        "custom-raw": {
            "input": history(
                {
                    "type": "custom_tool_call",
                    "name": "patch",
                    "call_id": "custom_old",
                    "input": token,
                }
            )
        },
        "grammar": {
            "tools": [
                {**CUSTOM, "format": {"type": "grammar", "syntax": "lark", "definition": token}}
            ]
        },
        "metadata": {"client_metadata": {"key": token}},
        "cache": {"prompt_cache_key": token},
    }[surface]
    original = request(**changes)
    before = deepcopy(original.wire_dict())
    assert isinstance(await module.create(settings).prepare_responses(original, context()), Deny)
    assert original.wire_dict() == before


async def test_only_exact_opaque_fields_are_exempt_and_adjacent_plaintext_is_still_checked():
    opaque = "BLOCK@example.invalid"
    original = request(
        input=[
            {"type": "reasoning", "encrypted_content": opaque},
            *history(
                call(encrypted_function_args=[opaque]),
                output=[
                    {"type": "encrypted_content", "encrypted_content": opaque},
                    {"type": "input_image", "image_url": "data:image/png;base64,QkxPQ0s="},
                    {"type": "input_audio", "audio_url": "data:audio/wav;base64,QkxPQ0s="},
                    {"type": "input_text", "text": "safe"},
                ],
            ),
        ]
    )
    plugin = content_policy.create(
        content_policy.Settings(terms=("BLOCK", "QkxPQ0s"), phase="request")
    )
    result = await plugin.prepare_responses(original, context())
    assert type(result) is ResponsesRequest and result.wire_dict() == original.wire_dict()
    changed = deepcopy(original.wire_dict())
    changed["input"][0]["summary"] = [{"type": "summary_text", "text": "BLOCK"}]
    assert isinstance(await plugin.prepare_responses(request(**changed), context()), Deny)
    changed = deepcopy(original.wire_dict())
    changed["input"][2]["output"][-1]["text"] = "BLOCK"
    assert isinstance(await plugin.prepare_responses(request(**changed), context()), Deny)


@pytest.mark.parametrize("phase", ["both", "response"])
@pytest.mark.parametrize(
    "module,settings",
    [
        (content_policy, {"terms": ("BLOCK",)}),
        (email_mask, {}),
        (phone_mask, {}),
    ],
)
async def test_native_early_hook_refuses_response_policy_instead_of_skipping_it(
    module, settings, phase
):
    plugin = module.create(module.Settings(phase=phase, **settings))
    with pytest.raises(ResponsesUnsupported):
        await plugin.prepare_early_responses(request(), context())
    runner, provider = pipeline(module.__name__.rsplit(".", 1)[-1], {**settings, "phase": phase})

    async def on_text(text):
        pytest.fail("An incompatible policy must emit nothing")

    with pytest.raises(ResponsesUnsupported):
        await runner.run_responses_early(request(), consent=ALL, on_text=on_text)
    assert provider.calls == 0


async def test_redaction_refuses_annotation_offset_changes_and_log_keeps_payload(caplog):
    answer = response(
        output=[
            message(
                [
                    {
                        "type": "output_text",
                        "text": "BLOCK",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "title": "safe",
                                "url": "safe",
                                "start_index": 0,
                                "end_index": 5,
                            }
                        ],
                    }
                ],
                "assistant",
                id="msg_new",
            )
        ]
    )
    plugin = content_policy.create(content_policy.Settings(terms=("BLOCK",), action="redact"))
    assert isinstance(await plugin.check_responses(answer, context()), Deny)
    plugin = content_policy.create(content_policy.Settings(terms=("BLOCK",), action="log"))
    with caplog.at_level("INFO", logger="gateway7"):
        result = await plugin.check_responses(answer, context())
    assert result.wire_dict() == answer.wire_dict()
    assert "policy_match" in caplog.text and "BLOCK" not in caplog.text


async def test_response_opaque_bytes_do_not_hide_adjacent_reasoning_summary():
    answer = response(
        output=[
            {
                "type": "reasoning",
                "id": "rs_new",
                "encrypted_content": "BLOCK==",
                "summary": [{"type": "summary_text", "text": "safe"}],
            }
        ]
    )
    plugin = content_policy.create(content_policy.Settings(terms=("BLOCK",), action="block"))
    assert (await plugin.check_responses(answer, context())).wire_dict() == answer.wire_dict()
    changed = response(
        output=[
            {
                "type": "reasoning",
                "id": "rs_new",
                "encrypted_content": "BLOCK==",
                "summary": [{"type": "summary_text", "text": "BLOCK"}],
            }
        ]
    )
    assert isinstance(await plugin.check_responses(changed, context()), Deny)


async def test_hosted_search_consent_does_not_exempt_server_arguments_or_loaded_definitions():
    base = [
        {
            "type": "tool_search_call",
            "execution": "server",
            "call_id": "call_server",
            "arguments": {},
        },
        {
            "type": "tool_search_output",
            "execution": "server",
            "call_id": "call_server",
            "status": "completed",
            "tools": [],
        },
    ]
    for index in (0, 1):
        items = deepcopy(base)
        if index == 0:
            items[0]["arguments"] = {"query": "BLOCK"}
        else:
            items[1]["tools"] = [{**FUNCTION, "description": "BLOCK"}]
        runner, provider = pipeline("content_policy", {"terms": ["BLOCK"], "phase": "request"})
        with pytest.raises(GatewayError) as caught:
            await runner.run_responses(request(input=items), consent=ALL)
        assert caught.value.code == "policy_denied" and provider.calls == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"input": [message("safe", id="BLOCK")]},
        {"input": [{"type": "reasoning", "id": "BLOCK", "summary": []}]},
        {"input": history(call(id="BLOCK"))},
        {"input": history(call(call_id="BLOCK"))},
        {"input": history(call(namespace="BLOCK"))},
        {
            "tools": [
                {"type": "namespace", "name": "BLOCK", "description": "safe", "tools": [FUNCTION]}
            ]
        },
    ],
)
async def test_protected_native_identity_matches_are_denied_not_ignored_or_rewritten(changes):
    original = request(**changes)
    before = deepcopy(original.wire_dict())
    runner, provider = pipeline(
        "content_policy", {"terms": ["BLOCK"], "phase": "request", "action": "redact"}
    )
    with pytest.raises(GatewayError) as caught:
        await runner.run_responses(original, consent=ALL)
    assert caught.value.code == "policy_denied" and provider.calls == 0
    assert original.wire_dict() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "BLOCK"},
        {"model": "BLOCK"},
        {"metadata": {"correlation": "BLOCK"}},
        {"output": [message([{"type": "output_text", "text": "safe"}], "assistant", id="BLOCK")]},
    ],
)
async def test_provider_metadata_privacy_matches_are_denied_without_rewriting(changes):
    answer = response(**changes)
    before = deepcopy(answer.wire_dict())
    runner, provider = pipeline(
        "content_policy",
        {"terms": ["BLOCK"], "phase": "response", "action": "redact"},
        result=answer,
    )
    with pytest.raises(GatewayError) as caught:
        await runner.run_responses(request(), consent=ALL)
    assert caught.value.code == "policy_denied" and provider.calls == 1
    assert answer.wire_dict() == before


@pytest.mark.parametrize("early", [False, True])
async def test_native_builtin_chain_masks_request_and_only_configured_response_phases(early):
    phase = "request" if early else "both"
    config = GatewayConfig.model_validate(
        {
            "plugins": {
                "policy": {
                    "module": "gateway7.plugins.content_policy",
                    "settings": {
                        "terms": ["secret"],
                        "action": "redact",
                        "phase": phase,
                    },
                },
                "email": {"module": "gateway7.plugins.email_mask", "settings": {"phase": phase}},
                "phone": {"module": "gateway7.plugins.phone_mask", "settings": {"phase": phase}},
            },
            "middleware": ["policy", "email", "phone"],
        }
    )
    text = "secret fixture@example.invalid +79000000000"
    answer = response(
        output=[message([{"type": "output_text", "text": text}], "assistant", id="msg_new")]
    )

    class Inspect(Provider):
        async def complete_responses(self, request, **options):
            assert request.input == "[removed] [EMAIL] [PHONE]"
            return await super().complete_responses(request, **options)

        async def complete_responses_early(self, request, *, on_text, **options):
            assert request.input == "[removed] [EMAIL] [PHONE]"
            return await super().complete_responses_early(request, on_text=on_text, **options)

    provider = Inspect(answer)
    runner = Pipeline(load_plugins(config), provider, config.limits, provider_name="openai")
    chunks = []

    async def on_text(text):
        chunks.append(text)

    result = (
        await runner.run_responses_early(request(input=text), on_text=on_text)
        if early
        else await runner.run_responses(request(input=text))
    )
    assert result.output_text == (text if early else "[removed] [EMAIL] [PHONE]")
    assert chunks == ([text] if early else []) and provider.calls == 1


def known_probability_response(surface="safe", *, statistics=True):
    probability = {
        "token": "BLOCK" if surface == "token" else "safe",
        "bytes": [115],
        "logprob": -0.5,
        "top_logprobs": [
            {"token": "BLOCK" if surface == "top" else "other", "bytes": [111], "logprob": -1.0}
        ],
    }
    return response(
        user="BLOCK" if surface == "user" else "safe-user",
        safety_identifier="BLOCK" if surface == "safety" else "safe-id",
        output=[
            message(
                [
                    {
                        "type": "output_text",
                        "text": "BLOCK" if surface == "text" else "safe",
                        "logprobs": [probability] if statistics is True else statistics,
                    }
                ],
                "assistant",
                id="msg_new",
            )
        ],
    )


@pytest.mark.parametrize("surface", ["user", "safety", "token", "top", "text"])
@pytest.mark.parametrize("action", ["block", "redact"])
async def test_known_subset_probability_and_metadata_plaintext_cannot_leak(surface, action):
    answer = known_probability_response(surface)
    before = deepcopy(answer.wire_dict())
    plugin = content_policy.create(content_policy.Settings(terms=("BLOCK",), action=action))
    assert isinstance(await plugin.check_responses(answer, context()), Deny)
    assert answer.wire_dict() == before


@pytest.mark.parametrize("statistics", [None, []])
async def test_known_subset_empty_probability_metadata_keeps_safe_text_redaction(statistics):
    answer = known_probability_response("text", statistics=statistics)
    plugin = content_policy.create(content_policy.Settings(terms=("BLOCK",), action="redact"))
    result = await plugin.check_responses(answer, context())
    assert not isinstance(result, Deny)
    assert result.output_text == "[removed]"
    assert result.wire_dict()["output"][0]["content"][0]["logprobs"] == statistics


def test_known_subset_snapshot_protects_probability_facts_presence_and_text_but_not_key_order():
    from gateway7.responses_policy import protected_snapshot

    answer = known_probability_response()
    original = protected_snapshot(answer)
    for field, value in (("bytes", [116]), ("token", "different"), ("logprob", -0.7)):
        altered = answer.model_copy(deep=True)
        probability = altered.output[0].content[0].logprobs[0]
        altered.output[0].content[0].logprobs[0] = probability.model_copy(update={field: value})
        assert protected_snapshot(altered) != original
    altered = answer.model_copy(deep=True)
    part = altered.output[0].content[0]
    altered.output[0].content[0] = part.model_copy(update={"text": "different"})
    assert protected_snapshot(altered) != original
    altered = answer.model_copy(deep=True)
    altered.output[0].content[0].__pydantic_fields_set__.discard("logprobs")
    assert protected_snapshot(altered) != original
    altered = answer.model_copy(deep=True)
    probability = altered.output[0].content[0].logprobs[0]
    altered.output[0].content[0].logprobs[0] = type(probability).model_validate(
        dict(reversed(list(probability.wire_dict().items())))
    )
    assert protected_snapshot(altered) == original


@pytest.mark.parametrize(
    "mutation",
    ["text", "token", "top-token", "bytes", "logprob", "user", "safety", "presence", "order"],
)
async def test_known_subset_protected_probability_hook_edits_are_denied_except_key_order(mutation):
    from dataclasses import replace

    answer = known_probability_response()
    runner, provider = pipeline(
        "content_policy", {"terms": ["UNMATCHED"], "phase": "response"}, answer
    )

    async def changed(payload, ctx):
        result = payload.model_copy(deep=True)
        part = result.output[0].content[0]
        probability = part.logprobs[0]
        if mutation == "text":
            result.output[0].content[0] = part.model_copy(update={"text": "changed"})
        elif mutation in ("token", "bytes", "logprob"):
            value = {"token": "changed", "bytes": [116], "logprob": -0.7}[mutation]
            part.logprobs[0] = probability.model_copy(update={mutation: value})
        elif mutation == "top-token":
            probability.top_logprobs[0] = probability.top_logprobs[0].model_copy(
                update={"token": "changed"}
            )
        elif mutation in ("user", "safety"):
            field = "user" if mutation == "user" else "safety_identifier"
            result = result.model_copy(update={field: "changed"})
        elif mutation == "presence":
            result = result.model_copy(update={"max_tool_calls": None})
        else:
            part.logprobs[0] = type(probability).model_validate(
                dict(reversed(list(probability.wire_dict().items())))
            )
        return result

    original = runner.plugins.middleware_chain[0]
    plugin = replace(original, check_responses=changed)
    runner.plugins = replace(
        runner.plugins, instances={plugin.name: plugin}, middleware_chain=(plugin,)
    )
    if mutation == "order":
        result = await runner.run_responses(request(), consent=ALL)
        assert result.wire_dict() == answer.wire_dict()
    else:
        with pytest.raises(GatewayError) as caught:
            await runner.run_responses(request(), consent=ALL)
        assert caught.value.code == "plugin_error"
    assert provider.calls == 1
