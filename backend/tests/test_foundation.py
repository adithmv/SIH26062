from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Assignment, Event, Mission, Personnel, Position
from tests.fixtures_data import seed, uid


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
