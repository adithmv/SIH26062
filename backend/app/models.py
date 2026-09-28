from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Personnel(Base):
    __tablename__ = "personnel"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(80))
    station: Mapped[str] = mapped_column(String(80))


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    kind: Mapped[str] = mapped_column(String(80))


class Mission(Base):
    __tablename__ = "missions"
    __table_args__ = (
        CheckConstraint("expected_return > departure", name="return_after_departure"),
        CheckConstraint("expected_check_in >= departure", name="check_in_after_departure"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(120))
    station: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="planned")
    vehicle_id: Mapped[UUID] = mapped_column(ForeignKey("vehicles.id"))
    departure: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expected_check_in: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expected_return: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(default=1)


class Assignment(Base):
    __tablename__ = "assignments"
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), primary_key=True)
    personnel_id: Mapped[UUID] = mapped_column(ForeignKey("personnel.id"), primary_key=True)


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="valid_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="valid_longitude"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), index=True)
    latitude: Mapped[float]
    longitude: Mapped[float]
    source: Mapped[str] = mapped_column(String(40))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CheckIn(Base):
    __tablename__ = "check_ins"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), index=True)
    source: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(String(500))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("device_id", "sequence", name="unique_device_sequence"),
        CheckConstraint("priority BETWEEN 0 AND 4", name="valid_priority"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(80))
    sequence: Mapped[int]
    kind: Mapped[str] = mapped_column(String(80))
    priority: Mapped[int]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)
