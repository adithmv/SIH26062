from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, update
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


def summary(session, mission, now, contacts=None):
    if contacts is None:
        contacts = tuple(session.scalar(select(model.observed_at).where(model.mission_id == mission.id)
                                        .order_by(model.observed_at.desc()).limit(1))
                         for model in (CheckIn, Position))
    check_in, position = contacts
    contact_times = [utc(value) for value in contacts if value]
    last_contact = max(contact_times) if contact_times else None
    due = utc(mission.expected_check_in)
    if check_in:
        due = max(due, utc(check_in) + timedelta(minutes=mission.check_in_interval_minutes))
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
                              .order_by(Position.observed_at.desc(), Position.received_at.desc(), Position.id).limit(1))
    age = max(0, int((now - utc(position.observed_at)).total_seconds() // 60)) if position else None
    check_ins = session.scalars(select(CheckIn).where(CheckIn.mission_id == mission.id)
                                .order_by(CheckIn.observed_at.desc(), CheckIn.received_at.desc(), CheckIn.id))
    state = summary(session, mission, now)
    return {**state, "personnel": people_summaries(session, list(people), now),
            "vehicle": record(session.get(Vehicle, mission.vehicle_id)),
            "last_position": record(position) if position else None,
            "position_age_minutes": age,
            "position_stale": age is None or age >= mission.check_in_interval_minutes,
            "check_ins": [record(c) for c in check_ins]}


def claim_version(session, mission, version):
    # Reject changes based on an outdated version.
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
    # Lock resources in a fixed order.
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
    shared_people = select(Assignment.mission_id).where(Assignment.personnel_id.in_(personnel_ids))
    conflict = session.scalar(overlaps.where(or_(Mission.vehicle_id == vehicle_id, Mission.id.in_(shared_people)))
                              .order_by(Mission.code).limit(1))
    if conflict:
        raise HTTPException(409, f"Personnel or vehicle already assigned to {conflict.code} during this period.")


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


def people_summaries(session, people, now):
    if not people:
        return []
    contacts = [select(func.max(model.observed_at)).where(model.mission_id == Mission.id)
                .correlate(Mission).scalar_subquery() for model in (CheckIn, Position)]
    rows = session.execute(select(Assignment.personnel_id, Mission, *contacts).join(Mission)
                           .where(Assignment.personnel_id.in_([person.id for person in people]),
                                  Mission.status == "in_field"))
    active = {person_id: summary(session, mission, now, (check_in, position))
              for person_id, mission, check_in, position in rows}
    return [{**record(person), "operational_status": active.get(person.id, {}).get("operational_status", "at_station"),
             "active_mission_id": active.get(person.id, {}).get("id"),
             "active_mission_code": active.get(person.id, {}).get("code")} for person in people]


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
