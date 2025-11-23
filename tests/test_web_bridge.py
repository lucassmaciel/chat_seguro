import asyncio
import json

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("starlette")
from starlette.requests import Request
from starlette.responses import JSONResponse

from server import web_bridge


def test_load_allowed_origins_production_requires_entries(tmp_path, monkeypatch):
    env_file = tmp_path / "origins.json"
    env_file.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("ALLOWED_ORIGINS_FILE", str(env_file))

    with pytest.raises(RuntimeError):
        web_bridge._load_allowed_origins("production")


def test_load_allowed_origins_merges_env_and_default(monkeypatch, tmp_path):
    config_file = tmp_path / "origins.json"
    config_file.write_text(json.dumps(["https://app.example.com", "https://app.example.com"]))
    monkeypatch.setenv("ALLOWED_ORIGINS_FILE", str(config_file))
    origins = web_bridge._load_allowed_origins("development")

    assert web_bridge.DEFAULT_DEV_ORIGIN in origins
    assert origins.count("https://app.example.com") == 1


def test_is_origin_allowed_respects_set(monkeypatch):
    monkeypatch.setattr(web_bridge, "ALLOWED_ORIGINS_SET", {"https://allowed.com"})

    assert web_bridge._is_origin_allowed("https://allowed.com") is True
    assert web_bridge._is_origin_allowed("https://blocked.com") is False


def test_load_allowed_origins_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000/")

    origins = web_bridge._load_allowed_origins("development")

    assert origins == ["http://localhost:3000"]


def test_is_origin_allowed_normalizes_trailing_slash(monkeypatch):
    monkeypatch.setattr(web_bridge, "ALLOWED_ORIGINS_SET", {"http://localhost:3000"})

    assert web_bridge._is_origin_allowed("http://localhost:3000/") is True


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


def test_enforce_allowed_origins_blocks(monkeypatch):
    monkeypatch.setattr(web_bridge, "_is_origin_allowed", lambda origin: False)

    scope = {
        "type": "http",
        "headers": [(b"origin", b"http://blocked")],
        "path": "/api/test",
        "method": "GET",
        "query_string": b"",
        "server": ("test", 80),
        "client": ("test", 1234),
    }
    request = Request(scope)

    async def call_next(_):
        return JSONResponse({"status": "ok"})

    response = asyncio.run(web_bridge.enforce_allowed_origins(request, call_next))
    assert response.status_code == 403
