"""Password sessions keep browser credentials private and revocation immediate."""

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import threading

import httpx
import pytest

from gateway7.app import create_app
from gateway7.config import GatewayConfig
from gateway7.errors import GatewayError, StartupError
from gateway7.operator_sessions import COOKIE_NAME, LoginThrottle, OperatorSessions, PasswordWorker

ROOT = "synthetic-session-recovery-token"
PASSWORD = "synthetic correct password"
MARKER = {"X-Gateway7-Operator": "true"}
RECOVERY = {"Authorization": "Bearer " + ROOT}


def configuration(tmp_path):
    return GatewayConfig.model_validate(
        {
            "auth": {
                "enabled": True,
                "operator_token_env": "SESSION_ROOT",
                "management_db": str(tmp_path / "sessions.sqlite3"),
            }
        }
    )


@pytest.fixture(params=["sqlite", "postgres"])
def managed_config(monkeypatch, tmp_path, request):
    monkeypatch.setenv("SESSION_ROOT", ROOT)
    monkeypatch.setenv("FAKE_LLM_API_KEY", "synthetic-session-provider-token")
    config = configuration(tmp_path)
    if request.param == "postgres":
        dsn = os.environ.get("GATEWAY7_TEST_POSTGRES_DSN")
        if not dsn:
            pytest.skip("Set GATEWAY7_TEST_POSTGRES_DSN to a disposable PostgreSQL database")
        import psycopg

        with psycopg.connect(dsn, autocommit=True) as connection:
            assert connection.info.dbname.startswith(("gateway7_test", "gateway7_task"))
            connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")
        monkeypatch.setenv("SESSION_DATABASE_URL", dsn)
        raw = config.model_dump()
        raw["auth"].pop("management_db")
        raw["auth"]["management_database_url_env"] = "SESSION_DATABASE_URL"
        config = GatewayConfig.model_validate(raw)
    yield config
    if request.param == "postgres":
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")


@pytest.fixture
async def browser(managed_config):
    app = create_app(config=managed_config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://gateway.test"
        ) as client:
            yield app, client


async def change(client, path, body=None, *, method="POST", headers=None):
    auth = RECOVERY if headers is None else headers
    state = await client.get("/operator/state", headers=auth)
    assert state.status_code == 200, state.text
    return await client.request(
        method,
        path,
        json=body,
        headers={**MARKER, **auth, "If-Match": str(state.json()["revision"])},
    )


