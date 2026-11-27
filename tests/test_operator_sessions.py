"""Password sessions keep browser credentials private and revocation immediate."""

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import secrets
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


async def test_cancelled_logout_publishes_revocation_before_pending_cookie_mutation(
    browser, monkeypatch
):
    app, client = browser
    await account(client)
    csrf = (await login(client)).json()["csrf_token"]
    raw_cookie = client.cookies.get(COOKIE_NAME)
    cookie_headers = [(b"cookie", (COOKIE_NAME + "=" + raw_cookie).encode())]
    original_call = app.state.db.call
    original_delete = app.state.admin_store.delete_operator_session
    read_ready, release_read = asyncio.Event(), asyncio.Event()
    deleted, release_delete = threading.Event(), threading.Event()

    async def delayed(operation, *args, **kwargs):
        result = await original_call(operation, *args, **kwargs)
        if (
            operation.__name__ == "get_operator_session"
            and asyncio.current_task().get_name() == "gateway7-owned-management-mutation"
            and not read_ready.is_set()
        ):
            read_ready.set()
            await release_read.wait()
        return result

    def delete(*args):
        original_delete(*args)
        deleted.set()
        assert release_delete.wait(5)

    monkeypatch.setattr(app.state.db, "call", delayed)
    monkeypatch.setattr(app.state.admin_store, "delete_operator_session", delete)
    revision = app.state.control["revision"]
    pending = asyncio.create_task(
        client.post(
            "/operator/clients",
            json={"id": "after_logout"},
            headers={**MARKER, "X-Gateway7-CSRF": csrf, "If-Match": str(revision)},
        )
    )
    try:
        await asyncio.wait_for(read_ready.wait(), 3)
        logout = asyncio.create_task(app.state.operator_sessions.logout(cookie_headers))
        assert await asyncio.to_thread(deleted.wait, 3)
        logout.cancel("synthetic logout cancellation")
        release_delete.set()
        with pytest.raises(asyncio.CancelledError):
            await logout
    finally:
        release_delete.set()
        release_read.set()
        result = await asyncio.wait_for(pending, 3)
    assert result.status_code == 401, result.text
    digest = hashlib.sha256(raw_cookie.encode()).hexdigest()
    assert await original_call(app.state.admin_store.get_operator_session, digest) is None
    with pytest.raises(GatewayError):
        app.state.operator_sessions.authenticate_cached(cookie_headers)
    users = await client.get("/operator/clients", headers=RECOVERY)
    assert "after_logout" not in {item["id"] for item in users.json()["items"]}


@pytest.mark.parametrize("action", ["login", "logout"])
@pytest.mark.parametrize("stage", ["lookup", "mutation"])
async def test_unrelated_session_change_preserves_valid_inflight_actor(
    browser, monkeypatch, action, stage
):
    app, client = browser
    await account(client, "alice")
    await account(client, "bob")
    alice_csrf = (await login(client, "alice")).json()["csrf_token"]
    alice_cookie = client.cookies.get(COOKIE_NAME)
    bob_csrf = (await login(client, "bob")).json()["csrf_token"]
    bob_cookie = client.cookies.get(COOKIE_NAME)
    entered, release = asyncio.Event(), asyncio.Event()
    original_call = app.state.db.call
    original_hash = app.state.operator_sessions.passwords.hash

    async def delayed_lookup(operation, *args, **kwargs):
        result = await original_call(operation, *args, **kwargs)
        if (
            stage == "lookup"
            and operation.__name__ == "get_operator_session"
            and asyncio.current_task().get_name() == "unrelated-bob-lookup"
            and not entered.is_set()
        ):
            entered.set()
            await release.wait()
        return result

    async def delayed_hash(password):
        encoded = await original_hash(password)
        if stage == "mutation":
            entered.set()
            await release.wait()
        return encoded

    monkeypatch.setattr(app.state.db, "call", delayed_lookup)
    monkeypatch.setattr(app.state.operator_sessions.passwords, "hash", delayed_hash)
    bob_headers = {"Cookie": COOKIE_NAME + "=" + bob_cookie}
    if stage == "lookup":
        pending = asyncio.create_task(
            client.get("/operator/session", headers=bob_headers), name="unrelated-bob-lookup"
        )
    else:
        pending = asyncio.create_task(
            client.post(
                "/operator/accounts",
                json={
                    "id": "bobs_account",
                    "label": "Bob's account",
                    "role": "viewer",
                    "password": PASSWORD,
                },
                headers={
                    **bob_headers,
                    **MARKER,
                    "X-Gateway7-CSRF": bob_csrf,
                    "If-Match": str(app.state.control["revision"]),
                },
            )
        )
    try:
        await asyncio.wait_for(entered.wait(), 3)
        if action == "login":
            changed = await client.post(
                "/operator/session",
                json={"username": "alice", "password": PASSWORD},
                headers=MARKER,
            )
        else:
            changed = await client.delete(
                "/operator/session",
                headers={
                    **MARKER,
                    "Cookie": COOKIE_NAME + "=" + alice_cookie,
                    "X-Gateway7-CSRF": alice_csrf,
                },
            )
        assert changed.status_code in (200, 204), changed.text
    finally:
        release.set()
        result = await asyncio.wait_for(pending, 3)
    assert result.status_code == (200 if stage == "lookup" else 201), result.text
    current = await client.get("/operator/session", headers=bob_headers)
    assert current.status_code == 200, current.text
    assert current.json()["actor"]["id"] == "bob"


