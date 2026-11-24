import httpx
import pytest

from radar.http import FetchError, PoliteClient, RobotsDisallowed


def make_client(handler, **kw) -> PoliteClient:
    kw.setdefault("min_interval", 0)
    return PoliteClient(transport=httpx.MockTransport(handler), **kw)


def test_robots_disallow_is_respected():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n", headers={"content-type": "text/plain"})
        return httpx.Response(200, json={"ok": True})

    with make_client(handler) as c:
        assert c.get_json("https://ex.com/public") == {"ok": True}
        with pytest.raises(RobotsDisallowed):
            c.get("https://ex.com/private/jobs")


def test_missing_robots_means_allowed():
    def handler(req):
        return httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(200, json=[1])

    with make_client(handler) as c:
        assert c.get_json("https://ex.com/x") == [1]


def test_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("radar.http.time.sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        calls["n"] += 1
        return httpx.Response(429, headers={"retry-after": "1"}) if calls["n"] < 3 else httpx.Response(200, json={})

    with make_client(handler) as c:
        assert c.get_json("https://ex.com/api") == {}
    assert calls["n"] == 3


def test_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr("radar.http.time.sleep", lambda s: None)

    def handler(req):
        return httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(503)

    with make_client(handler, max_retries=2) as c, pytest.raises(FetchError):
        c.get("https://ex.com/api")


def test_user_agent_is_sent():
    seen = {}

    def handler(req):
        seen["ua"] = req.headers["user-agent"]
        return httpx.Response(404)

    with make_client(handler, respect_robots=False) as c:
        c.get("https://ex.com/")
    assert "PersonalJobRadar" in seen["ua"]
