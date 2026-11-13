"""Browser security with test-only origins; no Cloudflare Worker or external I/O."""
import json

import httpx
import pytest
from pydantic import ValidationError
from starlette.middleware.cors import CORSMiddleware

from backend.api import auth, dependencies
from backend.core.config import Settings
from backend.core.csrf import OriginCSRFMiddleware
from backend.database.queries import add_user
from backend.main import app

LOCAL = "http://localhost:5173"
BROWSER = "https://browser.test"  # Reserved test domain, not production configuration.
LOGOUT = "/auth/Text-to-Masterpiece/logout"


@pytest.mark.parametrize("value,expected", [
    ("", []), ("[]", []),
    (json.dumps([LOCAL, BROWSER]), [LOCAL, BROWSER]),
    (json.dumps([LOCAL, LOCAL]), [LOCAL]),
    ('["https://[::1]:8443"]', ["https://[::1]:8443"]),
])
def test_origin_configuration(monkeypatch, value, expected):
    monkeypatch.setenv("CORS_ORIGINS", value)
    assert Settings(_env_file=None).CORS_ORIGINS == expected


def test_origin_default_is_closed(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS")
    assert Settings(_env_file=None).CORS_ORIGINS == []


@pytest.mark.parametrize("value", [
    "*", '"https://browser.test"', "http://localhost:5173", "null", "{}",
    '["*"]', '["null"]', '["https://*.test"]', '["ftp://browser.test"]',
    '["https://browser.test/"]', '["https://browser.test/path"]',
    '["https://browser.test?x=1"]', '["https://browser.test#x"]',
    '["https://user:password@browser.test"]', '[" https://browser.test"]',
    '["https://browser.test:99999"]', '["https://browser.test\\\\evil.test"]',
    '["https://BROWSER.test"]', '["https://browser.test:443"]',
    '["https://browser.test\\n"]', '[1]', '[null]',
])
def test_invalid_origin_configuration(monkeypatch, value):
    monkeypatch.setenv("CORS_ORIGINS", value)
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(_env_file=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [LOCAL, BROWSER])
async def test_credentialed_cors_and_local_frontend(client, origin):
    response = await client.options(LOGOUT, headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "origin" in response.headers["vary"].lower()
    response = await client.post(LOGOUT, headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["https://evil.test", "null", "https://browser.test.evil.test", BROWSER + "/"])
async def test_untrusted_origin_cannot_post_even_without_preflight(client, origin):
    preflight = await client.options(LOGOUT, headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
    })
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers
    # Simple form requests do not need preflight; CORS alone cannot stop CSRF.
    response = await client.post(LOGOUT, headers={"Origin": origin}, data={"x": "y"})
    assert response.status_code == 403
    assert "set-cookie" not in response.headers  # Handler did not clear cookies.
    assert "access-control-allow-origin" not in response.headers
    get_response = await client.get("/Text-to-Masterpiece/about_me", headers={"Origin": origin})
    assert "access-control-allow-origin" not in get_response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    LOGOUT, "/auth/Text-to-Masterpiece/token", "/auth/Text-to-Masterpiece/registrate",
    "/Text-to-Masterpiece/generate",
])
async def test_csrf_rejects_before_auth_body_validation_or_generation(client, path):
    response = await client.post(path, headers={"Origin": "https://evil.test"})
    assert response.status_code == 403
    assert response.json() == {"detail": "Untrusted request origin."}


