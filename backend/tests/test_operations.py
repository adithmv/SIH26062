from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Event, Mission
from app.operations import now_utc
from app.seed import uid


@pytest.fixture
def clock():
    value = [datetime(2026, 9, 29, 10, tzinfo=timezone.utc)]
    app.dependency_overrides[now_utc] = lambda: value[0]
    yield value
    app.dependency_overrides.pop(now_utc, None)


def plan(clock, **changes):
    now = clock[0]
    return {
        "code": "TEST-" + uuid4().hex[:8], "name": "Field validation", "destination": "Ridge",
        "station": "Maitri", "vehicle_id": str(uid("vehicle-1")),
        "personnel_ids": [str(uid("person-2")), str(uid("person-3"))],
        "departure": now.isoformat(), "expected_check_in": (now + timedelta(hours=1)).isoformat(),
        "expected_return": (now + timedelta(hours=4)).isoformat(),
        "check_in_interval_minutes": 60, "overdue_grace_minutes": 15, **changes,
    }


def create(client, clock, **changes):
    body = plan(clock, **changes)
    result = client.post("/api/missions", json=body)
    assert result.status_code == 201, result.text
    return result.json(), body


def action(client, mission, endpoint, **body):
    return client.post(f"/api/missions/{mission['id']}/{endpoint}", json={"version": mission["version"], **body})


def start(client, clock):
    mission, body = create(client, clock)
    response = action(client, mission, "depart")
    assert response.status_code == 200, response.text
    return response.json(), body


def test_full_lifecycle_and_personnel_return(client, clock, database):
    mission, _ = start(client, clock)
    assert mission["status"] == "in_field"
    assert mission["operational_status"] == "normal"
    clock[0] += timedelta(minutes=20)
    mission = action(client, mission, "check-ins", observed_at=clock[0].isoformat(), source="radio", note="Team accounted for").json()
    assert mission["next_check_in"] == (clock[0] + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    assert mission["version"] == 3
    mission = action(client, mission, "positions", observed_at=clock[0].isoformat(), source="gnss", latitude=-70.8, longitude=11.8).json()
    assert mission["position_stale"] is False
    mission = action(client, mission, "escalation", level="emergency", reason="Operator confirmed incident").json()
    assert mission["operational_status"] == "emergency"
    mission = action(client, mission, "complete", note="All personnel returned").json()
    assert mission["status"] == "completed"
    assert mission["escalation_level"] == "none"
    assert mission["completed_at"]
    people = client.get("/api/personnel").json()
    returned = [p for p in people if p["id"] in [str(uid("person-2")), str(uid("person-3"))]]
    assert all(p["operational_status"] == "at_station" and p["active_mission_id"] is None for p in returned)
    with Session(database) as session:
        records = list(session.scalars(select(Event).where(Event.mission_id == UUID(mission["id"]))))
        assert len(records) == 6
        assert len({event.sequence for event in records}) == 6


def test_deadline_boundaries_and_manual_escalation(client, clock):
    mission, _ = start(client, clock)
    path = "/api/missions/" + mission["id"]
    clock[0] += timedelta(minutes=59, seconds=59)
    assert client.get(path).json()["contact_status"] == "normal"
    clock[0] += timedelta(seconds=1)
    assert client.get(path).json()["operational_status"] == "check_in_due"
    clock[0] += timedelta(minutes=15)
    current = client.get(path).json()
    assert current["operational_status"] == "contact_overdue"
    assert current["escalation_level"] == "none"
    mission = action(client, current, "escalation", level="escalation", reason="Radio attempts unanswered").json()
    clock[0] += timedelta(minutes=1)
    mission = action(client, mission, "check-ins", observed_at=clock[0].isoformat(), source="radio", note="Contact restored").json()
    assert mission["contact_status"] == "normal"
    assert mission["operational_status"] == "escalation"
    mission = action(client, mission, "escalation", level="none", reason="Operator resolved concern").json()
    assert mission["operational_status"] == "normal"
    clock[0] += timedelta(hours=4)
    assert client.get(path).json()["return_overdue"] is True


def test_late_observations_do_not_regress_state(client, clock):
    mission, _ = start(client, clock)
    clock[0] += timedelta(minutes=50)
    recent = clock[0].isoformat()
    for endpoint, data in [("check-ins", {"note": "Recent"}), ("positions", {"latitude": -70.1, "longitude": 12})]:
        mission = action(client, mission, endpoint, source="radio", observed_at=recent, **data).json()
    deadline = mission["next_check_in"]
    clock[0] += timedelta(minutes=10)
    old = (clock[0] - timedelta(minutes=55)).isoformat()
    mission = action(client, mission, "check-ins", source="radio", observed_at=old, note="Delayed report").json()
    mission = action(client, mission, "positions", source="radio", observed_at=old, latitude=-71, longitude=13).json()
    assert mission["next_check_in"] == deadline
    assert mission["last_position"]["latitude"] == -70.1
    assert mission["last_contact_at"] == recent.replace("+00:00", "Z")
    assert len(mission["check_ins"]) == 2


def test_invalid_observations_and_stale_writes_are_atomic(client, clock, database):
    mission, _ = start(client, clock)
    before = mission["version"]
    future = (clock[0] + timedelta(seconds=1)).isoformat()
    assert action(client, mission, "check-ins", observed_at=future, source="radio", note="Future").status_code == 422
    assert action(client, mission, "positions", observed_at=clock[0].isoformat(), source="gnss", latitude=91, longitude=0).status_code == 422
    assert action(client, mission, "check-ins", observed_at="2026-09-29T10:00:00", source="radio", note="No offset").status_code == 422
    current = client.get("/api/missions/" + mission["id"]).json()
    assert current["version"] == before
    updated = action(client, mission, "check-ins", observed_at=clock[0].isoformat(), source="radio", note="Valid")
    assert updated.status_code == 201
    assert action(client, mission, "complete", note="Stale completion").status_code == 409
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Event).where(Event.mission_id == UUID(mission["id"]))) == 3


