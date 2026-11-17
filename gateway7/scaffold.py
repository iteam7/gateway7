"""Create an installable, offline-testable plugin project without overwriting files."""

from __future__ import annotations

import json
import keyword
import os
from pathlib import Path
import re
import shutil
import tempfile

from gateway7 import __version__
from gateway7.errors import StartupError


_PLUGIN = '''"""A small, pure text policy backed by Gateway7's typed middleware helper."""

from pydantic import BaseModel, ConfigDict, Field

from gateway7.plugin_api import PluginDescriptor
from gateway7.text_policy import TextPolicyMiddleware


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    term: str = Field(default="PRIVATE-TEST", min_length=1, max_length=128)
    replacement: str = Field(default="[removed]", min_length=1, max_length=128)


def create(settings: Settings) -> TextPolicyMiddleware:
    def transform(text: str) -> tuple[str, int]:
        hits = text.count(settings.term)
        return __TRANSFORM__, hits

    return TextPolicyMiddleware(transform, phase="__PHASE__", action="__ACTION__")


PLUGIN = PluginDescriptor(
    id="__PLUGIN_NAME__",
    api_version=2,
    settings_model=Settings,
    create=create,
    # The shared helper inspects typed tools and native Responses safely.
    supports_tools=True,
)
'''


def _native_response(text: str) -> dict[str, object]:
    return {
        "id": "resp_fixture",
        "created_at": 0.0,
        "model": "fake",
        "status": "completed",
        "output": [
            {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 8, "output_tokens": 3, "total_tokens": 11},
    }


def _fixtures(template: str = "redact") -> dict[str, object]:
    guard = template == "guard"
    usage = {"input_tokens": 8, "output_tokens": 3}
    benign = {"messages": [{"role": "user", "content": "Ordinary request"}]}
    chat_response = {"text": "Ordinary answer", "usage": usage}
    cases: list[dict[str, object]] = []

    def case(
        name: str,
        profile: str,
        request: dict,
        response: dict,
        *,
        forwarded: dict | None = None,
        answer: dict | None = None,
        error: str | None = None,
        calls: int = 1,
        deltas: list | None = None,
    ):
        expected: dict[str, object] = {"provider_calls": calls}
        if calls and forwarded is not None:
            expected["request"] = forwarded
        if error is not None:
            expected["error"] = error
        else:
            expected["response"] = response if answer is None else answer
        record: dict[str, object] = {
            "name": name,
            "profile": profile,
            "request": request,
            "provider_response": response,
            "expected": expected,
        }
        if deltas is not None:
            record["provider_deltas"] = deltas
            expected["deltas"] = deltas if error is None else []
        cases.append(record)

    case("benign chat preserves usage", "chat", benign, chat_response, forwarded=benign)
    history = {
        "messages": [
            {"role": role, "content": "Synthetic PRIVATE-TEST"}
            for role in ("system", "user", "assistant", "user")
        ]
    }
    masked_history = {
        "messages": [
            {"role": role, "content": "Synthetic [removed]"}
            for role in ("system", "user", "assistant", "user")
        ]
    }
    sensitive_response = {"text": "Answer PRIVATE-TEST", "usage": usage}
    if guard:
        case(
            "guard blocks request history before provider",
            "chat",
            history,
            sensitive_response,
            error="policy_denied",
            calls=0,
        )
        case(
            "request guard does not promise response filtering",
            "chat",
            benign,
            sensitive_response,
            forwarded=benign,
        )
    else:
        case(
            "redact request history and response",
            "chat",
            history,
            sensitive_response,
            forwarded=masked_history,
            answer={"text": "Answer [removed]", "usage": usage},
        )
    tool = {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Synthetic calculation",
            "parameters": {"type": "object", "properties": {"value": {"type": "string"}}},
        },
    }
    tool_request = {**benign, "tools": [tool], "tool_choice": "auto"}
    tool_answer = {
        "text": "",
        "tool_calls": [
            {
                "id": "call_fixture",
                "type": "function",
                "function": {"name": "calculate", "arguments": '{"value":"ordinary"}'},
            }
        ],
        "finish_reason": "tool_calls",
        "usage": usage,
    }
    case(
        "typed tools preserve call identity and arguments",
        "chat-tools",
        tool_request,
        tool_answer,
        forwarded=tool_request,
    )
    tool_history = {
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_previous",
                        "type": "function",
                        "function": {"name": "calculate", "arguments": '{"value":"ordinary"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_previous", "content": "ordinary"},
            {"role": "user", "content": "Ordinary request"},
        ],
        "tools": [tool],
    }
    case(
        "nullable assistant tool history remains intact",
        "chat-tools",
        tool_history,
        chat_response,
        forwarded=tool_history,
    )
    private_tool = json.loads(json.dumps(tool))
    private_tool["function"]["name"] = "PRIVATE-TEST"
    case(
        "protected tool name is denied rather than rewritten",
        "chat-tools",
        {**benign, "tools": [private_tool]},
        chat_response,
        error="policy_denied",
        calls=0,
    )
    native_request = {"input": "Ordinary request"}
    native_response = _native_response("Ordinary answer")
    case(
        "native Responses retain their own payload",
        "responses",
        native_request,
        native_response,
        forwarded=native_request,
    )
    if guard:
        case(
            "native request guard denies before provider",
            "responses",
            {"input": "PRIVATE-TEST"},
            native_response,
            error="policy_denied",
            calls=0,
        )
    else:
        case(
            "native text is redacted both ways",
            "responses",
            {"input": "PRIVATE-TEST"},
            _native_response("Answer PRIVATE-TEST"),
            forwarded={"input": "[removed]"},
            answer=_native_response("Answer [removed]"),
        )
        private_identity = _native_response("Ordinary answer")
        private_identity["id"] = "resp_PRIVATE-TEST"
        case(
            "native protected response identity fails closed",
            "responses",
            native_request,
            private_identity,
            error="policy_denied",
            calls=1,
        )
    native_deltas = [
        {
            "head": {"id": "resp_fixture", "created_at": 0.0, "model": "fake"},
            "sequence_number": 1,
            "item_id": "msg_fixture",
            "output_index": 0,
            "content_index": 0,
            "phase": "final_answer",
            "delta": "Ordinary answer",
            "leading_prefix": True,
        }
    ]
    if guard:
        case(
            "request-only guard permits early chat",
            "chat-early",
            benign,
            chat_response,
            forwarded=benign,
            deltas=["Ordinary ", "answer"],
        )
        case(
            "early chat guard denies before provider",
            "chat-early",
            history,
            chat_response,
            error="policy_denied",
            calls=0,
            deltas=[],
        )
        case(
            "request-only guard permits native early text",
            "responses-early",
            native_request,
            native_response,
            forwarded=native_request,
            deltas=native_deltas,
        )
        case(
            "native early guard denies before provider",
            "responses-early",
            {"input": "PRIVATE-TEST"},
            native_response,
            error="policy_denied",
            calls=0,
            deltas=[],
        )
    else:
        case(
            "response redactor refuses early chat",
            "chat-early",
            benign,
            chat_response,
            error="early_stream_unsupported",
            calls=0,
            deltas=[],
        )
        case(
            "response redactor refuses native early text",
            "responses-early",
            native_request,
            native_response,
            error="responses_unsupported",
            calls=0,
            deltas=[],
        )
    return {"schema_version": 2, "cases": cases}


