from datetime import datetime
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .db import get_session
from .models import Alert, Assignment, CheckIn, Event, Mission, MissionSupply, Personnel, Position, Vehicle
from .pmce import router as pmce_router
from .logistics import router as logistics_router
from .files import router as files_router
from .connections import router as connection_router
from .operations import (assign, audit, claim_version, commit, detail, now_utc, record,
                         require_field, require_mission, resources, summary, utc, validate_observation, person_summary, observation_replay)
from .schemas import (CheckInInput, CompletionInput, EscalationInput, EventOut, HealthOut,
                      MissionDetailOut, MissionEdit, MissionOut, MissionPlan, PersonOut,
                      PositionInput, VehicleOut, VersionInput)

app = FastAPI(title="Polar Expedition Manager", version="0.3.0")

app.include_router(pmce_router)
app.include_router(logistics_router)
app.include_router(files_router)
app.include_router(connection_router)


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(status_code=409, content={"detail": "Record conflicts with an existing identifier or relationship."})


@app.get("/api/health", response_model=HealthOut)
def health(session: Session = Depends(get_session)):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable") from None
    return {"status": "ok", "version": "0.3.0"}


@app.get("/api/missions", response_model=list[MissionOut])
def missions(session: Session = Depends(get_session), now: datetime = Depends(now_utc)):
    return [summary(session, row, now) for row in session.scalars(select(Mission).order_by(Mission.code))]


@app.get("/api/missions/{mission_id}", response_model=MissionDetailOut)
def mission_detail(mission_id: UUID, session: Session = Depends(get_session), now: datetime = Depends(now_utc)):
    return detail(session, require_mission(session, mission_id), now)


@app.post("/api/missions", response_model=MissionDetailOut, status_code=201)
def create_mission(body: MissionPlan, session: Session = Depends(get_session), now: datetime = Depends(now_utc)):
    resources(session, body.vehicle_id, body.personnel_ids, body.departure, body.expected_return)
    mission = Mission(id=uuid4(), **body.model_dump(exclude={"personnel_ids"}))
    session.add(mission)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Mission code already exists or the record could not be saved.") from None
    assign(session, mission, body.personnel_ids)
    audit(session, mission, "mission.created", now, {"personnel_ids": [str(p) for p in body.personnel_ids]})
    commit(session)
    return detail(session, mission, now)


@app.put("/api/missions/{mission_id}", response_model=MissionDetailOut)
def edit_mission(mission_id: UUID, body: MissionEdit, session: Session = Depends(get_session), now: datetime = Depends(now_utc)):
    mission = require_mission(session, mission_id)
    claim_version(session, mission, body.version)
    if mission.status == "completed":
        raise HTTPException(409, "Completed missions are read-only.")
    if body.station != mission.station and session.scalar(select(MissionSupply).where(MissionSupply.mission_id == mission_id).limit(1)):
        raise HTTPException(409, "Cannot change station while supplies are linked to the mission.")
    current_people = set(session.scalars(select(Assignment.personnel_id).where(Assignment.mission_id == mission_id)))
    if mission.status == "in_field" and (set(body.personnel_ids) != current_people or body.vehicle_id != mission.vehicle_id or body.departure != utc(mission.departure)):
        raise HTTPException(409, "An active mission's team, vehicle and departure cannot be changed.")
    resources(session, body.vehicle_id, body.personnel_ids, body.departure, body.expected_return, mission.id)
    before = {key: str(value) for key, value in record(mission).items()}
    for key, value in body.model_dump(exclude={"personnel_ids", "version"}).items():
        setattr(mission, key, value)
    assign(session, mission, body.personnel_ids)
    audit(session, mission, "mission.updated", now, {"previous": before})
    commit(session)
    return detail(session, mission, now)


@app.post("/api/missions/{mission_id}/depart", response_model=MissionDetailOut)
def depart(mission_id: UUID, body: VersionInput, session: Session = Depends(get_session), now: datetime = Depends(now_utc)):
    mission = require_mission(session, mission_id)
    claim_version(session, mission, body.version)
    if mission.status != "planned":
        raise HTTPException(409, "Only a planned mission can depart.")
    if utc(mission.expected_check_in) <= now or utc(mission.expected_return) <= now:
        raise HTTPException(422, "Update the check-in and return times to future times before departure.")
    people = list(session.scalars(select(Assignment.personnel_id).where(Assignment.mission_id == mission.id)))
    resources(session, mission.vehicle_id, people, now, mission.expected_return, mission.id, starting=True)
    mission.status = "in_field"
    mission.actual_departure = now
    audit(session, mission, "mission.departed", now, {})
    commit(session)
    return detail(session, mission, now)


