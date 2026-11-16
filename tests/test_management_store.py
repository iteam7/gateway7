"""Management backend selection rejects invalid configuration without leaking secrets."""

import pytest
from pydantic import ValidationError

from gateway7.config import GatewayConfig
from gateway7.errors import StartupError
from gateway7.management_store import open_management_store, postgres_url_from_environment


def test_backend_selector_rejects_ambiguous_or_unauthenticated_configuration():
    for auth in (
        {
            "enabled": True,
            "operator_token_env": "OPERATOR",
            "management_db": "private.sqlite3",
            "management_database_url_env": "DATABASE",
        },
        {
            "enabled": False,
            "operator_token_env": "OPERATOR",
            "management_database_url_env": "DATABASE",
        },
        {"enabled": True, "management_database_url_env": "DATABASE"},
        {
            "enabled": True,
            "operator_token_env": "OPERATOR",
            "management_database_url_env": "postgresql://private:secret@example/database",
        },
    ):
        with pytest.raises(ValidationError):
            GatewayConfig.model_validate({"auth": auth})
    config = GatewayConfig.model_validate(
        {
            "auth": {
                "enabled": True,
                "operator_token_env": "OPERATOR",
                "management_database_url_env": "DATABASE",
            }
        }
    )
    assert config.auth.management_enabled
    assert not GatewayConfig().auth.management_enabled


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "sqlite:///private.sqlite3",
        "host=private password=secret",
        "postgresql://private:secret@host",
        "postgresql://private:secret@host/database#secret",
        "postgresql://private:secret@host:99999/database",
        "postgresql://private:secret@host/data base",
    ],
)
def test_database_url_errors_never_reveal_secret_or_fallback(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("MANAGEMENT_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("MANAGEMENT_DATABASE_URL", value)
    with pytest.raises(StartupError) as error:
        postgres_url_from_environment("MANAGEMENT_DATABASE_URL")
    assert "secret" not in str(error.value) and "private" not in str(error.value)


def test_database_factory_failure_does_not_create_sqlite_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("MANAGEMENT_DATABASE_URL", raising=False)
    config = GatewayConfig.model_validate(
        {
            "auth": {
                "enabled": True,
                "operator_token_env": "OPERATOR",
                "management_database_url_env": "MANAGEMENT_DATABASE_URL",
            }
        }
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(StartupError):
        open_management_store(config)
    assert list(tmp_path.iterdir()) == []
