"""Strict private identity records; public projections never include their digests."""

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gateway7.admin_runtime import ClientPolicy
from gateway7.auth import credential_expiry
from gateway7.config import InstanceName, ModelId
from gateway7.errors import StartupError


class _Record(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class UserRecord(_Record):
    owner: str = Field(default="", max_length=128)
    tags: list[str] = Field(default_factory=list, max_length=16)
    created_at: str
    default_model: ModelId | None = None

    @field_validator("owner")
    @classmethod
    def safe_owner(cls, value: str) -> str:
        return ClientPolicy.safe_owner(value)

    @field_validator("tags")
    @classmethod
    def safe_tags(cls, value: list[str]) -> list[str]:
        return ClientPolicy.safe_tags(value)

    @field_validator("created_at")
    @classmethod
    def timestamp(cls, value: str) -> str:
        if credential_expiry(value) is None:
            raise ValueError("Invalid identity timestamp")
        return value


class KeyRecord(_Record):
    id: InstanceName
    client_id: InstanceName
    label: str = Field(min_length=1, max_length=64)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: str
    expires_at: str | None
    revoked: bool
    last_used_at: str | None = None

    @field_validator("created_at")
    @classmethod
    def timestamp(cls, value: str) -> str:
        return UserRecord.timestamp(value)

    @field_validator("expires_at", "last_used_at")
    @classmethod
    def optional_timestamp(cls, value: str | None) -> str | None:
        if value is not None:
            UserRecord.timestamp(value)
        return value


class OperatorRecord(_Record):
    id: InstanceName
    label: str = Field(min_length=1, max_length=64)
    role: Literal["admin", "viewer"]
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: str
    expires_at: str
    revoked: bool

    @field_validator("created_at", "expires_at")
    @classmethod
    def timestamp(cls, value: str) -> str:
        return UserRecord.timestamp(value)


def validate_identity(value: object) -> dict[str, Any]:
    try:
        if type(value) is not dict or set(value) != {"users", "keys", "operators"}:
            raise ValueError
        # Deleted users retain metadata and revoked-key records for attribution.
        users, keys, operators = value["users"], value["keys"], value["operators"]
        if any(type(records) is not dict for records in (users, keys, operators)):
            raise ValueError
        if len(users) > 4096 or len(keys) > 4096 or len(operators) > 64:
            raise ValueError
        digests = []
        for identity, metadata in users.items():
            if (
                type(identity) is not str
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", identity) is None
            ):
                raise ValueError
            UserRecord.model_validate(metadata)
        for identity, metadata in keys.items():
            record = KeyRecord.model_validate(metadata)
            if identity != record.id or record.client_id not in users:
                raise ValueError
            if record.expires_at is None and record.label != "legacy":
                raise ValueError
            digests.append(record.digest)
        for identity, metadata in operators.items():
            operator = OperatorRecord.model_validate(metadata)
            if identity != operator.id or identity == "bootstrap":
                raise ValueError
            digests.append(operator.digest)
        if len(digests) != len(set(digests)):
            raise ValueError
        return value
    except (ValueError, KeyError, TypeError):
        raise StartupError("Stored management identities are invalid") from None
