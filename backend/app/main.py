from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .schemas import HealthOut, MissionOut, MissionDetailOut, PersonOut, VehicleOut, EventOut
from .db import get_session
from .models import Assignment, CheckIn, Event, Mission, Personnel, Position, Vehicle

app = FastAPI(title="SIH26062 Mission Operations", version="0.1.0")


def record(obj):
    result = {}
    for column in obj.__table__.columns:
        value = getattr(obj, column.name)
        if isinstance(value, datetime):
            # SQLite's demo adapter drops offsets; stored values are always UTC.
            value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        result[column.name] = value
    return result


@app.get("/api/health", response_model=HealthOut)
def health(session: Session = Depends(get_session)):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable") from None
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/missions", response_model=list[MissionOut])
def missions(session: Session = Depends(get_session)):
    return [record(row) for row in session.scalars(select(Mission).order_by(Mission.code))]


@app.get("/api/missions/{mission_id}", response_model=MissionDetailOut)
def mission_detail(mission_id: UUID, session: Session = Depends(get_session)):
    mission = session.get(Mission, mission_id)
    if mission is None:
        raise HTTPException(404, "Mission not found")
    people = session.scalars(select(Personnel).join(Assignment).where(Assignment.mission_id == mission_id).order_by(Personnel.name))
    position = session.scalar(select(Position).where(Position.mission_id == mission_id).order_by(Position.observed_at.desc(), Position.id).limit(1))
    check_ins = session.scalars(select(CheckIn).where(CheckIn.mission_id == mission_id).order_by(CheckIn.observed_at.desc()))
    return {**record(mission), "personnel": [record(p) for p in people],
            "vehicle": record(session.get(Vehicle, mission.vehicle_id)),
            "last_position": record(position) if position else None,
            "check_ins": [record(c) for c in check_ins]}


@app.get("/api/personnel", response_model=list[PersonOut])
def personnel(session: Session = Depends(get_session)):
    return [record(row) for row in session.scalars(select(Personnel).order_by(Personnel.name))]


@app.get("/api/vehicles", response_model=list[VehicleOut])
def vehicles(session: Session = Depends(get_session)):
    return [record(row) for row in session.scalars(select(Vehicle).order_by(Vehicle.code))]


@app.get("/api/events", response_model=list[EventOut])
def events(session: Session = Depends(get_session)):
    return [record(row) for row in session.scalars(select(Event).order_by(Event.occurred_at.desc()).limit(100))]
