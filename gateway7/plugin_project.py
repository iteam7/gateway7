"""One explicit authoring project manifest; no production import-path changes."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import tomllib
from typing import Any

from gateway7.plugin_diagnostics import diagnostic

PROFILES = ("chat", "chat-tools", "chat-early", "responses", "responses-early")
MAX_PROJECT_BYTES = 1_048_576


@dataclass(frozen=True)
class PluginProject:
    root: Path
    module: str
    config: Path
    fixtures: Path
    profiles: tuple[str, ...]


def _project_file(root: Path, value: Any, field: str) -> Path:
    if (
        type(value) is not str
        or not value
        or len(value) > 1024
        or "\\" in value
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).drive
        or ".." in PurePosixPath(value).parts
    ):
        raise diagnostic(
            "Invalid plugin project path",
            "project_path_invalid",
            "tool.gateway7.plugin." + field,
            "Use a relative file path confined to the project directory",
            file="pyproject.toml",
        )
    try:
        resolved = (root / value).resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError
        return resolved
    except (OSError, ValueError):
        raise diagnostic(
            "Plugin project file is missing or escapes the project",
            "project_file_unavailable",
            "tool.gateway7.plugin." + field,
            "Create the declared file inside the project and avoid escaping symlinks",
            file="pyproject.toml",
        ) from None


def load_project(path: str | Path = ".") -> PluginProject:
    try:
        root = Path(path).resolve(strict=True)
        if not root.is_dir():
            raise ValueError
        manifest = (root / "pyproject.toml").resolve(strict=True)
        if not manifest.is_relative_to(root) or not manifest.is_file():
            raise ValueError
        with manifest.open("rb") as source:
            raw = source.read(MAX_PROJECT_BYTES + 1)
        if len(raw) > MAX_PROJECT_BYTES:
            raise ValueError
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise diagnostic(
            "Cannot read plugin project manifest",
            "project_manifest_unavailable",
            "pyproject.toml",
            "Pass a project directory containing a bounded UTF-8 pyproject.toml",
            file="pyproject.toml",
        ) from None
    try:
        declaration = data["tool"]["gateway7"]["plugin"]
        if (
            type(declaration) is not dict
            or set(declaration) != {"schema_version", "module", "config", "fixtures", "profiles"}
            or type(declaration["schema_version"]) is not int
            or declaration["schema_version"] != 1
        ):
            raise ValueError
        module = declaration["module"]
        profiles = declaration["profiles"]
        if (
            type(module) is not str
            or len(module) > 200
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", module) is None
        ):
            raise ValueError
        if (
            type(profiles) is not list
            or not profiles
            or len(profiles) > len(PROFILES)
            or any(type(profile) is not str or profile not in PROFILES for profile in profiles)
            or len(profiles) != len(set(profiles))
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise diagnostic(
            "Invalid plugin project declaration",
            "project_manifest_invalid",
            "tool.gateway7.plugin",
            "Declare schema_version=1, module, config, fixtures and unique known profiles",
            file="pyproject.toml",
        ) from None
    return PluginProject(
        root,
        module,
        _project_file(root, declaration["config"], "config"),
        _project_file(root, declaration["fixtures"], "fixtures"),
        tuple(profiles),
    )


def validate_project_config(project: PluginProject, config: Any) -> None:
    if not any(
        specification.module == project.module
        and specification.enabled
        and name in config.middleware
        for name, specification in config.plugins.items()
    ):
        raise diagnostic(
            "Declared plugin module is not active in the project chain",
            "project_module_inactive",
            "tool.gateway7.plugin.module",
            "Reference the declared module in an enabled instance in the global middleware chain",
            file="pyproject.toml",
        )
