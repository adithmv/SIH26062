import pytest
from pydantic import ValidationError
from app.config import Settings, get_settings


@pytest.mark.parametrize("origin", ["http://base.test", "https://base.test/path", "https://u:secret@base.test", "https://base.test?x=1", "https://base.test#part", "https://base.test:0", "https://base.test:70000", " https://base.test", "https://base.test\\evil", ""])
def test_invalid_base_origin_is_rejected(origin):
    with pytest.raises(ValidationError):
        Settings(mode="base", origin=origin)


@pytest.mark.parametrize("origin,expected", [("https://BASE.example:443/", "https://base.example"), ("https://[::1]:8443", "https://[::1]:8443"), ("https://base.internal", "https://base.internal")])
def test_origin_matches_browser_serialization(origin, expected):
    assert Settings(mode="base", origin=origin).origin == expected


def test_environment_only_and_unknown_mode_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("PEM_MODE", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("PEM_MODE=base\nPEM_ORIGIN=https://unexpected.test\n")
    assert get_settings().mode == "local"
    monkeypatch.setenv("PEM_MODE", "bsae")
    with pytest.raises(ValidationError):
        get_settings()


def test_base_disables_schema_even_when_app_was_imported_in_local_mode(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setenv("PEM_MODE", "base")
    monkeypatch.setenv("PEM_ORIGIN", "https://base.test")
    with TestClient(app) as client:
        for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
            response = client.get(path)
            assert response.status_code == 404
            assert response.headers["cache-control"] == "no-store"
