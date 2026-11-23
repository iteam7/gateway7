"""Optional real-browser journeys for the operator workspace.

With system Chromium installed:
    uv run --with playwright pytest -q tests/test_operator_workspace_browser.py
Only synthetic accounts, messages and credentials are used.
"""

import shutil
import socket
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
import uvicorn

from gateway7.analytics import Analytics
from gateway7.app import create_app
from gateway7.config import GatewayConfig
from gateway7.models import ChatResponse
from gateway7.telemetry import Telemetry

PASSWORD = "Synthetic-workspace-password-335"
RECOVERY = "synthetic-workspace-recovery-credential"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if not chromium:
        pytest.skip("Chromium is not installed")
    monkeypatch.setenv("WORKSPACE_OPERATOR", RECOVERY)
    monkeypatch.setenv("FAKE_LLM_API_KEY", "synthetic-workspace-provider-credential")
    calls = []

    class Provider:
        async def complete(self, request, **options):
            calls.append(request)
            return ChatResponse(
                text="Synthetic SECRET answer.", usage={"input_tokens": 7, "output_tokens": 5}
            )

        async def aclose(self):
            pass

    monkeypatch.setattr("gateway7.app.build_provider", lambda *_: Provider())
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": "fake", "model": "fake"},
            "auth": {
                "enabled": True,
                "operator_token_env": "WORKSPACE_OPERATOR",
                "management_db": str(tmp_path / "workspace.db"),
                "session_cookie_secure": False,
                "clients": {},
            },
        }
    )
    app = create_app(config=config, telemetry=Telemetry.disabled(), analytics=Analytics.disabled())
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        base = f"http://127.0.0.1:{listener.getsockname()[1]}"
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started
            with (
                httpx.Client(base_url=base, trust_env=False) as api,
                playwright.sync_playwright() as engine,
            ):
                browser = engine.chromium.launch(executable_path=chromium, args=["--no-sandbox"])
                try:
                    context = browser.new_context(viewport={"width": 1440, "height": 1000})
                    page = context.new_page()
                    page.on("dialog", lambda dialog: dialog.accept())
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    yield SimpleNamespace(
                        base=base,
                        api=api,
                        page=page,
                        context=context,
                        expect=playwright.expect,
                        calls=calls,
                        errors=errors,
                    )
                finally:
                    browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()


def account(workspace, username="workspace_admin", role="admin"):
    headers = {"Authorization": "Bearer " + RECOVERY, "X-Gateway7-Operator": "true"}
    revision = workspace.api.get("/operator/state", headers=headers).json()["revision"]
    response = workspace.api.post(
        "/operator/accounts",
        headers={**headers, "If-Match": str(revision)},
        json={"id": username, "label": username, "role": role, "password": PASSWORD},
    )
    assert response.status_code == 201


def login(workspace, username="workspace_admin", password=PASSWORD, remember=False):
    page = workspace.page
    page.locator("#login-username").fill(username)
    page.locator("#login-password").fill(password)
    page.locator("#login-remember").set_checked(remember)
    page.locator("#sign-in").click()
    workspace.expect(page.locator("#dashboard")).to_be_visible()
    workspace.expect(page.locator("#refresh")).to_be_enabled()


