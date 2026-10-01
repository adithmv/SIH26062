"""Validated operational payloads shared by field capture and central ingestion."""
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .schemas import Input

Source = Literal["manual", "radio", "gnss"]
Condition = Literal["operational", "maintenance", "unserviceable", "unknown"]


class SOSPayload(Input):
    message: str = Field(min_length=1, max_length=500)


class CheckInPayload(Input):
    source: Source
    note: str = Field(min_length=1, max_length=500)


class PositionPayload(Input):
    source: Source
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class StockPayload(Input):
    item_id: UUID
    expected_version: int = Field(ge=1)
    delta: int = Field(strict=True, ge=-1000000000, le=1000000000)
    note: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def nonzero(self):
        if self.delta == 0:
            raise ValueError("Stock movement must be nonzero.")
        return self


class VehiclePayload(Input):
    vehicle_id: UUID
    condition: Condition
    note: str = Field(min_length=1, max_length=500)


class AssetPayload(Input):
    asset_id: UUID
    condition: Condition
    note: str = Field(min_length=1, max_length=500)


class CargoPayload(Input):
    cargo_id: UUID
    expected_version: int = Field(ge=1)
    status: Literal["loaded", "in_transit", "delivered", "returned"]
    location: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=1, max_length=500)


class LogPayload(Input):
    note: str = Field(min_length=1, max_length=2000)


class ReportPayload(Input):
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=60000)


PAYLOADS = {
    "sos": SOSPayload, "check_in": CheckInPayload, "position": PositionPayload,
    "critical_inventory": StockPayload, "inventory_update": StockPayload,
    "vehicle_status": VehiclePayload, "asset_condition": AssetPayload,
    "cargo_movement": CargoPayload, "mission_log": LogPayload, "report": ReportPayload,
}
PRIORITIES = {
    "sos": 0, "check_in": 1, "position": 1,
    "critical_inventory": 2, "vehicle_status": 2, "asset_condition": 2,
    "inventory_update": 3, "cargo_movement": 3, "mission_log": 3, "report": 4,
}
