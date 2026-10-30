"""Create an installable, offline-testable plugin project without overwriting files."""

from __future__ import annotations

import json
import keyword
import os
from pathlib import Path
import re
import shutil
import tempfile

from gateway7.errors import StartupError


_PLUGIN = '''"""Replace one configured literal in request history and model responses."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from gateway7.models import ChatRequest, ChatResponse
from gateway7.plugin_api import NextHandler, PluginContext, PluginDescriptor


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    term: str = Field(default="PRIVATE-TEST", min_length=1, max_length=128)
    replacement: str = Field(default="[removed]", min_length=1, max_length=128)


@dataclass(frozen=True)
class LiteralMask:
    settings: Settings

    async def handle(
        self, request: ChatRequest, context: PluginContext, call_next: NextHandler
    ) -> ChatResponse:
        processed = request.model_copy(update={
            "messages": [message.model_copy(update={
                "content": message.content.replace(self.settings.term, self.settings.replacement)
            }) for message in request.messages]
        })
        response = await call_next(processed)
        return response.model_copy(update={
            "text": response.text.replace(self.settings.term, self.settings.replacement)
        })


def create(settings: Settings) -> LiteralMask:
    return LiteralMask(settings)


PLUGIN = PluginDescriptor(
    id="__PLUGIN_NAME__", api_version=2, settings_model=Settings, create=create,
    # Enable only after inspecting tool schemas, decoded arguments and results.
    supports_tools=False,
)
'''


def _fixtures() -> dict[str, object]:
    usage = {"input_tokens": 8, "output_tokens": 3}
    messages = [
        {"role": "system", "content": "Handle PRIVATE-TEST carefully"},
        {"role": "user", "content": "Earlier PRIVATE-TEST"},
        {"role": "assistant", "content": "Previous PRIVATE-TEST"},
        {"role": "user", "content": "Current PRIVATE-TEST"},
    ]
    request = {"messages": messages, "max_tokens": 32}
    transformed = {
        "messages": [
            {"role": item["role"], "content": item["content"].replace("PRIVATE-TEST", "[removed]")}
            for item in messages
        ],
        "max_tokens": 32,
    }
    benign = {"messages": [{"role": "user", "content": "Ordinary request"}]}
    return {
        "schema_version": 1,
        "cases": [
            {
                "name": "request history and response",
                "request": request,
                "provider_response": {"text": "Answer PRIVATE-TEST", "usage": usage},
                "expected": {
                    "provider_calls": 1,
                    "request": transformed,
                    "response": {"text": "Answer [removed]", "usage": usage},
                },
            },
            {
                "name": "benign text is unchanged",
                "request": benign,
                "provider_response": {"text": "Ordinary answer"},
                "expected": {
                    "provider_calls": 1,
                    "request": benign,
                    "response": {"text": "Ordinary answer"},
                },
            },
        ],
    }


def _project_files(name: str) -> dict[str, str]:
    package = "gateway7_plugin_" + name
    distribution = "gateway7-plugin-" + name.replace("_", "-")
    return {
        f"{package}/__init__.py": '"""Company-owned Gateway7 middleware package."""\n',
        f"{package}/plugin.py": _PLUGIN.replace("__PLUGIN_NAME__", name),
        "pyproject.toml": (
            '[build-system]\nrequires = ["hatchling>=1.27,<2"]\n'
            'build-backend = "hatchling.build"\n\n[project]\n'
            f'name = "{distribution}"\nversion = "0.1.0"\n'
            'requires-python = ">=3.11,<3.14"\ndependencies = ["gateway7>=0.1,<0.2"]\n\n'
            "[tool.hatch.build.targets.wheel]\n"
            f'packages = ["{package}"]\n'
        ),
        "gateway.yaml": (
            "# Offline tests never contact this provider or resolve credentials.\n"
            "provider:\n  kind: fake\n  model: fake\n"
            "auth:\n  enabled: false\n"
            "plugins:\n  sample:\n"
            f"    module: {package}.plugin\n"
            "    required: true\n    settings:\n"
            "      term: PRIVATE-TEST\n      replacement: '[removed]'\n"
            "middleware: [sample]\n"
        ),
        "fixtures.json": json.dumps(_fixtures(), indent=2, ensure_ascii=False) + "\n",
        "README.md": (
            f"# {name}\n\n"
            "An API v2 middleware package with synthetic request-history, response and benign fixtures.\n"
            "The sample replaces the literal `PRIVATE-TEST` with `[removed]` in both directions.\n\n"
            "## Try it offline\n\n"
            "Run these commands from this directory after installing the reviewed Gateway7 wheel in the active Python environment:\n\n"
            "```bash\ngateway7 plugin test --config gateway.yaml --fixtures fixtures.json\n"
            "gateway7 plugin test --config gateway.yaml --fixtures fixtures.json --json\n```\n\n"
            "The offline worker imports packages beside the configuration file, uses a deterministic fixture provider, "
            "and does not read provider or gateway credentials. Expected and actual values are shown for every check. "
            "Use synthetic fixtures only. Exit codes are 0 (all pass), 1 (mismatch), and 2 (invalid setup or timeout).\n\n"
            "## Install and run\n\n"
            "Install uv and the reviewed Gateway7 wheel first, and keep that Python environment active. "
            "From this directory, install only this plugin package, without resolving a different gateway7 distribution:\n\n"
            "```bash\nuv pip install --no-deps .\ngateway7 validate --config gateway.yaml\n```\n\n"
            "Gateway7 checks plugin API version 2 at load time. The package version `0.1.0` alone does not establish API-v2 compatibility.\n\n"
            "The [authoring guide](https://iteam7.github.io/gateway7/authoring/) includes a complete local HTTP walkthrough "
            "with this installed package, a synthetic upstream and a public test token; no provider account is needed.\n\n"
            "Edit `gateway.yaml` to select a real provider, model and authenticated client; supply keys through environment variables. "
            "Then run `gateway7 serve --config gateway.yaml`. The included fake-provider setting is for offline fixtures; "
            "it does not start an upstream service.\n\n"
            f"The module is `{package}.plugin`. Edit `{package}/plugin.py` and expand `fixtures.json` together. "
            "Keep immutable instance settings, await `call_next` exactly once for allowed requests, and use `Deny()` for policy blocks. "
            "Never put message text, original values or credentials in logs or instance state.\n\n"
            "## Offline boundary\n\n"
            "The isolated worker blocks Python socket networking and subprocess creation before importing plugins. "
            "It has a minimal environment and a wall-clock limit (default 30 seconds, adjustable with `--timeout`). "
            "This catches accidental network access; it is not an operating-system sandbox for hostile native code. "
            "Only install and test trusted plugins.\n"
        ),
    }


def create_plugin_project(name: str, directory: str | Path) -> Path:
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
            for relative, content in _project_files(name).items():
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
