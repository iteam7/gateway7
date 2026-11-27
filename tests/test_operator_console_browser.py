"""Optional Chromium regression for operator credential handoff.

Run with Playwright installed and Chromium on PATH; neither is a runtime dependency.
Optional command: uv run --with playwright pytest -q tests/test_operator_console_browser.py
The browser talks to a real local gateway using only synthetic credentials.
"""

import shutil
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from gateway7.analytics import Analytics
from gateway7.app import create_app
from gateway7.config import GatewayConfig
from gateway7.telemetry import Telemetry


@pytest.mark.parametrize("handoff", ["normal", "before-response", "failed", "logout"])
def test_operator_rotation_keeps_replacement_visible_and_session_current(
    tmp_path, monkeypatch, handoff
):
    playwright = pytest.importorskip("playwright.sync_api")
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium is not installed")
    bootstrap = "synthetic-browser-bootstrap-credential"
    monkeypatch.setenv("CONSOLE_BROWSER_OPERATOR", bootstrap)
    monkeypatch.setenv("FAKE_LLM_API_KEY", "synthetic-browser-provider-credential")
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": "fake", "model": "fake"},
            "auth": {
                "enabled": True,
                "operator_token_env": "CONSOLE_BROWSER_OPERATOR",
                "management_db": str(tmp_path / "admin.db"),
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
            assert server.started, "Synthetic gateway did not start"
            with httpx.Client(base_url=base, trust_env=False) as api:

                def headers(token):
                    return {"Authorization": f"Bearer {token}"}

                def operator(operator_id):
                    revision = api.get("/operator/state", headers=headers(bootstrap)).json()[
                        "revision"
                    ]
                    response = api.post(
                        "/operator/operators",
                        headers={
                            **headers(bootstrap),
                            "X-Gateway7-Operator": "true",
                            "If-Match": str(revision),
                        },
                        json={"id": operator_id, "label": operator_id, "role": "admin"},
                    )
                    assert response.status_code == 201
                    return response.json()["token"]

                current = operator("browser_current")
                other = operator("browser_other")
                with playwright.sync_playwright() as engine:
                    browser = engine.chromium.launch(
                        executable_path=chromium, args=["--no-sandbox"]
                    )
                    try:
                        context = browser.new_context(
                            permissions=["clipboard-read", "clipboard-write"]
                        )
                        page = context.new_page()
                        page.on("dialog", lambda dialog: dialog.accept())
                        page.goto(base + "/operator/console#operators")
                        page.locator("#show-token-login").click()
                        page.locator("#operator-token").fill(current)
                        page.locator("#connect").click()
                        identity = page.locator("#operator-identity")
                        playwright.expect(identity).to_contain_text("browser_current")

                        def rotate(operator_id):
                            row = page.get_by_role("row").filter(has_text=f"({operator_id})")
                            with page.expect_response(
                                lambda response: (
                                    response.url.endswith(f"/operators/{operator_id}/token")
                                    and response.request.method == "POST"
                                )
                            ) as response:
                                row.get_by_role("button", name="Rotate operator token").click()
                            assert response.value.status == 200
                            replacement = response.value.json()["token"]
                            playwright.expect(page.locator("#refresh")).to_be_enabled()
                            playwright.expect(page.locator("#dashboard")).to_be_visible()
                            playwright.expect(page.locator("#issued-token-panel")).to_be_visible()
                            assert page.locator("#issued-token").input_value() == replacement
                            return replacement

                        # Rotating someone else must leave the signed-in credential intact.
                        replacement_other = rotate("browser_other")
                        assert api.get("/operator/state", headers=headers(other)).status_code == 401
                        assert (
                            api.get(
                                "/operator/state", headers=headers(replacement_other)
                            ).status_code
                            == 200
                        )
                        assert (
                            api.get("/operator/state", headers=headers(current)).status_code == 200
                        )
                        page.locator("#dismiss-token").click()

                        page.get_by_role("link", name="Usage", exact=True).click()

                        # An old, delayed usage failure must neither erase the new
                        # session nor leave the filter controls permanently busy.
                        delayed = []

                        def delay_first_usage(route):
                            if not delayed:
                                delayed.append(route)
                            else:
                                route.continue_()

                        page.route("**/operator/usage?*", delay_first_usage)
                        with page.expect_request(lambda request: "/operator/usage?" in request.url):
                            page.locator("#apply-usage").click()
                        playwright.expect(page.locator("#apply-usage")).to_be_disabled()
                        page.get_by_role("link", name="Operators", exact=True).click()
                        if handoff != "normal":
                            held = []
                            rotation_url = "**/operators/browser_current/token"

                            def hold_rotation(route):
                                # fetch() commits server-side without handing the
                                # one-time response to the browser yet.
                                response = None if handoff == "failed" else route.fetch()
                                held.append((route, response))

                            page.route(rotation_url, hold_rotation)
                            row = page.get_by_role("row").filter(has_text="(browser_current)")
                            row.get_by_role("button", name="Rotate operator token").click()
                            deadline = time.monotonic() + 10
                            while not held and time.monotonic() < deadline:
                                page.wait_for_timeout(10)
                            assert held, "Rotation request was not intercepted"
                            route, response = held[0]
                            if handoff == "before-response":
                                row.get_by_role("button", name="Rotate operator token").click()
                                page.wait_for_timeout(100)
                                assert len(held) == 1, "Duplicate rotation reached the server"
                            if handoff == "logout":
                                assert response.status == 200
                                replacement = response.json()["token"]
                                page.locator("#disconnect").click()
                                page.locator("#operator-token").fill(bootstrap)
                                page.locator("#connect").click()
                                playwright.expect(identity).to_contain_text("bootstrap")
                                route.fulfill(response=response)
                                page.wait_for_timeout(100)
                                playwright.expect(identity).to_contain_text("bootstrap")
                                playwright.expect(
                                    page.locator("#issued-token-panel")
                                ).to_be_hidden()
                                assert page.locator("#issued-token").input_value() == ""
                                assert (
                                    api.get(
                                        "/operator/state", headers=headers(replacement)
                                    ).status_code
                                    == 200
                                )
                                return
                            if handoff == "failed":
                                revision = api.get(
                                    "/operator/state", headers=headers(bootstrap)
                                ).json()["revision"]
                                revoked = api.delete(
                                    "/operator/operators/browser_current",
                                    headers={
                                        **headers(bootstrap),
                                        "X-Gateway7-Operator": "true",
                                        "If-Match": str(revision),
                                    },
                                )
                                assert revoked.status_code == 204
                            else:
                                assert response.status == 200
                                replacement = response.json()["token"]
                            # The competing read reaches the real server only
                            # after rotation/revocation has invalidated its bearer.
                            old_read = delayed[0].fetch()
                            assert old_read.status == 401
                            with page.expect_response(
                                lambda result: (
                                    "/operator/usage?" in result.url and result.status == 401
                                )
                            ):
                                delayed[0].fulfill(response=old_read)
                            page.wait_for_timeout(100)
                            playwright.expect(page.locator("#dashboard")).to_be_visible()
                            if handoff == "failed":
                                response = route.fetch()
                                assert response.status == 401
                                route.fulfill(response=response)
                                playwright.expect(page.locator("#connection-panel")).to_be_visible()
                                playwright.expect(
                                    page.locator("#issued-token-panel")
                                ).to_be_hidden()
                                assert page.locator("#issued-token").input_value() == ""
                                return
                            with page.expect_response(
                                lambda result: result.url.endswith(
                                    "/operators/browser_current/token"
                                )
                            ):
                                route.fulfill(response=response)
                            playwright.expect(page.locator("#refresh")).to_be_enabled()
                            playwright.expect(page.locator("#dashboard")).to_be_visible()
                            playwright.expect(page.locator("#issued-token-panel")).to_be_visible()
                            assert page.locator("#issued-token").input_value() == replacement
                            page.unroute(rotation_url, hold_rotation)
                        else:
                            replacement = rotate("browser_current")
                            delayed[0].fulfill(status=401, json={"error": "old credential"})
                        page.locator("#reveal-token").click()
                        assert page.locator("#issued-token").get_attribute("type") == "text"
                        page.locator("#copy-token").click()
                        playwright.expect(page.locator("#copy-token")).to_have_text("Copied")
                        assert page.evaluate("() => navigator.clipboard.readText()") == replacement
                        page.locator("#dismiss-token").click()
                        page.get_by_role("link", name="Usage", exact=True).click()
                        page.unroute("**/operator/usage?*", delay_first_usage)
                        playwright.expect(page.locator("#apply-usage")).to_be_enabled()
                        playwright.expect(page.locator("#clear-usage")).to_be_enabled()
                        with page.expect_response(
                            lambda response: "/operator/usage?" in response.url
                        ) as usage:
                            page.locator("#apply-usage").click()
                        assert usage.value.status == 200
                        assert (
                            api.get("/operator/state", headers=headers(current)).status_code == 401
                        )
                        assert (
                            api.get("/operator/state", headers=headers(replacement)).status_code
                            == 200
                        )
                        # A later refresh must also use the replacement credential.
                        with page.expect_response(
                            lambda response: response.url.endswith("/operator/state")
                        ) as refreshed:
                            page.locator("#refresh").click()
                        assert refreshed.value.status == 200
                        playwright.expect(page.locator("#refresh")).to_be_enabled()
                        page.locator("#disconnect").click()
                        playwright.expect(page.locator("#issued-token-panel")).to_be_hidden()
                        assert page.locator("#issued-token").input_value() == ""
                        # Ordinary authentication failure still clears a displayed credential.
                        page.locator("#operator-token").fill(replacement)
                        page.locator("#connect").click()
                        playwright.expect(page.locator("#refresh")).to_be_enabled()
                        page.get_by_role("link", name="Operators", exact=True).click()
                        rotate("browser_other")
                        revision = api.get("/operator/state", headers=headers(bootstrap)).json()[
                            "revision"
                        ]
                        revoked = api.delete(
                            "/operator/operators/browser_current",
                            headers={
                                **headers(bootstrap),
                                "X-Gateway7-Operator": "true",
                                "If-Match": str(revision),
                            },
                        )
                        assert revoked.status_code == 204
                        # A background refresh must still clear an open credential dialog.
                        page.evaluate("() => document.getElementById('refresh').click()")
                        playwright.expect(page.locator("#connection-panel")).to_be_visible()
                        playwright.expect(page.locator("#issued-token-panel")).to_be_hidden()
                        assert page.locator("#issued-token").input_value() == ""
                    finally:
                        browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "Synthetic gateway did not stop"