def test_resource_conflicts_and_reference_validation(client, clock):
    mission, body = create(client, clock)
    duplicate = {**body, "code": "OTHER"}
    assert client.post("/api/missions", json=duplicate).status_code == 409
    assert client.post("/api/missions", json={**duplicate, "vehicle_id": str(uuid4())}).status_code == 422
    assert client.post("/api/missions", json={**duplicate, "personnel_ids": []}).status_code == 422
    assert client.post("/api/missions", json={**duplicate, "personnel_ids": [body["personnel_ids"][0]] * 2}).status_code == 422
    assert client.post("/api/missions", json={**duplicate, "expected_check_in": (clock[0] + timedelta(days=1)).isoformat()}).status_code == 422
    # An overdue active mission still owns its people/vehicle even past its planned return.
    later = plan(clock, code="LATER", vehicle_id=str(uid("vehicle-0")), personnel_ids=[str(uid("person-0"))])
    result = client.post("/api/missions", json=later)
    assert result.status_code == 201
    assert action(client, result.json(), "depart").status_code == 409


def test_edit_plan_and_completed_read_only(client, clock):
    mission, body = create(client, clock)
    path = "/api/missions/" + mission["id"]
    response = client.put(path, json={**body, "version": mission["version"], "destination": "New ridge"})
    assert response.status_code == 200
    mission = response.json()
    assert mission["destination"] == "New ridge"
    assert client.put(path, json={**body, "version": 1}).status_code == 409
    mission = action(client, mission, "depart").json()
    assert client.put(path, json={**body, "version": mission["version"], "personnel_ids": [str(uid("person-0"))]}).status_code == 409
    mission = action(client, mission, "complete", note="Returned safely").json()
    assert client.put(path, json={**body, "version": mission["version"]}).status_code == 409
    assert action(client, mission, "check-ins", observed_at=clock[0].isoformat(), source="radio", note="Late").status_code == 409

def test_future_plan_shows_actual_personnel_location(client, clock):
    # A future plan must not report a person as at station when another mission is active.
    mission, _ = create(client, clock, vehicle_id=str(uid("vehicle-0")), personnel_ids=[str(uid("person-0"))])
    assert mission["status"] == "planned"
    assert mission["personnel"][0]["active_mission_id"] == str(uid("mission-0"))


def test_return_station_and_duplicate_code_rollback(client, clock):
    mission, body = create(client, clock, station="Bharati")
    path = "/api/missions/" + mission["id"]
    conflict = client.put(path, json={**body, "version": mission["version"], "code": "FM-001"})
    assert conflict.status_code == 409
    assert client.get(path).json()["version"] == mission["version"]
    mission = action(client, mission, "depart").json()
    assert action(client, mission, "complete", note="All back at Bharati").status_code == 200
    people = client.get("/api/personnel").json()
    assert all(p["station"] == "Bharati" for p in people if p["id"] in body["personnel_ids"])


def test_zero_grace_and_expired_departure(client, clock):
    mission, _ = create(client, clock, overdue_grace_minutes=0)
    mission = action(client, mission, "depart").json()
    clock[0] += timedelta(hours=1)
    assert client.get("/api/missions/" + mission["id"]).json()["contact_status"] == "contact_overdue"
    old = client.get("/api/missions/" + str(uid("mission-1"))).json()
    assert action(client, old, "depart").status_code == 422

def test_observation_receipt_replay_is_idempotent(client, clock, database):
    mission, _ = start(client, clock)
    event_id = str(uuid4())
    body = {"observed_at": clock[0].isoformat(), "source": "radio", "note": "Receipt test", "client_event_id": event_id}
    first = action(client, mission, "check-ins", **body)
    assert first.status_code == 201
    assert first.json()["acknowledged_event_id"] == event_id
    repeated = action(client, mission, "check-ins", **body)
    assert repeated.status_code == 201
    assert repeated.json()["version"] == first.json()["version"]
    assert len(repeated.json()["check_ins"]) == 1
    # Retrying a lost acknowledgement remains safe after the mission has completed.
    assert action(client, first.json(), "complete", note="Team returned").status_code == 200
    repeated = action(client, mission, "check-ins", **body)
    assert repeated.status_code == 201
    assert repeated.json()["status"] == "completed"
    with Session(database) as session:
        assert session.get(Event, UUID(event_id)).kind == "check_in.recorded"


def test_reused_receipt_id_cannot_change_payload(client, clock):
    mission, _ = start(client, clock)
    event_id = str(uuid4())
    body = {"observed_at": clock[0].isoformat(), "source": "radio", "note": "Original", "client_event_id": event_id}
    first = action(client, mission, "check-ins", **body).json()
    assert action(client, first, "check-ins", **{**body, "note": "Different"}).status_code == 409
    assert client.get("/api/missions/" + mission["id"]).json()["version"] == first["version"]


def test_position_receipt_replay_does_not_duplicate(client, clock):
    mission, _ = start(client, clock)
    body = {"observed_at": clock[0].isoformat(), "source": "gnss", "latitude": -70.8, "longitude": 11.8, "client_event_id": str(uuid4())}
    first = action(client, mission, "positions", **body).json()
    repeated = action(client, mission, "positions", **body).json()
    assert repeated["last_position"]["id"] == first["last_position"]["id"]
    assert repeated["version"] == first["version"]