async def account(client, username="admin", role="admin"):
    response = await change(
        client,
        "/operator/accounts",
        {"id": username, "label": username, "role": role, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    assert response.json()["operator"]["password_configured"]
    assert "token" not in response.json()
    return response.json()


async def login(client, username="admin", remember=False):
    response = await client.post(
        "/operator/session",
        json={"username": username, "password": PASSWORD, "remember": remember},
        headers=MARKER,
    )
    assert response.status_code == 200, response.text
    return response


async def test_cookie_login_csrf_roles_and_secret_storage(browser):
    app, client = browser
    await account(client)
    response = await login(client, remember=True)
    cookie = response.headers["set-cookie"]
    assert all(
        value in cookie
        for value in ("HttpOnly", "SameSite=strict", "Secure", "Path=/operator", "Max-Age=")
    )
    data = response.json()
    expires = datetime.fromisoformat(data["expires_at"])
    assert 604790 <= (expires - datetime.now(timezone.utc)).total_seconds() <= 604800
    csrf = data["csrf_token"]
    assert data["actor"] == {"id": "admin", "role": "admin", "is_bootstrap": False}
    assert (await client.get("/operator/session")).json()["csrf_token"] == csrf
    missing = await change(client, "/operator/clients", {"id": "missing_csrf"}, headers={})
    assert missing.status_code == 403
    created = await change(
        client, "/operator/clients", {"id": "alice"}, headers={"X-Gateway7-CSRF": csrf}
    )
    assert created.status_code == 201, created.text
    assert (await client.get("/v1/models")).status_code == 401
    assert (
        await client.get("/operator/state", headers={"Authorization": "broken"})
    ).status_code == 401
    assert (await client.get("/operator/state", headers=RECOVERY)).status_code == 200
    raw_token = client.cookies.get(COOKIE_NAME)
    snapshot = await app.state.db.call(app.state.admin_store.backup_snapshot)
    serialized = json.dumps(snapshot)
    assert PASSWORD not in serialized and raw_token not in serialized and csrf not in serialized
    stored = await app.state.db.call(
        app.state.admin_store.get_operator_session, hashlib.sha256(raw_token.encode()).hexdigest()
    )
    assert stored["operator_id"] == "admin"
    # Automation bearer rotation does not interrupt the separate password session.
    rotated = await change(
        client,
        "/operator/operators/admin/token",
        {"label": "automation"},
        headers={"X-Gateway7-CSRF": csrf},
    )
    assert rotated.status_code == 200, rotated.text
    assert (await client.get("/operator/session")).status_code == 200


async def test_viewer_can_read_and_logout_but_not_mutate(browser):
    _, client = browser
    await account(client, "viewer", "viewer")
    response = await login(client, "viewer")
    assert "Max-Age=" not in response.headers["set-cookie"]
    ttl = datetime.fromisoformat(response.json()["expires_at"]) - datetime.now(timezone.utc)
    assert 43190 <= ttl.total_seconds() <= 43200
    csrf = response.json()["csrf_token"]
    denied = await change(
        client,
        "/operator/accounts",
        {"id": "escalation", "password": PASSWORD},
        headers={"X-Gateway7-CSRF": csrf},
    )
    assert denied.status_code == 403
    old_cookie = client.cookies.get(COOKIE_NAME)
    assert (await client.delete("/operator/session", headers=MARKER)).status_code == 403
    logout = await client.delete("/operator/session", headers={**MARKER, "X-Gateway7-CSRF": csrf})
    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert (
        await client.get("/operator/session", headers={"Cookie": COOKIE_NAME + "=" + old_cookie})
    ).status_code == 401
    assert (await client.get("/operator/state", headers=RECOVERY)).status_code == 200


@pytest.mark.parametrize("action", ["reset", "revoke", "demote"])
async def test_credential_change_during_body_prevents_cookie_mutation(browser, action):
    _, client = browser
    await account(client)
    csrf = (await login(client)).json()["csrf_token"]
    revision = (await client.get("/operator/state")).json()["revision"]
    entered, release = asyncio.Event(), asyncio.Event()

    async def body():
        entered.set()
        await release.wait()
        yield b'{"id":"stale_actor"}'

    pending = asyncio.create_task(
        client.post(
            "/operator/clients",
            content=body(),
            headers={
                **MARKER,
                "X-Gateway7-CSRF": csrf,
                "If-Match": str(revision),
                "Content-Type": "application/json",
            },
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 3)
        if action == "reset":
            changed = await change(
                client,
                "/operator/accounts/admin/password",
                {"password": "synthetic replacement password"},
                method="PUT",
            )
        elif action == "revoke":
            changed = await change(client, "/operator/operators/admin", method="DELETE")
        else:
            changed = await change(
                client,
                "/operator/operators/admin",
                {"label": "demoted", "role": "viewer"},
                method="PUT",
            )
        assert changed.status_code in (200, 204), changed.text
    finally:
        release.set()
        result = await asyncio.wait_for(pending, 3)
    assert result.status_code in (401, 403), result.text
    users = await client.get("/operator/clients", headers=RECOVERY)
    assert "stale_actor" not in {item["id"] for item in users.json()["items"]}
    assert (await client.get("/operator/session")).status_code == 401


async def test_late_session_lookup_cannot_restore_logged_out_actor(browser, monkeypatch):
    app, client = browser
    await account(client)
    await login(client)
    headers = [(b"cookie", (COOKIE_NAME + "=" + client.cookies.get(COOKIE_NAME)).encode())]
    entered, release = asyncio.Event(), asyncio.Event()
    original = app.state.db.call

    async def delayed(operation, *args, **kwargs):
        result = await original(operation, *args, **kwargs)
        if (
            operation.__name__ == "get_operator_session"
            and asyncio.current_task().get_name() == "late-session"
        ):
            entered.set()
            await release.wait()
        return result

    monkeypatch.setattr(app.state.db, "call", delayed)
    pending = asyncio.create_task(
        app.state.operator_sessions.authenticate(headers), name="late-session"
    )
    try:
        await asyncio.wait_for(entered.wait(), 3)
        await app.state.operator_sessions.logout(headers)
    finally:
        release.set()
    with pytest.raises(GatewayError) as failure:
        await pending
    assert failure.value.code == "unauthorized"
    with pytest.raises(GatewayError):
        app.state.operator_sessions.authenticate_cached(headers)


async def test_remembered_session_survives_process_restart(managed_config):
    config = managed_config
    app = create_app(config=config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://gateway.test"
        ) as client:
            await account(client)
            response = await login(client, remember=True)
            raw = client.cookies.get(COOKIE_NAME)
            csrf = response.json()["csrf_token"]
    restarted = create_app(config=config)
    async with restarted.router.lifespan_context(restarted):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(restarted),
            base_url="https://gateway.test",
            cookies={COOKIE_NAME: raw},
        ) as client:
            response = await client.get("/operator/session")
            assert response.status_code == 200, response.text
            assert response.json()["csrf_token"] == csrf
            logout = await client.delete(
                "/operator/session", headers={**MARKER, "X-Gateway7-CSRF": csrf}
            )
            assert logout.status_code == 204


async def test_login_rejects_cross_origin_and_throttles_generic_failures(browser):
    _, client = browser
    await account(client)
    body = {"username": "admin", "password": "synthetic wrong password"}
    for origin in ("null", "https://other.test"):
        assert (
            await client.post("/operator/session", json=body, headers={**MARKER, "Origin": origin})
        ).status_code == 422
    missing = await client.post("/operator/session", json=body)
    assert missing.status_code == 422
    for _ in range(5):
        response = await client.post("/operator/session", json=body, headers=MARKER)
        assert response.status_code == 401
        assert body["password"] not in response.text
    assert (await client.post("/operator/session", json=body, headers=MARKER)).status_code == 429
    limiter = LoginThrottle()
    for index in range(3000):
        try:
            limiter.check("user" + str(index), "127.0.0.1")
        except GatewayError:
            pass
    assert len(limiter._buckets) <= 2048


async def test_expired_session_cannot_read_or_mutate(browser, monkeypatch):
    import gateway7.operator_sessions as module

    _, client = browser
    await account(client)
    data = (await login(client)).json()
    expires = datetime.fromisoformat(data["expires_at"])

    class Expired(datetime):
        @classmethod
        def now(cls, tz=None):
            return expires + timedelta(seconds=1)

    monkeypatch.setattr(module, "datetime", Expired)
    assert (await client.get("/operator/session")).status_code == 401
    assert (await client.get("/operator/state")).status_code == 401


async def test_session_lookup_failure_after_healthcheck_is_sanitized_unavailable(
    browser, monkeypatch
):
    app, client = browser
    await account(client)
    await login(client)
    assert (await client.get("/ready")).status_code == 200

    def unavailable(digest):
        raise StartupError("synthetic private storage diagnostic")

    monkeypatch.setattr(app.state.admin_store, "get_operator_session", unavailable)
    response = await client.get("/operator/state")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"
    assert "synthetic private storage diagnostic" not in response.text


async def test_cookie_policy_write_enforces_and_restores_without_yaml_edits(browser):
    app, client = browser
    await account(client)
    csrf = (await login(client)).json()["csrf_token"]
    auth = {"X-Gateway7-CSRF": csrf}
    spec = {
        "id": "literal",
        "label": "Literal guard",
        "template": "literal_guard",
        "phase": "request",
        "terms": ["PRIVATE-CONTROL-TEST"],
    }
    preview = await change(
        client,
        "/operator/policy-preview",
        {"spec": spec, "text": "PRIVATE-CONTROL-TEST"},
        headers=auth,
    )
    assert preview.status_code == 200, preview.text
    created = await change(client, "/operator/policies", spec, headers=auth)
    assert created.status_code == 201, created.text
    assigned = await change(
        client,
        "/operator/policy-assignments",
        {"global": ["literal"], "clients": {}},
        method="PUT",
        headers=auth,
    )
    assert assigned.status_code == 200, assigned.text
    created_user = await change(client, "/operator/clients", {"id": "alice"}, headers=auth)
    result = await client.post(
        "/chat",
        json={"messages": [{"role": "user", "content": "PRIVATE-CONTROL-TEST"}]},
        headers={"Authorization": "Bearer " + created_user.json()["token"]},
    )
    assert result.status_code == 403, result.text
    assert result.json()["error"]["code"] == "policy_denied"
    from gateway7.policy_admin import restore_policy_config

    baseline = GatewayConfig.model_validate(
        {**app.state.config.model_dump(), "plugins": {}, "middleware": []}
    )
    restored = restore_policy_config(baseline, app.state.control)
    assert "policy_literal" in restored.middleware


async def test_password_worker_queue_is_bounded_and_running_work_is_drained():
    worker = PasswordWorker(capacity=1)
    entered, release = threading.Event(), threading.Event()

    def blocking():
        entered.set()
        assert release.wait(3)
        return True

    pending = asyncio.create_task(worker._call(blocking))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        with pytest.raises(GatewayError) as failure:
            await worker.hash(PASSWORD)
        assert failure.value.code == "overloaded"
        pending.cancel()
        await asyncio.sleep(0)
        assert not pending.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await worker.close()


@pytest.mark.parametrize(
    "peer,host,accepted",
    [
        ("127.0.0.1", "localhost:8000", True),
        ("::1", "[::1]:8000", True),
        ("172.18.0.1", "localhost", False),
        ("127.0.0.1", "public.example", False),
    ],
)
def test_insecure_cookie_opt_in_requires_actual_loopback_peer_and_host(
    tmp_path, peer, host, accepted
):
    from types import SimpleNamespace

    config = configuration(tmp_path)
    config = GatewayConfig.model_validate(
        {
            **config.model_dump(),
            "auth": {**config.auth.model_dump(), "session_cookie_secure": False},
        }
    )
    manager = OperatorSessions(SimpleNamespace(config=config))
    scope = {
        "type": "http",
        "scheme": "http",
        "path": "/operator/session",
        "client": (peer, 1234),
        "headers": [(b"host", host.encode())],
    }
    try:
        if accepted:
            manager.check_transport(scope)
        else:
            with pytest.raises(GatewayError):
                manager.check_transport(scope)
    finally:
        manager.passwords._pool.shutdown()
