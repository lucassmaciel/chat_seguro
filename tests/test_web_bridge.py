import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("starlette")
from starlette.requests import Request

from server import web_bridge


def test_cors_allows_any_origin():
    middleware = next(
        (mw for mw in web_bridge.app.user_middleware if mw.cls.__name__ == "CORSMiddleware"),
        None,
    )

    assert middleware is not None
    assert middleware.options.get("allow_origin_regex") == ".*"
    assert middleware.options.get("allow_credentials") is True


def test_issue_and_require_session(monkeypatch):
    monkeypatch.setattr(web_bridge, "session_tokens", {})
    token = web_bridge._issue_session_token("client-1")

    scope = {
        "type": "http",
        "headers": [(b"x-session-token", token.encode())],
        "path": "/api/test",
        "method": "GET",
        "query_string": b"",
        "server": ("test", 80),
        "client": ("test", 1234),
    }
    request = Request(scope)
    resolved_token, client_id = web_bridge._require_session(request)

    assert resolved_token == token
    assert client_id == "client-1"
