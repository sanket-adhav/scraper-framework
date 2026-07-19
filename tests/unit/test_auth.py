"""Auth tests: login providers, encrypted session store, and the single-re-login
auth middleware (no infinite loops)."""

import httpx
import pytest

from components.auth.form_login import FormLoginProvider
from components.auth.session_store import EncryptedSessionStore
from components.auth.token_login import TokenLoginProvider
from components.middleware.auth import AuthMiddleware
from core.contracts.login_provider import Session, SessionContext
from core.errors.exceptions import AuthError
from core.models import Response, ScrapeRequest
from tests.fake_browser import FakeBrowser, fake_browser_factory

CTX = SessionContext(
    plugin="shop", account="bot", login_url="https://shop.example/login",
    credentials={"username": "bot", "password": "secret"},
)


class TestEncryptedSessionStore:
    def test_round_trip_survives_restart(self, tmp_path):
        key = EncryptedSessionStore.generate_key()
        EncryptedSessionStore(tmp_path, key).put("shop", "bot", Session(cookies={"sid": "abc"}))
        # a brand-new store object = a process restart
        loaded = EncryptedSessionStore(tmp_path, key).get("shop", "bot")
        assert loaded is not None and loaded.cookies == {"sid": "abc"}

    def test_stored_bytes_are_encrypted(self, tmp_path):
        key = EncryptedSessionStore.generate_key()
        store = EncryptedSessionStore(tmp_path, key)
        store.put("shop", "bot", Session(cookies={"sid": "topsecret"}))
        raw = next(tmp_path.glob("*.session")).read_bytes()
        assert b"topsecret" not in raw  # at rest, the cookie value is not readable

    def test_wrong_key_fails_clearly(self, tmp_path):
        EncryptedSessionStore(tmp_path, EncryptedSessionStore.generate_key()).put(
            "shop", "bot", Session(cookies={"sid": "abc"})
        )
        with pytest.raises(AuthError, match="decrypt"):
            EncryptedSessionStore(tmp_path, EncryptedSessionStore.generate_key()).get("shop", "bot")

    def test_missing_session_is_none(self, tmp_path):
        store = EncryptedSessionStore(tmp_path, EncryptedSessionStore.generate_key())
        assert store.get("shop", "nobody") is None


class TestTokenLoginProvider:
    async def test_acquires_bearer_token(self):
        async def endpoint(ctx):
            return {"access_token": "tok-123", "expires_in": 3600}

        session = await TokenLoginProvider(endpoint=endpoint).acquire(CTX)
        assert session.headers["Authorization"] == "Bearer tok-123"
        assert await TokenLoginProvider(endpoint=endpoint).is_valid(session)

    async def test_missing_token_raises(self):
        async def endpoint(ctx):
            return {"error": "bad creds"}

        with pytest.raises(AuthError, match="no access_token"):
            await TokenLoginProvider(endpoint=endpoint).acquire(CTX)

    async def test_http_endpoint_over_mock_transport(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"access_token": "xyz", "expires_in": 60})

        provider = TokenLoginProvider(
            token_url="https://auth.example/token", transport=httpx.MockTransport(handler)
        )
        session = await provider.acquire(CTX)
        assert session.headers["Authorization"] == "Bearer xyz"


class TestFormLoginProvider:
    async def test_drives_form_and_captures_cookies(self):
        browser = FakeBrowser(cookies=[{"name": "sid", "value": "logged-in"}])
        provider = FormLoginProvider(
            browser_factory=fake_browser_factory(browser), success_check=".dashboard"
        )
        session = await provider.acquire(CTX)
        assert session.cookies == {"sid": "logged-in"}
        assert "fill:input[name=username]=bot" in browser.log
        assert "click:button[type=submit]" in browser.log

    async def test_no_cookies_is_auth_error(self):
        browser = FakeBrowser(cookies=[])
        provider = FormLoginProvider(browser_factory=fake_browser_factory(browser))
        with pytest.raises(AuthError, match="no cookies"):
            await provider.acquire(CTX)


class StubProvider:
    """A login provider whose validity and login count are test-controlled."""

    def __init__(self, valid: bool):
        self.valid = valid
        self.logins = 0

    async def acquire(self, ctx):
        self.logins += 1
        return Session(cookies={"sid": f"session-{self.logins}"})

    async def is_valid(self, session):
        return self.valid


class TestAuthMiddleware:
    async def test_attaches_session_cookies(self):
        provider = StubProvider(valid=True)
        seen = {}

        async def next_(request):
            seen["cookies"] = dict(request.cookies)
            return Response(status=200)

        await AuthMiddleware(provider, CTX)(ScrapeRequest(url="https://shop.example/x"), next_)
        assert seen["cookies"]["sid"] == "session-1"

    async def test_single_relogin_on_401_then_success(self):
        provider = StubProvider(valid=True)
        calls = {"n": 0}

        async def next_(request):
            calls["n"] += 1
            return Response(status=401) if calls["n"] == 1 else Response(status=200)

        result = await AuthMiddleware(provider, CTX)(
            ScrapeRequest(url="https://shop.example/x"), next_
        )
        assert result.status == 200
        assert provider.logins == 2  # initial login + exactly one re-login on the 401
        assert calls["n"] == 2

    async def test_persistent_401_fails_after_one_relogin_no_loop(self):
        """The DoD guard: never an infinite login loop."""
        provider = StubProvider(valid=True)
        calls = {"n": 0}

        async def next_(request):
            calls["n"] += 1
            return Response(status=401)  # always unauthorized

        with pytest.raises(AuthError, match="still unauthorized"):
            await AuthMiddleware(provider, CTX)(ScrapeRequest(url="https://shop.example/x"), next_)
        # initial login + exactly one re-login, then give up — never a loop
        assert provider.logins == 2
        assert calls["n"] == 2

    async def test_uses_stored_session_without_logging_in(self, tmp_path):
        store = EncryptedSessionStore(tmp_path, EncryptedSessionStore.generate_key())
        store.put("shop", "bot", Session(cookies={"sid": "from-disk"}))
        provider = StubProvider(valid=True)
        seen = {}

        async def next_(request):
            seen["cookies"] = dict(request.cookies)
            return Response(status=200)

        await AuthMiddleware(provider, CTX, store=store)(
            ScrapeRequest(url="https://shop.example/x"), next_
        )
        assert seen["cookies"]["sid"] == "from-disk"
        assert provider.logins == 0  # stored valid session reused, no login

    async def test_internal_ttl_header_never_sent(self):
        seen = {}

        async def next_(request):
            seen["headers"] = dict(request.headers)
            return Response(status=200)

        class TtlProvider(StubProvider):
            async def acquire(self, ctx):
                self.logins += 1
                return Session(headers={"Authorization": "Bearer x", "_ttl": "3600"})

        await AuthMiddleware(TtlProvider(valid=False), CTX)(
            ScrapeRequest(url="https://shop.example/x"), next_
        )
        assert "Authorization" in seen["headers"]
        assert "_ttl" not in seen["headers"]  # internal key filtered out