@pytest.mark.parametrize("cancelled", [False, True], ids=["completed", "cancelled"])
async def test_login_eviction_invalidates_only_removed_sessions_even_if_caller_cancels(
    browser, monkeypatch, cancelled
):
    from gateway7.operator_sessions import SessionLogin

    app, client = browser
    await account(client, "alice")
    await account(client, "bob")
    await login(client, "alice")
    alice_cookie = client.cookies.get(COOKIE_NAME)
    await login(client, "bob")
    bob_cookie = client.cookies.get(COOKIE_NAME)
    manager, store = app.state.operator_sessions, app.state.admin_store
    alice_digest = hashlib.sha256(alice_cookie.encode()).hexdigest()
    alice_session = await app.state.db.call(store.get_operator_session, alice_digest)
    created = datetime.fromisoformat(alice_session["created_at"])
    # Fill Alice's documented 16-session allowance without bypassing the real
    # store's eviction path or spending 15 extra password verifications.
    for index in range(15):
        digest = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()
        session = {
            **alice_session,
            "created_at": (created + timedelta(microseconds=index + 1)).isoformat(),
        }
        removed = await app.state.db.call(store.create_operator_session, digest, session)
        assert removed == []
        manager._remember(digest, session)
    committed, release = threading.Event(), threading.Event()
    original = store.create_operator_session
    evicted = []

    def delayed(*args):
        removed = original(*args)
        evicted.extend(removed)
        committed.set()
        assert release.wait(5)
        return removed

    monkeypatch.setattr(store, "create_operator_session", delayed)
    pending = asyncio.create_task(
        manager.login(SessionLogin(username="alice", password=PASSWORD), "127.0.0.1")
    )
    try:
        assert await asyncio.to_thread(committed.wait, 3)
        if cancelled:
            pending.cancel("synthetic login cancellation")
    finally:
        release.set()
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await pending
    else:
        await pending
    assert evicted == [alice_digest]
    assert await app.state.db.call(store.get_operator_session, alice_digest) is None
    with pytest.raises(GatewayError):
        manager.authenticate_cached([(b"cookie", (COOKIE_NAME + "=" + alice_cookie).encode())])
    assert (
        manager.authenticate_cached([(b"cookie", (COOKIE_NAME + "=" + bob_cookie).encode())]).id
        == "bob"
    )
    count = await app.state.db.call(
        lambda: store._control_query(
            "SELECT COUNT(*) FROM {prefix}operator_sessions WHERE operator_id=?", ("alice",)
        ).fetchone()[0]
    )
    assert count == 16


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


async def test_cancelled_shutdown_drains_password_worker_and_closes_management_resources(
    managed_config,
):
    app = create_app(config=managed_config)
    context = app.router.lifespan_context(app)
    await context.__aenter__()
    worker = app.state.operator_sessions.passwords
    entered, release = threading.Event(), threading.Event()

    def blocking():
        entered.set()
        assert release.wait(5)

    pending = asyncio.create_task(worker._call(blocking))
    shutdown = None
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        shutdown = asyncio.create_task(context.__aexit__(None, None, None))
        async with asyncio.timeout(3):
            while not worker._closed:
                await asyncio.sleep(0)
        shutdown.cancel("synthetic shutdown cancellation")
        await asyncio.sleep(0)
        shutdown.cancel("repeated shutdown cancellation")
        release.set()
        with pytest.raises(asyncio.CancelledError) as failure:
            await shutdown
        assert failure.value.args == ("synthetic shutdown cancellation",)
        await pending
        assert app.state.operator_sessions is None
        assert app.state.admin_store is None
        assert app.state.db._closed
        assert app.state.db.pending == 0
        # A fresh process can immediately reacquire the same management store.
        restarted = create_app(config=managed_config)
        async with restarted.router.lifespan_context(restarted):
            assert restarted.state.ready
    finally:
        release.set()
        await asyncio.gather(pending, return_exceptions=True)
        if shutdown is not None:
            await asyncio.gather(shutdown, return_exceptions=True)
        if app.state.admin_store is not None:
            await app.state.db.call(app.state.admin_store.close)
            app.state.admin_store = None
        await app.state.db.close()


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
