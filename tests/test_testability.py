"""QR-02: the suite covers the critical modules and catches forwarding after a failure."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CRITICAL_MODULES = ("pipeline", "app", "auth", "providers")
IGNORED = shutil.ignore_patterns(
    ".git", ".venv", ".venv-docs", "node_modules", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", "dist", "build", "site",
)
FAILURE_TESTS = "tests/test_core.py::test_request_failure_never_reaches_provider"
# Forward the request anyway when a request-side middleware raises or denies.
MUTATIONS = (
    (
        "                except Exception:\n"
        "                    if downstream_failure is not None:\n",
        "                except Exception:\n"
        "                    if not called:\n"
        "                        return await dispatch(index + 1, incoming)\n"
        "                    if downstream_failure is not None:\n",
    ),
    (
        "                if type(result) is Deny:\n",
        "                if type(result) is Deny and not called:\n"
        "                    return await dispatch(index + 1, incoming)\n"
        "                if type(result) is Deny:\n",
    ),
)


def test_each_critical_module_has_a_test():
    sources = [path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("test_*.py")]
    for name in CRITICAL_MODULES:
        assert (ROOT / "gateway7" / f"{name}.py").is_file()
        pattern = re.compile(
            rf"(from gateway7\.{name} import|import gateway7\.{name}\b"
            rf"|import_module\(\"gateway7\.{name}\"\))"
        )
        assert any(pattern.search(source) for source in sources), name


@pytest.fixture
def checkout(tmp_path):
    target = tmp_path / "checkout"
    shutil.copytree(ROOT, target, ignore=IGNORED)
    # A minimal environment: no provider keys, tokens or proxy settings reach the runs.
    env = {name: os.environ[name] for name in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if name in os.environ}
    env.update({"PYTHONPATH": str(target), "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(tmp_path)})

    def run(*arguments):
        return subprocess.run(
            [sys.executable, *arguments], cwd=target, env=env,
            capture_output=True, text=True, timeout=240,
        )

    return target, run


def test_forwarding_after_request_failure_fails_the_suite_and_the_demo(checkout):
    target, run = checkout
    located = run("-c", "import gateway7.pipeline as module; print(module.__file__)")
    assert Path(located.stdout.strip()).resolve() == (target / "gateway7" / "pipeline.py").resolve()
    control = run("-m", "pytest", "-q", "-p", "no:cacheprovider", FAILURE_TESTS)
    assert control.returncode == 0, control.stdout[-2000:]

    pipeline = target / "gateway7" / "pipeline.py"
    source = pipeline.read_text(encoding="utf-8")
    for original, broken in MUTATIONS:
        assert source.count(original) == 1, "pipeline.py changed; update the QR-02 mutation"
        source = source.replace(original, broken)
    pipeline.write_text(source, encoding="utf-8")

    targeted = run("-m", "pytest", "-q", "-p", "no:cacheprovider", FAILURE_TESTS)
    assert targeted.returncode != 0
    assert "policy_denied" in targeted.stdout and "failed" in targeted.stdout
    suite = run(
        "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
        "--ignore", "tests/test_testability.py",
    )
    assert suite.returncode != 0
    demo = run("-m", "demo.run")
    assert demo.returncode != 0
    assert "PASS composition" in demo.stdout
    assert "PASS failure: policy_denied" not in demo.stdout
