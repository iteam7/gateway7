"""Explicit management backend selection with private environment credentials."""

import os
import re
from urllib.parse import urlsplit

from gateway7.admin_store import AdminStore, ManagementStore
from gateway7.config import GatewayConfig
from gateway7.errors import StartupError


def postgres_url_from_environment(name: str) -> str:
    """Validate a URL without returning its value in a diagnostic."""
    try:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name) is None:
            raise ValueError
        value = os.environ.get(name, "")
        validate_postgres_url(value)
        return value
    except (ValueError, UnicodeError):
        raise StartupError(
            "Management PostgreSQL URL environment variable is missing or invalid"
        ) from None


def validate_postgres_url(value: str) -> None:
    try:
        if (
            not value
            or len(value) > 16384
            or any(character.isspace() or ord(character) < 33 for character in value)
        ):
            raise ValueError
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("postgres", "postgresql")
            or not parsed.hostname
            or not parsed.path.removeprefix("/")
            or parsed.fragment
        ):
            raise ValueError
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
    except (ValueError, UnicodeError):
        raise ValueError("Invalid management PostgreSQL URL") from None


def open_management_store(config: GatewayConfig) -> ManagementStore:
    """Never infer a backend or fall back after a configured backend fails."""
    if config.auth.management_database_url_env is not None:
        from gateway7.postgres_store import PostgresAdminStore

        dsn = postgres_url_from_environment(config.auth.management_database_url_env)
        return PostgresAdminStore(dsn, config)
    if config.auth.management_db is not None:
        return AdminStore(config.auth.management_db, config)
    raise StartupError("A management database backend must be configured")