@app.post("/api/missions/{mission_id}/check-ins", response_model=MissionDetailOut, status_code=201)
def check_in(mission_id: UUID, body: CheckInInput, session: Session = Depends(get_session), now: datetime = Depends(now_utc)):
    mission = require_mission(session, mission_id)
    if observation_replay(session, mission, body, "check_in.recorded"):
        return {**detail(session, mission, now), "acknowledged_event_id": body.client_event_id}
    claim_version(session, mission, body.version)
    require_field(mission)
    validate_observation(mission, body.observed_at, now)
    row = CheckIn(id=uuid4(), mission_id=mission.id, received_at=now, **body.model_dump(exclude={"version", "client_event_id"}))
    session.add(row)
    audit(session, mission, "check_in.recorded", now, {"check_in_id": str(row.id), "client_request": body.model_dump(mode="json", exclude={"version", "client_event_id"})}, body.observed_at, 1, event_id=body.client_event_id)
    commit(session)
    return {**detail(session, mission, now), "acknowledged_event_id": body.client_event_id}


@app.post("/api/missions/{mission_id}/positions", response_model=MissionDetailOut, status_code=201)
def position(mission_id: UUID, body: PositionInput, session: Session = Depends(get_session), now: datetime = Depends(now_utc)):
    mission = require_mission(session, mission_id)
    if observation_replay(session, mission, body, "position.recorded"):
        return {**detail(session, mission, now), "acknowledged_event_id": body.client_event_id}
    claim_version(session, mission, body.version)
    require_field(mission)
    validate_observation(mission, body.observed_at, now)
    row = Position(id=uuid4(), mission_id=mission.id, received_at=now, **body.model_dump(exclude={"version", "client_event_id"}))
    session.add(row)
    audit(session, mission, "position.recorded", now, {"position_id": str(row.id), "client_request": body.model_dump(mode="json", exclude={"version", "client_event_id"})}, body.observed_at, 1, event_id=body.client_event_id)
    commit(session)
    return {**detail(session, mission, now), "acknowledged_event_id": body.client_event_id}


@app.post("/api/missions/{mission_id}/escalation", response_model=MissionDetailOut)
def escalate(mission_id: UUID, body: EscalationInput, session: Session = Depends(get_session), now: datetime = Depends(now_utc)):
    mission = require_mission(session, mission_id)
    claim_version(session, mission, body.version)
    require_field(mission)
    if body.level != "emergency" and session.scalar(select(Alert).where(Alert.mission_id == mission_id, Alert.resolved_at.is_(None)).limit(1)):
        raise HTTPException(409, "Resolve open SOS alerts before lowering escalation.")
    mission.escalation_level = body.level
    mission.escalation_reason = body.reason
    audit(session, mission, "mission.escalation_changed", now, {"level": body.level, "reason": body.reason}, priority=0)
    commit(session)
    return detail(session, mission, now)


@app.post("/api/missions/{mission_id}/complete", response_model=MissionDetailOut)
def complete(mission_id: UUID, body: CompletionInput, session: Session = Depends(get_session), now: datetime = Depends(now_utc)):
    mission = require_mission(session, mission_id)
    claim_version(session, mission, body.version)
    require_field(mission)
    if session.scalar(select(Alert).where(Alert.mission_id == mission_id, Alert.resolved_at.is_(None)).limit(1)):
        raise HTTPException(409, "Resolve open SOS alerts before completing the mission.")
    assigned = select(Assignment.personnel_id).where(Assignment.mission_id == mission.id)
    session.execute(update(Personnel).where(Personnel.id.in_(assigned)).values(station=mission.station))
    mission.status = "completed"
    mission.completed_at = now
    mission.escalation_level = "none"
    audit(session, mission, "mission.completed", now, {"note": body.note})
    commit(session)
    return detail(session, mission, now)


@app.get("/api/personnel", response_model=list[PersonOut])
def personnel(session: Session = Depends(get_session), now: datetime = Depends(now_utc)):
    return [person_summary(session, person, now) for person in session.scalars(select(Personnel).order_by(Personnel.name))]


@app.get("/api/vehicles", response_model=list[VehicleOut])
def vehicles(session: Session = Depends(get_session)):
    return [record(row) for row in session.scalars(select(Vehicle).order_by(Vehicle.code))]


@app.get("/api/events", response_model=list[EventOut])
def events(session: Session = Depends(get_session)):
    return [record(row) for row in session.scalars(select(Event).order_by(Event.received_at.desc(), Event.id).limit(100))]
