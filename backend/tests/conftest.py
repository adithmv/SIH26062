import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app
from tests.fixtures_data import seed


@pytest.fixture()
def database(tmp_path, monkeypatch, request):
    url = os.getenv("TEST_DATABASE_URL", "sqlite:///" + (tmp_path / "test.sqlite3").as_posix())
    engine = create_engine(url)
    import app.db as db
    monkeypatch.setattr(db, "engine", engine)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    if not request.node.get_closest_marker("empty_database"):
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