def test_password_policy_and_user_journey(workspace):
    page, expect = workspace.page, workspace.expect
    page.goto(workspace.base + "/operator/console#operators")
    # The recovery path can create the first ordinary password account.
    page.locator("#show-token-login").click()
    page.locator("#operator-token").fill(RECOVERY)
    page.locator("#connect").click()
    expect(page.locator("#operator-management")).to_be_visible()
    expect(page.locator("#refresh")).to_be_enabled()
    page.locator("#new-operator-id").fill("workspace_admin")
    page.locator("#new-operator-label").fill("Workspace administrator")
    page.locator("#new-operator-role").select_option("admin")
    page.locator("#new-operator-password").fill(PASSWORD)
    with page.expect_response(
        lambda response: response.url.endswith("/operator/accounts")
    ) as created:
        page.locator("#create-operator").click()
    assert created.value.status == 201
    expect(
        page.get_by_role("cell", name="Workspace administrator (workspace_admin)", exact=True)
    ).to_be_visible()
    assert page.locator("#new-operator-password").input_value() == ""
    page.locator("#disconnect").click()
    login(workspace, remember=True)
    cookies = workspace.context.cookies()
    assert cookies and all(cookie["httpOnly"] for cookie in cookies)
    assert all(cookie["expires"] > time.time() for cookie in cookies)
    page.reload()
    expect(page.locator("#operator-identity")).to_contain_text("workspace_admin")
    expect(page.locator("#refresh")).to_be_enabled()
    assert page.evaluate("() => localStorage.length + sessionStorage.length") == 0
    for label in [
        "Overview",
        "Users & keys",
        "Models",
        "Policies",
        "Usage",
        "Budgets & pricing",
        "Operators",
        "Activity",
    ]:
        page.get_by_role("link", name=label, exact=True).first.click()
        assert page.locator(".workspace-view:visible").count() == 1
        expect(page.get_by_role("link", name=label, exact=True).first).to_have_attribute(
            "aria-current", "page"
        )
    page.get_by_role("link", name="Users & keys", exact=True).first.click()
    page.locator("#create-client").click()
    page.locator("#client-id").fill("demo_user")
    page.locator("#client-owner").fill("Example team")
    page.locator("#save-client").click()
    expect(page.locator("#issued-token-panel")).to_be_visible()
    client_token = page.locator("#issued-token").input_value()
    page.locator("#dismiss-token").click()
    expect(page.locator("#refresh")).to_be_enabled()
    page.get_by_role("link", name="Policies", exact=True).first.click()
    page.locator("#policy-id").fill("guard_demo")
    page.locator("#policy-label").fill("Block test terms")
    page.locator("#policy-terms").fill("BLOCKME")
    page.locator("#policy-sample").fill("A synthetic BLOCKME sample.")
    with page.expect_response(lambda response: response.url.endswith("/policy-preview")) as preview:
        page.locator("#preview-policy").click()
    assert preview.value.json()["provider_calls"] == 0
    expect(page.locator("#policy-preview-output")).to_contain_text("Blocked")
    assert not workspace.calls
    page.locator("#save-policy").click()
    expect(
        page.get_by_role("cell", name="Block test terms (guard_demo)", exact=True)
    ).to_be_visible()
    page.locator("#policy-assignment-choice").select_option("guard_demo")
    page.locator("#add-policy-assignment").click()
    page.locator("#save-policy-assignments").click()
    expect(page.locator("#save-policy-assignments")).to_be_enabled()
    expect(page.locator("#policy-assignment-order")).to_contain_text("Block test terms")
    response = workspace.api.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer " + client_token},
        json={"model": "fake", "messages": [{"role": "user", "content": "BLOCKME"}]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "policy_denied"
    assert not workspace.calls
    response = workspace.api.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer " + client_token},
        json={"model": "fake", "messages": [{"role": "user", "content": "Allowed synthetic text"}]},
    )
    assert response.status_code == 200
    assert len(workspace.calls) == 1
    # A response policy can be scoped to one user after the shared guard.
    page.get_by_role("button", name="New policy", exact=True).click()
    page.locator("#policy-id").fill("redact_response")
    page.locator("#policy-label").fill("Remove test secrets")
    page.locator("#policy-template").select_option("literal_redact")
    page.locator("#policy-phase").select_option("response")
    page.locator("#policy-terms").fill("SECRET")
    page.locator("#policy-replacement").fill("[REMOVED]")
    page.locator("#save-policy").click()
    expect(
        page.get_by_role("cell", name="Remove test secrets (redact_response)", exact=True)
    ).to_be_visible()
    expect(page.locator("#refresh")).to_be_enabled()
    page.locator("#policy-assignment-target").select_option("client")
    page.locator("#policy-assignment-user").fill("demo_user")
    page.locator("#policy-assignment-user").press("Tab")
    page.locator("#policy-assignment-choice").select_option("redact_response")
    page.locator("#add-policy-assignment").click()
    assert page.locator("#policy-assignment-user").input_value() == "demo_user"
    assert page.locator("#policy-assignment-user").evaluate("el => el.form.checkValidity()"), (
        page.locator("#policy-assignment-user").evaluate(
            "el => [...el.form.elements].filter(x => !x.validity.valid).map(x => ({id:x.id, value:x.value, required:x.required, disabled:x.disabled}))"
        )
    )
    with page.expect_response(
        lambda response: response.url.endswith("/policy-assignments")
    ) as assignment:
        page.locator("#save-policy-assignments").click()
    assert assignment.value.status == 200
    assert assignment.value.json()["clients"]["demo_user"] == ["redact_response"]
    expect(page.locator("#save-policy-assignments")).to_be_enabled()
    response = workspace.api.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer " + client_token},
        json={"model": "fake", "messages": [{"role": "user", "content": "Allowed synthetic text"}]},
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Synthetic [REMOVED] answer."
    # Editing and deleting an unassigned template do not require server changes.
    page.get_by_role("row").filter(has_text="(redact_response)").get_by_role(
        "button", name="Edit", exact=True
    ).click()
    page.locator("#policy-label").fill("Redact response secrets")
    page.locator("#save-policy").click()
    expect(
        page.get_by_role("cell", name="Redact response secrets (redact_response)", exact=True)
    ).to_be_visible()
    page.get_by_role("button", name="New policy", exact=True).click()
    page.locator("#policy-id").fill("email_demo")
    page.locator("#policy-label").fill("Mask sample email")
    page.locator("#policy-template").select_option("email_mask")
    expect(page.locator("#policy-replacement")).to_have_value("[EMAIL]")
    page.locator("#save-policy").click()
    email_row = page.get_by_role("row").filter(has_text="(email_demo)")
    expect(email_row).to_be_visible()
    email_row.get_by_role("button", name="Delete", exact=True).click()
    expect(email_row).to_have_count(0)
    expect(page.locator("#refresh")).to_be_enabled()
    page.set_viewport_size({"width": 390, "height": 844})
    mobile_policy = page.locator(".policy-list tbody tr").filter(has_text="(redact_response)")
    expect(mobile_policy.get_by_role("button", name="Edit", exact=True)).to_be_visible()
    mobile_policy.get_by_role("button", name="Edit", exact=True).click()
    expect(page.locator("#policy-id")).to_have_value("redact_response")
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    page.set_viewport_size({"width": 1440, "height": 1000})
    # Resetting this account ends its cookie session and directs it to sign in.
    page.get_by_role("link", name="Operators", exact=True).click()
    page.get_by_role("row").filter(has_text="(workspace_admin)").get_by_role(
        "button", name="Reset password"
    ).click()
    page.locator("#reset-operator-password").fill("Changed-synthetic-password-335")
    page.get_by_role("button", name="Save password", exact=True).click()
    expect(page.locator("#connection-panel")).to_be_visible()
    expect(page.locator("#message")).to_contain_text("Password changed")
    login(workspace, password="Changed-synthetic-password-335")
    page.locator("#disconnect").click()
    page.reload()
    expect(page.locator("#connection-panel")).to_be_visible()
    assert page.locator("#dashboard").is_hidden()
    assert not workspace.errors