@pytest.mark.asyncio
async def test_forwarded_headers_and_host_are_not_origin_authority(client):
    response = await client.post(LOGOUT, headers={
        "Origin": "https://evil.test", "Host": "evil.test",
        "X-Forwarded-Host": "browser.test", "X-Forwarded-Proto": "https",
        "Forwarded": 'host="browser.test";proto=https',
    })
    assert response.status_code == 403
    response = await client.post(LOGOUT, headers={
        "Origin": BROWSER, "Host": "internal.test",
        "X-Forwarded-Host": "evil.test", "X-Forwarded-Proto": "http",
    })
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_origins_are_rejected(client):
    response = await client.post(LOGOUT, headers=[("Origin", BROWSER), ("Origin", "https://evil.test")])
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_no_origin_policy(client):
    # Existing non-browser clients remain supported, including cookie sessions.
    client.cookies.set("access_token", "test-cookie")
    assert (await client.post(LOGOUT)).status_code == 200
    assert (await client.post(LOGOUT, headers={"Sec-Fetch-Site": "same-origin"})).status_code == 200
    response = await client.post(LOGOUT, headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_empty_allowlist_does_not_auto_trust_same_host_or_forwarded_headers():
    async def endpoint(scope, receive, send):
        from starlette.responses import JSONResponse
        await JSONResponse({"ok": True})(scope, receive, send)

    closed = CORSMiddleware(
        OriginCSRFMiddleware(endpoint, allowed_origins=[]),
        allow_origins=[], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=closed), base_url=BROWSER) as browser:
        response = await browser.post("/", headers={"Origin": BROWSER})
        assert response.status_code == 403
        assert "access-control-allow-origin" not in response.headers
        response = await browser.options("/", headers={
            "Origin": BROWSER, "Access-Control-Request-Method": "POST",
        })
        assert response.status_code == 400
        assert (await browser.post("/")).status_code == 200  # Explicit compatibility policy.


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["token", "registrate"])
async def test_https_proxy_guest_to_user_login_logout_and_cookie_paths(client, db, monkeypatch, action):
    # Simulate only the ASGI scope at the Render hop: public URL /api/*,
    # internal HTTP + different Host. No trust in forwarded headers is needed.
    async def render_hop(scope, receive, send):
        internal = dict(scope)
        internal["scheme"] = "http"
        internal["server"] = ("render.internal", 80)
        internal["headers"] = [(k, v) for k, v in scope["headers"] if k != b"host"] + [(b"host", b"render.internal")]
        await app(internal, receive, send)

    monkeypatch.setattr(auth, "COOKIE_SECURE", True)
    monkeypatch.setattr(auth, "COOKIE_SAMESITE", "lax")
    monkeypatch.setattr(dependencies, "COOKIE_SECURE", True)
    monkeypatch.setattr(dependencies, "COOKIE_SAMESITE", "lax")
    if action == "token":
        await add_user("proxy@example.com", "Password123!", db)
        await db.commit()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=render_hop, root_path="/api"),
        base_url=BROWSER, headers={"Origin": BROWSER, "Sec-Fetch-Site": "same-origin"},
    ) as browser:
        guest = await browser.get("/api/Text-to-Masterpiece")
        assert guest.status_code == 200
        guest_cookie = guest.headers["set-cookie"].lower()
        assert "httponly" in guest_cookie and "secure" in guest_cookie
        assert "samesite=lax" in guest_cookie and "path=/" in guest_cookie
        assert "domain=" not in guest_cookie
        assert browser.cookies.get("guest_id")
        if action == "token":
            response = await browser.post("/api/auth/Text-to-Masterpiece/token", data={
                "username": "proxy@example.com", "password": "Password123!",
            })
        else:
            response = await browser.post("/api/auth/Text-to-Masterpiece/registrate", json={
                "email": "proxy@example.com", "password": "Password123!",
            })
        assert response.status_code == 200, response.text
        cookies = response.headers.get_list("set-cookie")
        assert len(cookies) == 2  # User session + removal of guest cookie.
        for cookie in cookies:
            lowered = cookie.lower()
            assert "httponly" in lowered and "secure" in lowered
            assert "samesite=lax" in lowered and "path=/" in lowered
            assert "domain=" not in lowered
        assert browser.cookies.get("access_token") and not browser.cookies.get("guest_id")
        me = await browser.get("/api/auth/Text-to-Masterpiece/users/me")
        assert me.status_code == 200
        assert me.json()["email"] == "proxy@example.com"
        # A disallowed Origin must not log the current user out.
        rejected = await browser.post("/api" + LOGOUT, headers={"Origin": "https://evil.test"})
        assert rejected.status_code == 403
        assert browser.cookies.get("access_token")
        response = await browser.post("/api" + LOGOUT)
        assert response.status_code == 200
        assert len(response.headers.get_list("set-cookie")) == 2
        assert not browser.cookies.get("access_token") and not browser.cookies.get("guest_id")
        assert (await browser.get("/api/auth/Text-to-Masterpiece/users/me")).status_code == 401
