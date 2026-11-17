"""Dev reads current project source without changing timestamp-valid user caches."""

import importlib
import importlib.util
from pathlib import Path
import py_compile
import struct
import sys
import time
from uuid import uuid4

import pytest

from gateway7._project_source import project_source_imports
from gateway7.scaffold import create_plugin_project
from test_plugin_dev import _assert_port_released, _ready, _request, _start, _stop


def stale_timestamp_cache(source: Path, before: str, after: str) -> Path:
    """Use ordinary same-size writes in one real timestamp second, never utime."""
    assert len(before.encode()) == len(after.encode())
    for _ in range(4):
        # Start near the second boundary to leave ordinary compilation/writes
        # ample headroom, including on filesystems with coarse timestamps.
        deadline = time.monotonic() + 2
        while time.time() % 1 > 0.1:
            assert time.monotonic() < deadline
            time.sleep(0.005)
        source.write_text(before)
        original = source.stat()
        py_compile.compile(
            str(source), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP
        )
        cache = Path(importlib.util.cache_from_source(str(source)))
        source.write_text(after)
        changed = source.stat()
        flags, timestamp, size = struct.unpack("<III", cache.read_bytes()[4:16])
        if (
            flags == 0
            and timestamp == int(changed.st_mtime) & 0xFFFFFFFF
            and size == changed.st_size
        ):
            assert int(original.st_mtime) == int(changed.st_mtime)
            return cache
    pytest.fail("Could not produce same-second ordinary writes for timestamp-cache regression")


@pytest.mark.parametrize("entry", ["module", "lazy_helper"])
def test_dev_http_uses_edited_source_with_valid_old_cache_and_preserves_files(tmp_path, entry):
    project = create_plugin_project("source_fresh", tmp_path, "guard")
    package = project / "gateway7_plugin_source_fresh"
    module = package / "plugin.py"
    if entry == "module":
        original = module.read_text()
        edited = original.replace("text.count(settings.term)", 'text.count("xxxxxxxxxxx")')
        assert edited != original
        cache = stale_timestamp_cache(module, original, edited)
    else:
        original = module.read_text()
        edited = original.replace(
            "hits = text.count(settings.term)",
            "from .rules import count_matches\n        hits = count_matches(text)",
        )
        assert edited != original
        module.write_text(edited)
        helper = package / "rules.py"
        cache = stale_timestamp_cache(
            helper,
            'def count_matches(text):\n    return text.count("PRIVATE-TEST")\n',
            'def count_matches(text):\n    return text.count("xxxxxxxxxxxx")\n',
        )
    assert cache.exists()
    original_files = {
        str(path.relative_to(project)): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    process, lines, reader = _start(project)
    gateway = upstream = None
    try:
        gateway, upstream, token = _ready(process, lines)
        status, response = _request(
            gateway,
            "/chat",
            token,
            {"model": "synthetic-model", "messages": [{"role": "user", "content": "PRIVATE-TEST"}]},
        )
        assert status == 200, response
        assert "PRIVATE-TEST" in response
    finally:
        _stop(process)
        reader.join(timeout=2)
    assert process.returncode == 0
    _assert_port_released(gateway)
    _assert_port_released(upstream)
    assert original_files == {
        str(path.relative_to(project)): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("namespace", [False, True])
def test_source_context_covers_relative_helpers_and_cleans_up_hook(
    tmp_path, monkeypatch, namespace
):
    package_name = "review_package_" + uuid4().hex
    package = tmp_path / package_name
    package.mkdir()
    if not namespace:
        (package / "__init__.py").write_text("")
    (package / "plugin.py").write_text(
        "def read():\n    from .rules import VALUE\n    return VALUE\n"
    )
    helper = package / "rules.py"
    stale_timestamp_cache(helper, 'VALUE = "old"\n', 'VALUE = "new"\n')
    paths, finders = sys.path[:], sys.meta_path[:]
    try:
        with project_source_imports(tmp_path):
            module = importlib.import_module(package_name + ".plugin")
            assert package_name + ".rules" not in sys.modules
            assert module.read() == "new"
            assert Path(module.__file__).is_relative_to(tmp_path)
        assert sys.path == paths and sys.meta_path == finders
    finally:
        for name in list(sys.modules):
            if name == package_name or name.startswith(package_name + "."):
                monkeypatch.delitem(sys.modules, name, raising=False)


def test_outside_project_modules_keep_normal_loader_and_cache_behavior(tmp_path, monkeypatch):
    project, dependency = tmp_path / "project", tmp_path / "dependency"
    project.mkdir()
    dependency.mkdir()
    name = "review_dependency_" + uuid4().hex
    source = dependency / (name + ".py")
    cache = stale_timestamp_cache(source, 'VALUE = "old"\n', 'VALUE = "new"\n')
    unchanged = cache.read_bytes()
    monkeypatch.syspath_prepend(str(dependency))
    try:
        with project_source_imports(project):
            module = importlib.import_module(name)
            assert module.VALUE == "old"
            assert type(module.__loader__).__name__ == "SourceFileLoader"
        assert cache.read_bytes() == unchanged
    finally:
        monkeypatch.delitem(sys.modules, name, raising=False)


def test_source_context_refuses_bytecode_only_project_module(tmp_path, monkeypatch):
    name = "review_bytecode_" + uuid4().hex
    source = tmp_path / (name + ".py")
    source.write_text('VALUE = "bytecode-only"\n')
    py_compile.compile(str(source), cfile=str(tmp_path / (name + ".pyc")), doraise=True)
    source.unlink()
    try:
        with (
            project_source_imports(tmp_path),
            pytest.raises(ImportError, match="require Python source"),
        ):
            importlib.import_module(name)
    finally:
        monkeypatch.delitem(sys.modules, name, raising=False)
