import httpx
import pytest

from app import connections

pytestmark = pytest.mark.empty_database


def remote(monkeypatch, handler):
    client = httpx.AsyncClient
    def create(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return client(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(connections.httpx, "AsyncClient", create)


def test_reachable_backend(client, monkeypatch):
    def handler(request):
        assert str(request.url) == "http://192.168.1.20:8000/api/health"
        return httpx.Response(200, json={"status": "ok", "version": "0.3.0"})
    remote(monkeypatch, handler)
    response = client.post("/api/connection/check", json={"address": "http://192.168.1.20:8000/"})
    data = response.json()
    assert data["reachable"]
    assert data["version"] == "0.3.0"
    assert data["checked_at"] and data["response_ms"] >= 0
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("address", ["http://169.254.169.254", "http://8.8.8.8", "file:///tmp", "http://user:secret@localhost", "http://localhost/api", "http://localhost?key=x", "http://localhost:0", "http://example.com", "http://0.0.0.0"])
def test_invalid_target_is_rejected(client, address):
    assert client.post("/api/connection/check", json={"address": address}).status_code == 400


@pytest.mark.parametrize("response", [httpx.Response(401), httpx.Response(503), httpx.Response(302, headers={"location": "http://8.8.8.8"}), httpx.Response(200, text="not json"), httpx.Response(200, json={"status": "wrong"}), httpx.Response(200, text="x" * 4097)])
def test_bad_response_is_not_connected(client, monkeypatch, response):
    remote(monkeypatch, lambda request: response)
    data = client.post("/api/connection/check", json={"address": "http://localhost:8001"}).json()
    assert not data["reachable"]
    assert data["response_ms"] is None
    assert data["message"]


def test_timeout(client, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("private diagnostic")
    remote(monkeypatch, handler)
    result = client.post("/api/connection/check", json={"address": "http://localhost:8001"}).json()
    assert not result["reachable"]
    assert "timed out" in result["message"]
    assert "private diagnostic" not in result["message"]
