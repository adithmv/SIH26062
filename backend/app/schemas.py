from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MissionPlan(Input):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    station: str = Field(min_length=1, max_length=80)
    vehicle_id: UUID
    personnel_ids: list[UUID] = Field(min_length=1, max_length=100)
    departure: AwareDatetime
    expected_check_in: AwareDatetime
    expected_return: AwareDatetime
    check_in_interval_minutes: int = Field(default=60, ge=1, le=1440)
    overdue_grace_minutes: int = Field(default=15, ge=0, le=240)

    @field_validator("departure", "expected_check_in", "expected_return")
    @classmethod
    def utc(cls, value):
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def valid_plan(self):
        if not self.departure <= self.expected_check_in <= self.expected_return or self.departure == self.expected_return:
            raise ValueError("Check-in must fall between departure and return; return must follow departure.")
        if len(set(self.personnel_ids)) != len(self.personnel_ids):
            raise ValueError("Select each person only once.")
        return self


class MissionEdit(MissionPlan):
    version: int = Field(ge=1)


class VersionInput(Input):
    version: int = Field(ge=1)


class Observation(VersionInput):
    observed_at: AwareDatetime
    source: Literal["manual", "radio", "gnss", "simulated_gnss", "simulated_radio"]

    @field_validator("observed_at")
    @classmethod
    def utc(cls, value):
        return value.astimezone(timezone.utc)


class CheckInInput(Observation):
    note: str = Field(min_length=1, max_length=500)


class PositionInput(Observation):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class EscalationInput(VersionInput):
    level: Literal["none", "escalation", "emergency"]
    reason: str = Field(min_length=3, max_length=500)


class CompletionInput(VersionInput):
    note: str = Field(min_length=3, max_length=500)


class PersonOut(BaseModel):
    id: UUID
    name: str
    role: str
    station: str
    operational_status: str = "at_station"
    active_mission_id: UUID | None = None
    active_mission_code: str | None = None


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
    check_in_interval_minutes: int
    overdue_grace_minutes: int
    escalation_level: str
    escalation_reason: str | None
    actual_departure: datetime | None
    completed_at: datetime | None
    operational_status: str
    contact_status: str
    return_overdue: bool
    evaluated_at: datetime
    next_check_in: datetime
    last_contact_at: datetime | None


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
    position_age_minutes: int | None
    position_stale: bool
    check_ins: list[CheckInOut]


class HealthOut(BaseModel):
    status: str
    version: str
