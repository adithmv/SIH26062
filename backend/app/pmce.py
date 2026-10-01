"""Basic field outbox, priority policy and central event receipts."""
import json
import os
from datetime import timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, Field, field_validator, model_validator
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import get_session
from .models import PMCEOutbox, PMCEReceipt, PMCESyncLock
from .operations import now_utc, utc
from .schemas import Input

router = APIRouter(prefix="/api/pmce", tags=["PMCE"])
PRIORITIES = {
    "sos": 0, "check_in": 1, "position": 1,
    "critical_inventory": 2, "vehicle_status": 2,
    "inventory_update": 3, "mission_log": 3, "report": 4,
}
MAX_FAILURES = 5
LEASE_SECONDS = 900


def encode(event):
    return json.dumps(event, separators=(",", ":"), sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")


class MissionEvent(Input):
    id: UUID
    device_id: str = Field(min_length=1, max_length=80)
    mission_id: UUID
    kind: Literal["sos", "check_in", "position", "critical_inventory", "vehicle_status", "inventory_update", "mission_log", "report"]
    occurred_at: AwareDatetime
    payload: dict

    @field_validator("occurred_at")
    @classmethod
    def normalize_time(cls, value):
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def bounded_event(self):
        if len(encode(self.model_dump(mode="json"))) > 65536:
            raise ValueError("Event exceeds 64 KiB; attachments are not supported.")
        return self


class SyncOptions(Input):
    mode: Literal["offline", "limited", "broadband"]
    byte_budget: int = Field(default=2048, ge=1, le=1048576)
    limit: int = Field(default=100, ge=1, le=100)


def save_once(session, model, body, **values):
    event = body.model_dump(mode="json")
    row = session.get(model, body.id)
    if row is None:
        row = model(id=body.id, event=event, **values)
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            row = session.get(model, body.id)
            if row is None:
                raise
    if row.event != event:
        raise HTTPException(409, "Event ID already exists with different contents.")
    return row


def delivery_status(row):
    if row.acknowledged_at:
        return "acknowledged"
    if row.blocked:
        return "blocked"
    if row.failures >= MAX_FAILURES:
        return "paused"
    return "pending"


def outgoing(row):
    return {
        "event": row.event, "priority": row.priority,
        "status": delivery_status(row),
        "queued_at": utc(row.queued_at), "acknowledged_at": utc(row.acknowledged_at) if row.acknowledged_at else None,
        "attempts": row.attempts, "last_error": row.last_error,
        "failures": row.failures, "next_attempt_at": utc(row.next_attempt_at) if row.next_attempt_at else None,
    }


@router.post("/outbox", status_code=201)
def enqueue(body: MissionEvent, session: Session = Depends(get_session)):
    row = save_once(session, PMCEOutbox, body, priority=PRIORITIES[body.kind], queued_at=now_utc(), attempts=0)
    return outgoing(row)


@router.get("/outbox")
def outbox(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
           pending_only: bool = False, session: Session = Depends(get_session)):
    query = select(PMCEOutbox)
    if pending_only:
        query = query.where(PMCEOutbox.acknowledged_at.is_(None))
    rows = session.scalars(query.order_by(PMCEOutbox.priority, PMCEOutbox.queued_at, PMCEOutbox.id).offset(offset).limit(limit))
    return [outgoing(row) for row in rows]


def decisions(session, options):
    now = now_utc()
    # Unavailable rows must not hide eligible work behind the batch limit.
    rows = session.scalars(select(PMCEOutbox).where(
        PMCEOutbox.acknowledged_at.is_(None), PMCEOutbox.blocked.is_(False),
        PMCEOutbox.failures < MAX_FAILURES,
        or_(PMCEOutbox.next_attempt_at.is_(None), PMCEOutbox.next_attempt_at <= now),
    ).order_by(
        PMCEOutbox.priority, PMCEOutbox.queued_at, PMCEOutbox.id).limit(options.limit))
    remaining = options.byte_budget
    for row in rows:
        size = len(encode(row.event))
        reason = None
        if options.mode == "offline":
            reason = "offline"
        elif options.mode == "limited" and row.priority > 2:
            reason = "routine data waits for broadband"
        elif options.mode == "limited" and size > remaining:
            reason = "payload exceeds remaining byte budget"
        else:
            remaining -= size
        yield row, size, reason


@router.post("/plan")
def plan(body: SyncOptions, session: Session = Depends(get_session)):
    return [{"id": row.id, "priority": row.priority, "bytes": size,
             "action": "queue" if reason else "send", "reason": reason}
            for row, size, reason in decisions(session, body)]


def central_url():
    url = os.getenv("PMCE_CENTRAL_URL", "").rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(503, "Set PMCE_CENTRAL_URL to the central API origin.")
    return url


def acquire_sync(session):
    owner = uuid4()
    now = now_utc()
    result = session.execute(update(PMCESyncLock).where(
        PMCESyncLock.id == 1,
        or_(PMCESyncLock.owner.is_(None), PMCESyncLock.expires_at <= now),
    ).values(owner=owner, expires_at=now + timedelta(seconds=LEASE_SECONDS)))
    session.commit()
    if result.rowcount != 1:
        raise HTTPException(409, "PMCE sync is already running.")
    return owner


def release_sync(session, owner):
    session.rollback()
    session.execute(update(PMCESyncLock).where(PMCESyncLock.id == 1, PMCESyncLock.owner == owner)
                    .values(owner=None, expires_at=None))
    session.commit()


@router.post("/outbox/{event_id}/retry")
def retry(event_id: UUID, session: Session = Depends(get_session)):
    owner = acquire_sync(session)
    try:
        row = session.get(PMCEOutbox, event_id)
        if row is None:
            raise HTTPException(404, "Queued event not found.")
        if row.acknowledged_at:
            raise HTTPException(409, "Event is already acknowledged.")
        row.blocked = False
        row.failures = 0
        row.next_attempt_at = None
        row.last_error = None
        session.commit()
        return outgoing(row)
    finally:
        release_sync(session, owner)


@router.post("/sync")
def sync(body: SyncOptions, session: Session = Depends(get_session)):
    owner = acquire_sync(session)
    try:
        return deliver(body, session, owner)
    finally:
        release_sync(session, owner)


def deliver(body, session, owner):
    results = []
    with httpx.Client(timeout=5.0) as client:
        for row, size, reason in decisions(session, body):
            if reason:
                results.append({"id": row.id, "status": "pending", "reason": reason})
                continue
            url = central_url()
            renewed = session.execute(update(PMCESyncLock).where(
                PMCESyncLock.id == 1, PMCESyncLock.owner == owner,
                PMCESyncLock.expires_at > now_utc(),
            ).values(expires_at=now_utc() + timedelta(seconds=LEASE_SECONDS)))
            if renewed.rowcount != 1:
                session.rollback()
                raise HTTPException(409, "Sync lease expired; retry the pass.")
            row.attempts += 1
            session.commit()
            try:
                response = client.post(url + "/api/pmce/events", content=encode(row.event), headers={"Content-Type": "application/json"})
                response.raise_for_status()
                if response.json().get("acknowledged_event_id") != str(row.id):
                    raise ValueError("Missing or mismatched receipt")
            except (httpx.HTTPError, ValueError, AttributeError) as exc:
                code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                row.blocked = code is not None and 400 <= code < 500 and code not in (408, 429)
                row.failures += 1
                row.next_attempt_at = now_utc() + timedelta(seconds=min(60, 5 * 2 ** (row.failures - 1)))
                row.last_error = f"Central returned HTTP {code}" if code else "No valid receipt; retry required"
                session.commit()
                results.append({"id": row.id, "status": delivery_status(row), "reason": row.last_error})
                if row.blocked:
                    continue
                break
            row.acknowledged_at = now_utc()
            row.last_error = None
            row.failures = 0
            row.next_attempt_at = None
            session.commit()
            results.append({"id": row.id, "status": "acknowledged", "bytes": size})
    return results


@router.get("/status")
def status(session: Session = Depends(get_session)):
    state = case(
        (PMCEOutbox.acknowledged_at.is_not(None), "acknowledged"),
        (PMCEOutbox.blocked.is_(True), "blocked"),
        (PMCEOutbox.failures >= MAX_FAILURES, "paused"), else_="pending",
    )
    counts = {"pending": 0, "acknowledged": 0, "blocked": 0, "paused": 0}
    counts.update(dict(session.execute(select(state, func.count()).group_by(state)).all()))
    priorities = dict(session.execute(select(PMCEOutbox.priority, func.count()).where(
        PMCEOutbox.acknowledged_at.is_(None)).group_by(PMCEOutbox.priority)).all())
    return {"counts": counts, "undelivered_by_priority": {f"P{i}": priorities.get(i, 0) for i in range(5)},
            "attempts": session.scalar(select(func.coalesce(func.sum(PMCEOutbox.attempts), 0))),
            "central_events": session.scalar(select(func.count()).select_from(PMCEReceipt))}


@router.post("/events")
def receive(body: MissionEvent, session: Session = Depends(get_session)):
    row = save_once(session, PMCEReceipt, body, received_at=now_utc())
    return {"acknowledged_event_id": row.id, "received_at": row.received_at}


@router.get("/events")
def received(limit: int = Query(100, ge=1, le=1000), session: Session = Depends(get_session)):
    rows = session.scalars(select(PMCEReceipt).order_by(PMCEReceipt.received_at.desc(), PMCEReceipt.id).limit(limit))
    return [{"event": row.event, "priority": PRIORITIES[row.event["kind"]], "received_at": row.received_at} for row in rows]