def test_mobile_viewer_navigation_and_session_logout(workspace):
    account(workspace, "workspace_viewer", "viewer")
    page, expect = workspace.page, workspace.expect
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(workspace.base + "/operator/console")
    login(workspace, "workspace_viewer")
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    page.locator("#toggle-navigation").click()
    expect(page.locator("#toggle-navigation")).to_have_attribute("aria-expanded", "true")
    page.get_by_role("link", name="Policies", exact=True).first.click()
    expect(page.locator("#toggle-navigation")).to_have_attribute("aria-expanded", "false")
    expect(page.locator("#policy-management")).to_be_visible()
    assert page.locator("#save-policy").is_hidden()
    assert page.locator("#preview-policy").is_hidden()
    page.locator("#toggle-navigation").click()
    page.keyboard.press("Escape")
    expect(page.locator("#toggle-navigation")).to_have_attribute("aria-expanded", "false")
    page.locator("#toggle-navigation").click()
    page.get_by_role("button", name="Close navigation", exact=True).click(
        position={"x": 350, "y": 200}
    )
    expect(page.locator("#toggle-navigation")).to_have_attribute("aria-expanded", "false")
    page.locator("#disconnect").click()
    expect(page.locator("#sign-in")).to_be_enabled()
    page.reload()
    expect(page.locator("#connection-panel")).to_be_visible()
    assert not workspace.errors


def test_pending_password_login_serializes_recovery_mode(workspace):
    account(workspace)
    page, expect = workspace.page, workspace.expect
    page.goto(workspace.base + "/operator/console")
    page.locator("#show-token-login").click()
    page.locator("#operator-token").fill(RECOVERY)
    held = []

    def hold_login(route):
        if route.request.method == "POST":
            held.append((route, route.fetch()))
        else:
            route.continue_()

    page.route("**/operator/session", hold_login)
    page.locator("#login-username").fill("workspace_admin")
    page.locator("#login-password").fill(PASSWORD)
    page.locator("#sign-in").click()
    deadline = time.monotonic() + 10
    while not held and time.monotonic() < deadline:
        page.wait_for_timeout(10)
    assert held
    expect(page.locator("#show-token-login")).to_be_disabled()
    expect(page.locator("#connect")).to_be_disabled()
    # Even an externally dispatched submit cannot start a competing token login.
    page.evaluate("() => document.getElementById('connect-form').requestSubmit()")
    assert page.locator("#dashboard").is_hidden()
    route, response = held[0]
    assert response.status == 200
    route.fulfill(response=response)
    expect(page.locator("#operator-identity")).to_contain_text("workspace_admin")
    expect(page.locator("#refresh")).to_be_enabled()
    page.unroute("**/operator/session", hold_login)
    page.locator("#disconnect").click()
    expect(page.locator("#sign-in")).to_be_enabled()
    page.reload()
    expect(page.locator("#connection-panel")).to_be_visible()
    assert page.locator("#dashboard").is_hidden()
    assert not workspace.errors
