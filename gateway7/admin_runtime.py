"""Validated operator mutations publish one durable client-policy snapshot."""

import csv
import hashlib
import io
import secrets
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gateway7.auth import AccessControl
from gateway7.client_policies import build_client_pipelines
from gateway7.config import ClientConfig, ClientLimitsConfig, GatewayConfig, InstanceName, ModelId
from gateway7.errors import GatewayError, StartupError
from gateway7.operator_console import operator_state


class ClientPolicy(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    enabled: bool = True
    models: list[ModelId] | None = Field(default=None, max_length=64)
    limits: ClientLimitsConfig = Field(default_factory=ClientLimitsConfig)
    additional_middleware: list[InstanceName] = Field(default_factory=list, max_length=64)

    def client_config(self) -> ClientConfig:
        data = self.model_dump()
        if self.models is None:
            data.pop("models")
        return ClientConfig.model_validate({"token_env": "GATEWAY7_MANAGED_CLIENT", **data})


class CreateClient(ClientPolicy):
    id: InstanceName

    def client_config(self) -> ClientConfig:
        data = self.model_dump(exclude={"id"})
        if self.models is None:
            data.pop("models")
        return ClientConfig.model_validate({"token_env": "GATEWAY7_MANAGED_CLIENT", **data})


class AdminController:
    """No await separates validation, database commit and runtime publication."""

    def __init__(self, state: Any) -> None:
        self.state = state

    def _required(self) -> None:
        if self.state.admin_store is None:
            raise GatewayError("not_found")

    def _client(self, client_id: str) -> ClientConfig:
        self._required()
        client = self.state.config.auth.clients.get(client_id)
        if client is None:
            raise GatewayError("not_found")
        return client

    def _row(self, client_id: str) -> dict[str, Any]:
        snapshot = operator_state(
            self.state.config,
            self.state.pipeline,
            self.state.client_pipelines,
            ready=self.state.ready,
        )
        row = next(row for row in snapshot["clients"] if row["id"] == client_id)
        row["credential_active"] = client_id in self.state.token_digests
        return row

    def _publish(self, clients: dict[str, ClientConfig], digests: dict[str, bytes]) -> None:
        try:
            data = self.state.config.model_dump()
            data["auth"]["clients"] = {
                name: client.model_dump() for name, client in clients.items()
            }
            candidate = GatewayConfig.model_validate(data)
            for client in clients.values():
                additional = client.additional_middleware
                if len(additional) != len(set(additional)) or any(
                    name not in self.state.pipeline.plugins.instances
                    or not candidate.plugins[name].enabled
                    or name in candidate.middleware
                    for name in additional
                ):
                    raise ValueError("Invalid middleware selection")
            access = AccessControl(candidate, token_digests=digests)
            pipelines = build_client_pipelines(
                candidate, self.state.pipeline.plugins, self.state.pipeline
            )
            self.state.admin_store.save_clients(clients, digests)
        except (ValidationError, ValueError, KeyError):
            raise GatewayError("invalid_request") from None
        except StartupError:
            raise GatewayError("unavailable") from None
        self.state.usage_ledger.ensure_clients(clients)
        self.state.admission.update(candidate)
        self.state.config = candidate
        self.state.access = access
        self.state.client_pipelines = pipelines
        self.state.token_digests = digests

    def create(self, payload: CreateClient) -> dict[str, Any]:
        self._required()
        clients = dict(self.state.config.auth.clients)
        if payload.id in clients or len(clients) >= 128:
            raise GatewayError("invalid_request")
        try:
            clients[payload.id] = payload.client_config()
        except ValidationError:
            raise GatewayError("invalid_request") from None
        token = secrets.token_urlsafe(32)
        digests = {**self.state.token_digests, payload.id: hashlib.sha256(token.encode()).digest()}
        self._publish(clients, digests)
        return {"client": self._row(payload.id), "token": token}

    def update(self, client_id: str, payload: ClientPolicy) -> dict[str, Any]:
        previous = self._client(client_id)
        try:
            client = payload.client_config().model_copy(update={"token_env": previous.token_env})
        except ValidationError:
            raise GatewayError("invalid_request") from None
        self._publish(
            {**self.state.config.auth.clients, client_id: client}, dict(self.state.token_digests)
        )
        return {"client": self._row(client_id)}

    def rotate(self, client_id: str) -> dict[str, str]:
        self._client(client_id)
        token = secrets.token_urlsafe(32)
        self._publish(
            dict(self.state.config.auth.clients),
            {**self.state.token_digests, client_id: hashlib.sha256(token.encode()).digest()},
        )
        return {"token": token}

    def revoke(self, client_id: str) -> None:
        self._client(client_id)
        digests = dict(self.state.token_digests)
        digests.pop(client_id, None)
        self._publish(dict(self.state.config.auth.clients), digests)

    def delete(self, client_id: str) -> None:
        self._client(client_id)
        clients, digests = dict(self.state.config.auth.clients), dict(self.state.token_digests)
        del clients[client_id]
        digests.pop(client_id, None)
        self._publish(clients, digests)


def usage_csv(snapshot: dict[str, Any]) -> str:
    """Escape spreadsheet formulas as well as ordinary CSV delimiters."""
    stream = io.StringIO(newline="")
    rows = snapshot.get("rows", [])
    fields = [
        "day",
        "client_id",
        "model",
        "provider_attempts",
        "complete",
        "provider_error",
        "cancelled",
        "known_input_tokens",
        "known_output_tokens",
        "input_usage_unknown_attempts",
        "output_usage_unknown_attempts",
    ]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        result = {**row, **row.get("outcomes", {})}
        writer.writerow(
            {
                field: "'" + value
                if isinstance(value := result.get(field, ""), str)
                and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
                else value
                for field in fields
            }
        )
    return stream.getvalue()
