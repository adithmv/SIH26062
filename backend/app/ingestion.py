"""Commit a central receipt and its operational effects together."""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .event_schemas import PRIORITIES
from .models import (Alert, Asset, Cargo, CheckIn, Event, Mission, MissionSupply,
                     PMCEReceipt, Position, StockItem, StockMovement, Vehicle)
from .operations import audit, claim_version, require_field, require_mission, utc, validate_observation


def stock_change(session, item_id, expected_version, delta, note, event_id,
                 occurred_at, received_at, request, mission_id=None):
    item = session.get(StockItem, item_id)
    if item is None:
        raise HTTPException(404, "Stock item not found.")
    result = session.execute(update(StockItem).where(
        StockItem.id == item_id, StockItem.version == expected_version,
        StockItem.quantity + delta >= 0,
        StockItem.quantity + delta <= 1000000000,
    ).values(quantity=StockItem.quantity + delta, version=StockItem.version + 1)
        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "Stock changed or quantity is outside allowed bounds. Review current stock.")
    session.refresh(item)
    session.add(StockMovement(id=event_id, item_id=item_id, mission_id=mission_id,
                             delta=delta, balance=item.quantity, note=note,
                             occurred_at=occurred_at, received_at=received_at, request=request))
    return item


def apply_event(session, body, mission, now):
    data = body.payload
    if body.kind == "check_in":
        session.add(CheckIn(id=body.id, mission_id=mission.id, observed_at=body.occurred_at,
                            received_at=now, **data))
    elif body.kind == "position":
        session.add(Position(id=body.id, mission_id=mission.id, observed_at=body.occurred_at,
                             received_at=now, **data))
    elif body.kind == "sos":
        session.add(Alert(id=body.id, mission_id=mission.id, message=data["message"],
                          occurred_at=body.occurred_at, received_at=now))
        mission.escalation_level = "emergency"
        mission.escalation_reason = data["message"]
    elif body.kind in ("critical_inventory", "inventory_update"):
        item_id = UUID(data["item_id"])
        item = session.get(StockItem, item_id)
        if item is None or session.get(MissionSupply, (mission.id, item_id)) is None:
            raise HTTPException(422, "Stock item is not linked to this mission.")
        if item.critical != (body.kind == "critical_inventory"):
            raise HTTPException(422, "Event kind must match the stock item's critical flag.")
        stock_change(session, item_id, data["expected_version"], data["delta"], data["note"],
                     body.id, body.occurred_at, now, body.model_dump(mode="json"), mission.id)
    elif body.kind == "vehicle_status":
        if UUID(data["vehicle_id"]) != mission.vehicle_id:
            raise HTTPException(422, "Vehicle is not assigned to this mission.")
        vehicle = session.get(Vehicle, mission.vehicle_id)
        if vehicle.condition_at is None or body.occurred_at > utc(vehicle.condition_at):
            vehicle.condition = data["condition"]
            vehicle.condition_at = body.occurred_at
    elif body.kind == "asset_condition":
        asset = session.get(Asset, UUID(data["asset_id"]))
        if asset is None or asset.mission_id != mission.id:
            raise HTTPException(422, "Asset is not assigned to this mission.")
        if asset.condition_at is None or body.occurred_at > utc(asset.condition_at):
            asset.condition = data["condition"]
            asset.condition_at = body.occurred_at
            asset.version += 1
    elif body.kind == "cargo_movement":
        cargo = session.get(Cargo, UUID(data["cargo_id"]))
        if cargo is None or cargo.mission_id != mission.id:
            raise HTTPException(422, "Cargo is not assigned to this mission.")
        transitions = {"registered": {"loaded"}, "loaded": {"in_transit", "returned"},
                       "in_transit": {"delivered", "returned"}, "delivered": {"returned"}, "returned": set()}
        if data["status"] not in transitions[cargo.status]:
            raise HTTPException(409, "Invalid cargo transition. Review current cargo status.")
        if cargo.updated_at and body.occurred_at < utc(cargo.updated_at):
            raise HTTPException(409, "Cargo movement predates the current state.")
        result = session.execute(update(Cargo).where(Cargo.id == cargo.id, Cargo.version == data["expected_version"])
                                 .values(status=data["status"], location=data["location"], updated_at=body.occurred_at,
                                         version=Cargo.version + 1).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise HTTPException(409, "Cargo changed. Review current cargo status.")
    # mission_log and report are retained in the immutable event history.


def ingest(session, body, now):
    event = body.model_dump(mode="json")
    try:
        existing = session.get(PMCEReceipt, body.id)
        if existing:
            if existing.event != event:
                raise HTTPException(409, "Event ID already exists with different contents.")
            return existing
        mission = require_mission(session, body.mission_id)
        # The mission version update serializes event effects with lifecycle edits.
        claim_version(session, mission, mission.version)
        require_field(mission)
        validate_observation(mission, body.occurred_at, now)
        if session.get(Event, body.id):
            raise HTTPException(409, "Event ID is already used by another operation.")
        apply_event(session, body, mission, now)
        audit(session, mission, "pmce." + body.kind, now,
              {"device_id": body.device_id, "event": event}, body.occurred_at,
              PRIORITIES[body.kind], event_id=body.id)
        receipt = PMCEReceipt(id=body.id, event=event, received_at=now)
        session.add(receipt)
        session.commit()
        return receipt
    except (HTTPException, IntegrityError) as exc:
        session.rollback()
        # Another sender may have committed the same event while we waited.
        existing = session.get(PMCEReceipt, body.id)
        if existing and existing.event == event:
            return existing
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, "Event conflicts with an existing operation.") from None
        raise
