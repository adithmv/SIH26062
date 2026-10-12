import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import BaseAccount, BaseSession
from app.security import COOKIE, password_hash

ORIGIN = "https://base.example.test"
PASSWORD = "a-test-password-only-42"


@pytest.fixture
def base(client, database, monkeypatch):
    monkeypatch.setenv("PEM_MODE", "base")
    monkeypatch.setenv("PEM_ORIGIN", ORIGIN)
    with Session(database) as session:
        for role in ("admin", "operator", "viewer"):
            session.add(BaseAccount(username=role, password_hash=password_hash(PASSWORD), role=role))
        session.commit()
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as secure:
        yield secure


def login(base, name="operator"):
    return base.post("/api/auth/login", json={"username": name, "password": PASSWORD})


def test_base_all_existing_areas_require_signin(base):
    for path in ("missions", "personnel", "vehicles", "files", "pmce/status", "pmce/events", "auth/audit"):
        assert base.get("/api/" + path).status_code == 401
    assert base.post("/api/connection/check", json={"address": "http://127.0.0.1:8000"}).status_code == 401
    assert base.get("/api/health").status_code == 200
    assert base.get("/api/auth/session").json() == {"mode": "base", "user": None}


def test_session_cookie_logout_and_revocation(base, database):
    response = login(base)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    for attribute in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert attribute in cookie
    assert base.get("/api/missions").status_code == 200
    token = base.cookies.get(COOKIE)
    with Session(database) as session:
        stored = session.scalar(select(BaseSession))
        assert stored.token_hash != token
    assert base.post("/api/auth/logout").status_code == 200
    base.cookies.set(COOKIE, token)
    assert base.get("/api/missions").status_code == 401


def test_readonly_and_cross_site_writes(base):
    assert login(base, "viewer").status_code == 200
    assert base.get("/api/missions").status_code == 200
    assert base.post("/api/files?name=test.txt", content=b"test").status_code == 403
    assert base.get("/api/auth/audit").status_code == 403
    assert base.post("/api/auth/logout", headers={"Origin": "https://evil.test"}).status_code == 403
    assert base.post("/api/auth/logout").status_code == 200
    assert login(base).status_code == 200
    assert base.post("/api/missions", json={}, headers={"Origin": "https://evil.test"}).status_code == 403


def test_disabled_account_and_expired_session(base, database):
    login(base)
    with Session(database) as session:
        user = session.scalar(select(BaseAccount).where(BaseAccount.username == "operator"))
        user.active = False
        session.commit()
    assert base.get("/api/missions").status_code == 401
    assert login(base).status_code == 401


def test_lockout_and_admin_audit(base):
    for _ in range(5):
        assert base.post("/api/auth/login", json={"username": "operator", "password": "wrong"}).status_code == 401
    assert login(base).status_code == 401
    assert login(base, "admin").status_code == 200
    response = base.get("/api/auth/audit")
    assert response.status_code == 200
    assert any(row["action"] == "login.failed" for row in response.json())
    assert PASSWORD not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_base_requires_https_configuration(monkeypatch):
    monkeypatch.setenv("PEM_MODE", "base")
    monkeypatch.setenv("PEM_ORIGIN", "http://base.test")
    with pytest.raises(RuntimeError, match="PEM_ORIGIN"):
        with TestClient(app):
            pass


def test_device_token_is_scoped_and_revocable(base, database, tmp_path, monkeypatch):
    from app.models import BaseDevice
    from app.security import digest
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path / "files"))
    token = "test-device-token-not-a-live-credential"
    with Session(database) as session:
        session.add(BaseDevice(name="test-device", token_hash=digest(token)))
        session.commit()
    headers = {"Authorization": "Bearer " + token}
    assert base.get("/api/missions", headers=headers).status_code == 403
    assert base.get("/api/files", headers=headers).status_code == 403
    from tests.test_pmce import event
    assert base.post("/api/pmce/events", json=event(device_id="other-device"), headers=headers).status_code == 403
    assert base.post("/api/pmce/events", json=event(device_id="test-device"), headers=headers).status_code == 200
    assert base.post("/api/files?name=received.txt", content=b"test", headers=headers).status_code == 201
    with Session(database) as session:
        device = session.scalar(select(BaseDevice))
        device.active = False
        session.commit()
    assert base.post("/api/files?name=received.txt", content=b"test", headers=headers).status_code == 401


def test_expired_session_does_not_authorize(base, database):
    from datetime import datetime, timezone, timedelta
    login(base)
    with Session(database) as session:
        stored = session.scalar(select(BaseSession))
        stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    assert base.get("/api/missions").status_code == 401