def _generated_tests(package: str, template: str) -> str:
    guard = template == "guard"
    lines = [
        '"""Editable unit checks; project fixtures check all declared profiles."""',
        "",
        "import time",
        "import unittest",
        "",
        "from pydantic import ValidationError",
        "from gateway7.models import ChatRequest, ChatResponse, Message",
        "from gateway7.plugin_api import Deny, PluginContext",
        f"from {package}.plugin import Settings, create",
        "",
        "",
        "class PolicyTests(unittest.IsolatedAsyncioTestCase):",
        "    async def test_policy_boundary_and_usage(self) -> None:",
        "        policy = create(Settings())",
        "        calls: list[ChatRequest] = []",
        '        usage = {"input_tokens": 8, "output_tokens": 3}',
        "",
        "        async def provider(request: ChatRequest) -> ChatResponse:",
        "            calls.append(request)",
        '            return ChatResponse(text="Answer PRIVATE-TEST", usage=usage)',
        "",
        '        request = ChatRequest(messages=[Message(role="user", content="PRIVATE-TEST")])',
        '        context = PluginContext("synthetic-unit", time.monotonic() + 2, {})',
        "        result = await policy.handle(request, context, provider)",
    ]
    if guard:
        lines.extend(
            ["        self.assertIsInstance(result, Deny)", "        self.assertEqual(calls, [])"]
        )
    else:
        lines.extend(
            [
                "        if isinstance(result, Deny):",
                '            self.fail("The redactor unexpectedly denied safe text")',
                '        self.assertEqual(result.text, "Answer [removed]")',
                "        self.assertEqual(len(calls), 1)",
                '        self.assertEqual(calls[0].messages[0].content, "[removed]")',
                "        self.assertEqual(result.usage, usage)",
            ]
        )
    lines.extend(
        [
            "",
            "    def test_settings_are_strict(self) -> None:",
            "        with self.assertRaises(ValidationError):",
            '            Settings.model_validate({"unexpected": True})',
            "",
            "",
            'if __name__ == "__main__":',
            "    unittest.main()",
            "",
        ]
    )
    return "\n".join(lines)


