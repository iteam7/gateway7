"""Keep installed distribution and public API versions aligned with release metadata."""

from importlib.metadata import version as distribution_version
from pathlib import Path
import tomllib

from gateway7 import __version__
from gateway7.app import create_app


def test_release_version_matches_distribution_and_public_openapi():
    project = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    installed_version = distribution_version("gateway7")
    assert installed_version == project["project"]["version"]
    assert __version__ == installed_version
    application = create_app()
    assert application.version == installed_version
    assert application.openapi()["info"]["version"] == installed_version
