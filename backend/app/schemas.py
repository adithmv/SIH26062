from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class PersonOut(BaseModel):
    id: UUID
    name: str
    role: str
    station: str


class VehicleOut(BaseModel):
    id: UUID
    code: str
    kind: str


class MissionOut(BaseModel):
    id: UUID
    code: str
    name: str
    destination: str
    station: str
    status: str
    vehicle_id: UUID
    departure: datetime
    expected_check_in: datetime
    expected_return: datetime
    version: int


class PositionOut(BaseModel):
    id: UUID
    mission_id: UUID
    latitude: float
    longitude: float
    source: str
    observed_at: datetime
    received_at: datetime


class CheckInOut(BaseModel):
    id: UUID
    mission_id: UUID
    source: str
    note: str
    observed_at: datetime
    received_at: datetime


class EventOut(BaseModel):
    id: UUID
    mission_id: UUID
    device_id: str
    sequence: int
    kind: str
    priority: int
    occurred_at: datetime
    received_at: datetime
    payload: dict


class MissionDetailOut(MissionOut):
    personnel: list[PersonOut]
    vehicle: VehicleOut
    last_position: PositionOut | None
    check_ins: list[CheckInOut]


class HealthOut(BaseModel):
    status: str
    version: str
