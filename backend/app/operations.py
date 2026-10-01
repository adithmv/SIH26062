from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Assignment, CheckIn, Event, Mission, Personnel, Position, Vehicle


def now_utc():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def record(obj):
    return {c.name: utc(v) if isinstance(v := getattr(obj, c.name), datetime) else v
            for c in obj.__table__.columns}


def require_mission(session, identity):
    mission = session.get(Mission, identity)
    if mission is None:
        raise HTTPException(404, "Mission not found")
    return mission


def summary(session, mission, now):
    check_in = session.scalar(select(CheckIn).where(CheckIn.mission_id == mission.id)
                              .order_by(CheckIn.observed_at.desc(), CheckIn.id).limit(1))
    position = session.scalar(select(Position).where(Position.mission_id == mission.id)
                              .order_by(Position.observed_at.desc(), Position.id).limit(1))
    contact_times = [utc(item.observed_at) for item in [check_in, position] if item]
    last_contact = max(contact_times) if contact_times else None
    due = utc(mission.expected_check_in)
    if check_in:
        due = max(due, utc(check_in.observed_at) + timedelta(minutes=mission.check_in_interval_minutes))
    due = min(due, utc(mission.expected_return))
    contact = "normal"
    overdue_return = False
    if mission.status == "in_field":
        if now >= due + timedelta(minutes=mission.overdue_grace_minutes):
            contact = "contact_overdue"
        elif now >= due:
            contact = "check_in_due"
        overdue_return = now >= utc(mission.expected_return)
    state = mission.status
    if mission.status == "in_field":
        state = mission.escalation_level if mission.escalation_level != "none" else (
            "return_overdue" if overdue_return else contact)
    return {**record(mission), "operational_status": state, "contact_status": contact,
            "return_overdue": overdue_return, "evaluated_at": now,
            "next_check_in": due, "last_contact_at": last_contact}


def detail(session, mission, now):
    people = session.scalars(select(Personnel).join(Assignment)
                             .where(Assignment.mission_id == mission.id).order_by(Personnel.name))
    position = session.scalar(select(Position).where(Position.mission_id == mission.id)
                              .order_by(Position.observed_at.desc(), Position.id).limit(1))
    age = max(0, int((now - utc(position.observed_at)).total_seconds() // 60)) if position else None
    check_ins = session.scalars(select(CheckIn).where(CheckIn.mission_id == mission.id)
                                .order_by(CheckIn.observed_at.desc(), CheckIn.id))
    state = summary(session, mission, now)
    return {**state, "personnel": [person_summary(session, p, now) for p in people],
            "vehicle": record(session.get(Vehicle, mission.vehicle_id)),
            "last_position": record(position) if position else None,
            "position_age_minutes": age,
            "position_stale": age is None or age >= mission.check_in_interval_minutes,
            "check_ins": [record(c) for c in check_ins]}


def claim_version(session, mission, version):
    # Atomic compare-and-swap also protects SQLite, which has no SELECT FOR UPDATE.
    result = session.execute(update(Mission).where(Mission.id == mission.id, Mission.version == version)
                             .values(version=Mission.version + 1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "Mission changed. Refresh the mission and try again.")
    session.refresh(mission)


def audit(session, mission, kind, now, payload, occurred_at=None, priority=2, event_id=None):
    session.add(Event(id=event_id or uuid4(), mission_id=mission.id, device_id=f"server:{mission.id}",
                      sequence=mission.version, kind=kind, priority=priority,
                      occurred_at=occurred_at or now, received_at=now,
                      payload={"schema_version": 1, **payload}))


def commit(session):
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "An identifier or relationship conflicts with an existing record.") from None


def resources(session, vehicle_id, personnel_ids, departure, expected_return, exclude=None, starting=False):
    # Consistent resource lock order serializes competing reservations on PostgreSQL.
    vehicle = session.scalar(select(Vehicle).where(Vehicle.id == vehicle_id).with_for_update())
    people = list(session.scalars(select(Personnel).where(Personnel.id.in_(personnel_ids))
                                  .order_by(Personnel.id).with_for_update()))
    if vehicle is None or len(people) != len(personnel_ids):
        raise HTTPException(422, "Select an existing vehicle and existing personnel.")
    overlaps = select(Mission).where(Mission.status.in_(["planned", "in_field"]))
    if exclude:
        overlaps = overlaps.where(Mission.id != exclude)
    if starting:
        overlaps = overlaps.where(or_(Mission.status == "in_field",
                                      (Mission.departure < expected_return) & (Mission.expected_return > departure)))
    else:
        overlaps = overlaps.where(Mission.departure < expected_return, Mission.expected_return > departure)
    for other in session.scalars(overlaps):
        assigned = set(session.scalars(select(Assignment.personnel_id).where(Assignment.mission_id == other.id)))
        if other.vehicle_id == vehicle_id or assigned.intersection(personnel_ids):
            raise HTTPException(409, f"Personnel or vehicle already assigned to {other.code} during this period.")


def assign(session, mission, ids):
    session.execute(delete(Assignment).where(Assignment.mission_id == mission.id))
    session.add_all([Assignment(mission_id=mission.id, personnel_id=p) for p in ids])


def require_field(mission):
    if mission.status != "in_field":
        raise HTTPException(409, "This action requires a mission currently in the field.")


def validate_observation(mission, observed_at, now):
    if observed_at > now:
        raise HTTPException(422, "Observation time cannot be in the future.")
    if observed_at < utc(mission.actual_departure or mission.departure):
        raise HTTPException(422, "Observation time cannot precede mission departure.")


def person_summary(session, person, now):
    active = session.scalar(select(Mission).join(Assignment)
                            .where(Assignment.personnel_id == person.id, Mission.status == "in_field"))
    return {**record(person), "operational_status": summary(session, active, now)["operational_status"] if active else "at_station",
            "active_mission_id": active.id if active else None, "active_mission_code": active.code if active else None}


def observation_replay(session, mission, body, kind):
    if body.client_event_id is None:
        return False
    event = session.get(Event, body.client_event_id)
    if event is None:
        return False
    expected = body.model_dump(mode="json", exclude={"version", "client_event_id"})
    if event.mission_id != mission.id or event.kind != kind or event.payload.get("client_request") != expected:
        raise HTTPException(409, "This report ID already belongs to a different observation.")
    return True
