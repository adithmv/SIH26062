"""Deterministic, additive fictional fixtures. Never overwrite existing records."""
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from .db import engine
from .models import Assignment, CheckIn, Event, Mission, Personnel, Position, Vehicle


def uid(key):
    return uuid5(NAMESPACE_URL, f"sih26062:demo:{key}")


def at(hour, minute=0):
    return datetime(2026, 9, 28, hour, minute, tzinfo=timezone.utc)


def seed(session):
    def add(model, key, **values):
        identity = uid(key)
        if session.get(model, identity) is None:
            session.add(model(id=identity, **values))
            session.flush()
        return identity

    people = [add(Personnel, f"person-{i}", name=name, role=role, station="Maitri")
              for i, (name, role) in enumerate([
                  ("Asha Rao", "Glaciologist"), ("Dev Menon", "Field engineer"),
                  ("Mira Shah", "Geologist"), ("Kabir Das", "Vehicle operator")])]
    for i, (name, destination, status) in enumerate([
        ("Ice survey / sector 07", "Survey site G07", "in_field"),
        ("Instrument recovery", "Observation ridge", "planned"),
    ]):
        vehicle = add(Vehicle, f"vehicle-{i}", code=f"PB-0{i+1}", kind="Tracked field vehicle")
        mission = add(Mission, f"mission-{i}", code=f"FM-00{i+1}", name=name,
                      destination=destination, station="Maitri", status=status,
                      vehicle_id=vehicle, departure=at(8+i), expected_check_in=at(12+i),
                      expected_return=at(17+i))
        for person in people[i*2:i*2+2]:
            if session.get(Assignment, (mission, person)) is None:
                session.add(Assignment(mission_id=mission, personnel_id=person))
        if i == 0:
            add(Position, "position-0", mission_id=mission, latitude=-70.77, longitude=11.75,
                source="simulated_gnss", observed_at=at(10, 30), received_at=at(10, 31))
            add(CheckIn, "check-in-0", mission_id=mission, source="simulated_radio",
                note="Team checked in at survey site.", observed_at=at(10, 30), received_at=at(10, 31))
            add(Event, "event-0", mission_id=mission, device_id="demo-station", sequence=1,
                kind="check_in.recorded", priority=1, occurred_at=at(10, 30), received_at=at(10, 31),
                payload={"check_in_id": str(uid("check-in-0")), "schema_version": 1})
    session.commit()


if __name__ == "__main__":
    with Session(engine) as session:
        seed(session)
    print("Fictional demo fixtures are ready.")
