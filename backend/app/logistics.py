"""Personnel, logistics and emergency operations entered by the operator."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .db import get_session
from .event_schemas import StockPayload
from .ingestion import stock_change
from .models import (Alert, Asset, Cargo, Mission, MissionSupply, Personnel,
                     StockItem, StockMovement, Vehicle)
from .operations import audit, claim_version, commit, detail, now_utc, record, require_mission
from .schemas import Input

router = APIRouter(prefix="/api", tags=["Operations"])


class PersonInput(Input):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=80)
    station: str = Field(min_length=1, max_length=80)


class VehicleInput(Input):
    code: str = Field(min_length=1, max_length=40)
    kind: str = Field(min_length=1, max_length=80)


class AssetInput(Input):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)


class CargoInput(Input):
    code: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=500)
    mission_id: UUID
    location: str = Field(min_length=1, max_length=120)


class StockInput(Input):
    sku: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    station: str = Field(min_length=1, max_length=80)
    unit: str = Field(min_length=1, max_length=30)
    critical: bool = False


class StockAdjustment(StockPayload):
    id: UUID
    occurred_at: AwareDatetime

    @field_validator("occurred_at")
    @classmethod
    def utc_time(cls, value):
        return value.astimezone(timezone.utc)


class AssetAssignment(Input):
    version: int = Field(ge=1)
    mission_id: UUID | None


class AlertAction(Input):
    version: int = Field(ge=1)
    operator: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=1, max_length=500)


def create_record(session, model, body):
    row = model(**body.model_dump())
    session.add(row)
    commit(session)
    return record(row)


@router.post("/personnel", status_code=201)
def create_person(body: PersonInput, session: Session = Depends(get_session)):
    return create_record(session, Personnel, body)


@router.post("/vehicles", status_code=201)
def create_vehicle(body: VehicleInput, session: Session = Depends(get_session)):
    return create_record(session, Vehicle, body)


@router.post("/assets", status_code=201)
def create_asset(body: AssetInput, session: Session = Depends(get_session)):
    return create_record(session, Asset, body)


@router.get("/assets")
def assets(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
           session: Session = Depends(get_session)):
    return [record(row) for row in session.scalars(select(Asset).order_by(Asset.code).offset(offset).limit(limit))]


@router.put("/assets/{asset_id}/assignment")
def assign_asset(asset_id: UUID, body: AssetAssignment, session: Session = Depends(get_session)):
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Asset not found.")
    # Lock affected missions in stable order before modifying their equipment.
    missions = []
    for identity in sorted({m for m in (asset.mission_id, body.mission_id) if m}, key=str):
        mission = require_mission(session, identity)
        claim_version(session, mission, mission.version)
        if mission.status == "in_field":
            raise HTTPException(409, "Equipment assignments cannot change during a field mission.")
        if identity == body.mission_id and mission.status == "completed":
            raise HTTPException(409, "Cannot assign equipment to a completed mission.")
        missions.append(mission)
    result = session.execute(update(Asset).where(Asset.id == asset_id, Asset.version == body.version)
                             .values(mission_id=body.mission_id, version=Asset.version + 1)
                             .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "Asset changed. Refresh before assigning.")
    for mission in missions:
        audit(session, mission, "asset.assignment_changed", now_utc(), {"asset_id": str(asset.id),
              "assigned": mission.id == body.mission_id})
    commit(session)
    session.refresh(asset)
    return record(asset)


@router.post("/cargo", status_code=201)
def create_cargo(body: CargoInput, session: Session = Depends(get_session)):
    mission = require_mission(session, body.mission_id)
    claim_version(session, mission, mission.version)
    if mission.status != "planned":
        raise HTTPException(409, "Register cargo before mission departure.")
    cargo = Cargo(**body.model_dump())
    session.add(cargo)
    session.flush()
    audit(session, mission, "cargo.registered", now_utc(), {"cargo_id": str(cargo.id)})
    commit(session)
    return record(cargo)


@router.get("/cargo")
def cargo(mission_id: UUID | None = None, limit: int = Query(100, ge=1, le=1000),
          offset: int = Query(0, ge=0), session: Session = Depends(get_session)):
    query = select(Cargo)
    if mission_id:
        query = query.where(Cargo.mission_id == mission_id)
    return [record(row) for row in session.scalars(query.order_by(Cargo.code).offset(offset).limit(limit))]


@router.post("/inventory", status_code=201)
def create_stock(body: StockInput, session: Session = Depends(get_session)):
    return create_record(session, StockItem, body)


@router.get("/inventory")
def inventory(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
              session: Session = Depends(get_session)):
    return [record(row) for row in session.scalars(select(StockItem).order_by(StockItem.sku).offset(offset).limit(limit))]


@router.post("/inventory/adjustments", status_code=201)
def adjust_stock(body: StockAdjustment, session: Session = Depends(get_session), now: datetime = Depends(now_utc)):
    request = body.model_dump(mode="json")
    existing = session.get(StockMovement, body.id)
    if existing:
        if existing.request != request:
            raise HTTPException(409, "Movement ID already has different contents.")
        return record(existing)
    if body.occurred_at > now:
        raise HTTPException(422, "Movement time cannot be in the future.")
    stock_change(session, body.item_id, body.expected_version, body.delta, body.note, body.id,
                 body.occurred_at, now, request)
    commit(session)
    return record(session.get(StockMovement, body.id))


@router.get("/inventory/{item_id}/movements")
def movements(item_id: UUID, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
              session: Session = Depends(get_session)):
    if session.get(StockItem, item_id) is None:
        raise HTTPException(404, "Stock item not found.")
    return [record(row) for row in session.scalars(select(StockMovement).where(StockMovement.item_id == item_id)
            .order_by(StockMovement.received_at.desc(), StockMovement.id).offset(offset).limit(limit))]


@router.put("/missions/{mission_id}/supplies/{item_id}")
def link_supply(mission_id: UUID, item_id: UUID, session: Session = Depends(get_session)):
    mission = require_mission(session, mission_id)
    item = session.get(StockItem, item_id)
    if item is None:
        raise HTTPException(404, "Stock item not found.")
    if item.station != mission.station:
        raise HTTPException(422, "Stock and mission must belong to the same station.")
    if session.get(MissionSupply, (mission_id, item_id)):
        return {"mission_id": mission_id, "item_id": item_id}
    claim_version(session, mission, mission.version)
    if mission.status != "planned":
        raise HTTPException(409, "Link supplies before departure.")
    session.add(MissionSupply(mission_id=mission_id, item_id=item_id))
    audit(session, mission, "supply.linked", now_utc(), {"item_id": str(item_id)})
    commit(session)
    return {"mission_id": mission_id, "item_id": item_id}


@router.get("/missions/{mission_id}/impact")
def impact(mission_id: UUID, session: Session = Depends(get_session), now: datetime = Depends(now_utc)):
    mission = require_mission(session, mission_id)
    return {"mission": detail(session, mission, now),
            "assets": [record(row) for row in session.scalars(select(Asset).where(Asset.mission_id == mission_id))],
            "cargo": [record(row) for row in session.scalars(select(Cargo).where(Cargo.mission_id == mission_id))],
            "supplies": [record(row) for row in session.scalars(select(StockItem).join(MissionSupply)
                         .where(MissionSupply.mission_id == mission_id))],
            "alerts": [record(row) for row in session.scalars(select(Alert).where(Alert.mission_id == mission_id)
                       .order_by(Alert.received_at.desc()))]}


@router.get("/alerts")
def alerts(open_only: bool = False, mission_id: UUID | None = None, limit: int = Query(100, ge=1, le=1000),
           offset: int = Query(0, ge=0), session: Session = Depends(get_session)):
    query = select(Alert)
    if open_only:
        query = query.where(Alert.resolved_at.is_(None))
    if mission_id:
        query = query.where(Alert.mission_id == mission_id)
    return [record(row) for row in session.scalars(query.order_by(Alert.received_at.desc(), Alert.id).offset(offset).limit(limit))]


def change_alert(session, alert_id, body, resolve):
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found.")
    if alert.resolved_at or (not resolve and alert.acknowledged_at):
        raise HTTPException(409, "Alert already processed. Refresh its state.")
    if resolve and not alert.acknowledged_at:
        raise HTTPException(409, "Acknowledge the alert before resolving it.")
    now = now_utc()
    values = {"resolved_at": now, "resolved_by": body.operator, "resolution": body.note} if resolve else {
        "acknowledged_at": now, "acknowledged_by": body.operator}
    mission = require_mission(session, alert.mission_id)
    claim_version(session, mission, mission.version)
    result = session.execute(update(Alert).where(Alert.id == alert_id, Alert.version == body.version)
                             .values(**values, version=Alert.version + 1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "Alert changed. Refresh before acting.")
    audit(session, mission, "sos.resolved" if resolve else "sos.acknowledged", now,
          {"alert_id": str(alert.id), "operator": body.operator, "note": body.note}, priority=0)
    commit(session)
    session.refresh(alert)
    return record(alert)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: UUID, body: AlertAction, session: Session = Depends(get_session)):
    return change_alert(session, alert_id, body, False)


@router.post("/alerts/{alert_id}/resolve")
def resolve(alert_id: UUID, body: AlertAction, session: Session = Depends(get_session)):
    return change_alert(session, alert_id, body, True)