def _project_files(name: str, template: str = "redact") -> dict[str, str]:
    package = "gateway7_plugin_" + name
    distribution = "gateway7-plugin-" + name.replace("_", "-")
    # Wheel distribution components collapse each run of name separators.
    wheel_distribution = re.sub(r"[-_.]+", "_", distribution).lower()
    major, minor, _ = __version__.split(".", 2)
    gateway_requirement = f"gateway7>={__version__},<{major}.{int(minor) + 1}"
    guard = template == "guard"
    profiles = ["chat", "chat-tools", "responses"] + (
        ["chat-early", "responses-early"] if guard else []
    )
    source = (
        _PLUGIN.replace("__PLUGIN_NAME__", name)
        .replace(
            "__TRANSFORM__",
            "text" if guard else "text.replace(settings.term, settings.replacement)",
        )
        .replace("__PHASE__", "request" if guard else "both")
        .replace("__ACTION__", "block" if guard else "redact")
    )
    if guard:
        source = source.replace(
            '    replacement: str = Field(default="[removed]", min_length=1, max_length=128)\n', ""
        )
    return {
        f"{package}/__init__.py": '"""Company-owned Gateway7 middleware package."""\n',
        f"{package}/plugin.py": source,
        "tests/test_policy.py": _generated_tests(package, template),
        "pyproject.toml": (
            '[build-system]\nrequires = ["hatchling>=1.27,<2"]\nbuild-backend = "hatchling.build"\n\n[project]\n'
            f'name = "{distribution}"\nversion = "0.1.0"\nrequires-python = ">=3.11,<3.14"\ndependencies = ["{gateway_requirement}"]\n\n'
            '[dependency-groups]\ndev = ["ruff>=0.11,<1", "mypy>=1.15,<3"]\n\n'
            f'[tool.hatch.build.targets.wheel]\npackages = ["{package}"]\n\n'
            '[tool.ruff]\ntarget-version = "py311"\nline-length = 100\n\n'
            '[tool.ruff.lint]\nselect = ["E4", "E7", "E9", "F"]\n\n'
            f'[tool.mypy]\npython_version = "3.11"\nstrict = true\nfiles = ["{package}", "tests"]\n\n'
            f'[tool.gateway7.plugin]\nschema_version = 1\nmodule = "{package}.plugin"\nconfig = "gateway.yaml"\nfixtures = "fixtures.json"\nprofiles = {json.dumps(profiles)}\n'
        ),
        "gateway.yaml": (
            "# Offline fixtures never contact this provider or resolve credentials.\n"
            "provider:\n  kind: fake\n  model: fake\nauth:\n  enabled: false\nplugins:\n  sample:\n"
            f"    module: {package}.plugin\n    required: true\n    settings:\n      term: PRIVATE-TEST\n"
            + ("" if guard else "      replacement: '[removed]'\n")
            + "middleware: [sample]\n"
        ),
        "fixtures.json": json.dumps(_fixtures(template), indent=2, ensure_ascii=False) + "\n",
        "README.md": (
            f"# {name}\n\n{template.capitalize()} middleware generated by Gateway7 {__version__}.\n"
            f"Requires `{gateway_requirement}`; middleware API 2, project schema 1, fixture schema 2.\n\n"
            "## Create, change, verify\n\nFrom this project directory, with the matching Gateway7 environment active:\n\n"
            "```sh\ngateway7 plugin test .\ngateway7 plugin inspect . --json\npython -m unittest discover -s tests -v\ngateway7 plugin dev . --port 0\n```\n\n"
            "Edit the pure transform in `"
            + package
            + "/plugin.py` and expand `fixtures.json` together.\n"
            "Make an expectation fail, run `gateway7 plugin test . --json`, then correct the implementation and rerun.\n"
            "The manifest supplies all paths; no checkout, provider account or live credentials are needed for inspection, fixtures or the synthetic dev service.\n"
            "The dev service prints a loopback URL and synthetic client command; Ctrl-C stops its gateway and upstream.\n\n"
            "## Development checks\n\n"
            "Install only this project's development tool group into the already selected environment containing the reviewed Gateway7 wheel:\n\n"
            "```sh\nuv pip install --group dev\nruff format --check .\nruff check .\nmypy\npython -m unittest discover -s tests -v\n```\n\n"
            "The tool-only installation does not install this project or resolve a different Gateway7 distribution.\n"
            "Use `ruff format .` when formatting needs repair.\n"
            "Do not run `uv sync` or assume an unpublished development Gateway7 build can be fetched from a package index.\n\n"
            "## Capability evidence\n\n"
            f"Declared profiles: {', '.join(profiles)}.\n"
            "Inspection reports hooks and declarations, never tested compatibility.\n"
            "The fixture report separately lists positive passing profiles; denial-only or unsupported-mode tests do not certify a profile.\n"
            + (
                "The guard checks requests only and can prepare early delivery; it does not promise to filter the answer.\n"
                if guard
                else "The redactor checks requests and complete responses; early delivery is deliberately rejected before provider work.\n"
            )
            + "The shared helper handles typed tools and native Responses without flattening their identities or altering provider usage.\n\n"
            "## Build and install\n\n"
            "```sh\nuv build --wheel\nuv pip install --no-deps dist/"
            + wheel_distribution
            + "-0.1.0-py3-none-any.whl\n"
            "gateway7 validate --config gateway.yaml\n```\n\n"
            "Install the reviewed Gateway7 build in the same environment first. Building may download build dependencies; the isolated fixture execution does not.\n"
            "Normal serving loads installed packages, not an implicit project source path.\n"
            "Choose a reviewed authenticated provider configuration before production serving.\n\n"
            "See local `CONTRACT.md` and `AGENTS.md` for the exact versioned authoring contract.\n"
        ),
        "AGENTS.md": (
            f"# Agent instructions for {name}\n\n"
            f"This project targets Gateway7 {__version__}, middleware API 2 and fixtures schema 2.\n"
            f"Change `{package}/plugin.py`, `gateway.yaml` and synthetic `fixtures.json`; project paths are in `[tool.gateway7.plugin]`.\n"
            "Read the bundled `CONTRACT.md`; use the installed public APIs rather than searching for a core checkout.\n\n"
            "1. Inspect: `gateway7 plugin inspect . --json`.\n"
            "2. Add a failing synthetic example: `gateway7 plugin test . --json`.\n"
            "3. Edit the pure `(text) -> (replacement, hits)` transform or its frozen settings.\n"
            "4. Run `gateway7 plugin test . --json` and `python -m unittest discover -s tests -v`.\n"
            "5. Install tools only with `uv pip install --group dev` in the reviewed Gateway7 environment, then run `ruff format --check .`, `ruff check .` and `mypy`.\n"
            "6. Optionally verify actual local HTTP with `gateway7 plugin dev . --port 0`.\n\n"
            "Never rewrite call IDs, tool names or executable arguments to force a fixture to pass; deny protected matches.\n"
            "Preserve provider usage, typed payloads, ordering and cancellation.\n"
            "Do not advertise early support for response-dependent settings.\n"
            "Do not log or retain prompts, answers or credentials; do not use live data in fixture reports.\n"
            "Do not claim inspection, negative tests or Chat-only examples certify other profiles.\n"
            "There is no generated lockfile: do not assume `uv run --locked` applies here.\n"
        ),
        "CONTRACT.md": (
            f"# Gateway7 {__version__}: local plugin contract\n\n"
            "Middleware API: **2**. Project manifest: **1**. Fixture schema: **2**.\n"
            f"Runtime requirement: `{gateway_requirement}`.\n\n"
            "## Public imports\n\n"
            "```python\nfrom gateway7.plugin_api import PluginDescriptor, Deny\nfrom gateway7.text_policy import TextPolicyMiddleware\nfrom gateway7.models import ChatRequest, ChatResponse\nfrom gateway7.responses_models import ResponsesRequest, ResponsesResponse\n```\n\n"
            "`TextPolicyMiddleware(transform, *, phase='both', action='redact')` accepts a pure synchronous callable returning `(replacement: str, hits: int)`.\n"
            "Use `phase='request', action='block'` for a request guard, and `phase='both', action='redact'` for buffered two-way redaction.\n"
            "Factories are synchronous; returned middleware hooks are asynchronous.\n"
            "`Settings` must be strict, frozen and forbid unknown fields.\n"
            "`PLUGIN` is a `PluginDescriptor` with `api_version=2` and the settings class and factory.\n"
            "The shared helper supports typed tools; `supports_tools=True` is its explicit contract, not permission to bypass inspection.\n\n"
            "## Preserve boundaries\n\n"
            "Allowed Chat calls await `call_next` once; request denial makes zero provider calls.\n"
            "Native Responses use their own request/check hooks and typed payloads, never a flattened Chat conversion.\n"
            "Early hooks run request checks only and reject response-dependent configurations.\n"
            "Routing, model selection, authentication, consent and provider usage remain gateway-owned.\n"
            "Only synthetic fixtures are printed. The offline worker blocks Python networking and subprocess creation and strips credentials; it is not an OS sandbox for hostile native code.\n"
            "Fixture schema 2 accepts 1–64 uniquely named cases in a synthetic JSON file up to 1 MiB; names begin with an ASCII letter, then use ASCII letters/digits, spaces, underscores, dots or hyphens, up to 128 characters.\n"
            "Early profile evidence requires a positive, nonempty validated delta emitted before completion; an empty prefix and final response alone do not prove early emission.\n"
            "Fixture reports show expected/actual and per-profile evidence, with exits 0 (pass), 1 (mismatch), 2 (invalid setup, worker failure or timeout).\n"
            "Inspection reports available hooks and declared profiles with no test certification.\n"
        ),
    }


