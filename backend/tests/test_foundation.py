import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app
from app.models import Assignment, Event, Mission, Personnel, Position
from app.seed import seed, uid


@pytest.fixture()
def database(tmp_path, monkeypatch):
    url = os.getenv("TEST_DATABASE_URL", "sqlite:///" + (tmp_path / "test.sqlite3").as_posix())
    engine = create_engine(url)
    import app.db as db
    monkeypatch.setattr(db, "engine", engine)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    with Session(engine) as session:
        seed(session)
    yield engine
    command.downgrade(config, "base")
    engine.dispose()


@pytest.fixture()
def client(database):
    def session_override():
        with Session(database) as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_seed_is_repeatable_and_preserves_changes(database):
    with Session(database) as session:
        person = session.get(Personnel, uid("person-0"))
        person.name = "Edited locally"
        session.commit()
        seed(session)
        assert session.scalar(select(func.count()).select_from(Personnel)) == 4
        assert session.scalar(select(func.count()).select_from(Mission)) == 2
        assert session.scalar(select(func.count()).select_from(Assignment)) == 4
        assert session.scalar(select(func.count()).select_from(Position)) == 1
        assert session.scalar(select(func.count()).select_from(Event)) == 1
        assert session.get(Personnel, uid("person-0")).name == "Edited locally"


def test_api_serves_relationships_and_utc(client):
    assert client.get("/api/health").json()["status"] == "ok"
    missions = client.get("/api/missions").json()
    assert len(missions) == 2
    result = client.get("/api/missions/" + str(uid("mission-0")))
    assert result.status_code == 200
    detail = result.json()
    assert len(detail["personnel"]) == 2
    assert detail["vehicle"]["code"] == "PB-01"
    assert detail["last_position"]["source"] == "simulated_gnss"
    assert detail["departure"].endswith(("+00:00", "Z"))
    assert detail["last_position"]["observed_at"] != detail["last_position"]["received_at"]
    assert len(client.get("/api/personnel").json()) == 4
    assert len(client.get("/api/vehicles").json()) == 2
    assert client.get("/api/events").json()[0]["id"] == str(uid("event-0"))


def test_unknown_and_malformed_missions(client):
    assert client.get("/api/missions/" + str(uid("absent"))).status_code == 404
    assert client.get("/api/missions/not-a-uuid").status_code == 422