def create_plugin_project(name: str, directory: str | Path, template: str = "redact") -> Path:
    if template not in ("guard", "redact"):
        raise StartupError("Plugin template must be guard or redact")
    if (
        re.fullmatch(r"[a-z][a-z0-9_]{0,47}", name) is None
        or keyword.iskeyword(name)
        or name.upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
    ):
        raise StartupError(
            "Plugin name must be a lowercase Python identifier, at most 48 characters"
        )
    try:
        parent = Path(directory).resolve(strict=True)
        if not parent.is_dir():
            raise OSError
        target = parent / name
        with tempfile.TemporaryDirectory(prefix=".gateway7-plugin-", dir=parent) as temporary:
            staging = Path(temporary)
            for relative, content in _project_files(name, template).items():
                path = staging / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("x", encoding="utf-8", newline="\n") as output:
                    output.write(content)
            # Exclusive directory creation refuses existing files, directories and
            # symlinks. Stage first so generation failures leave no partial project.
            target.mkdir()
            identity = target.stat(follow_symlinks=False)
            descriptor = None
            try:
                if os.rename in os.supports_dir_fd and hasattr(os, "O_DIRECTORY"):
                    descriptor = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                for item in staging.iterdir():
                    if descriptor is not None:
                        os.rename(item, item.name, dst_dir_fd=descriptor)
                    else:
                        if target.is_symlink():
                            raise OSError
                        item.rename(target / item.name)
            except BaseException:
                current = target.stat(follow_symlinks=False)
                if (identity.st_dev, identity.st_ino) == (current.st_dev, current.st_ino):
                    shutil.rmtree(target)
                raise
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        return target
    except FileExistsError:
        raise StartupError("Plugin target already exists; choose a new name or directory") from None
    except (OSError, ValueError):
        raise StartupError("Cannot create plugin project in the selected directory") from None
