"""The request contract. Hard safety rules are deliberately not preset fields."""

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DayType = Literal["normal", "heatwave", "low_solar", "grid_outage"]
Objective = Literal["balanced", "cost", "emissions", "custom"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Settings(StrictModel):
    objective: Objective = "balanced"
    cost_weight: float = Field(0.55, ge=0, le=1)
    carbon_weight: float = Field(0.45, ge=0, le=1)
    battery_capacity_kwh: float = Field(1000, ge=100, le=10000)
    battery_power_kw: float = Field(250, gt=0, le=2000)
    reserve_pct: float = Field(20, ge=10, le=90)
    charge_efficiency: float = Field(0.95, ge=0.5, le=1)
    discharge_efficiency: float = Field(0.95, ge=0.5, le=1)
    allow_grid_charging: bool = True
    solar_capacity_kwp: float = Field(100, ge=0, le=2000)
    comfort_min_c: float = Field(22, ge=16, le=29)
    comfort_max_c: float = Field(26, ge=17, le=32)
    laundry_start: int = Field(8, ge=0, le=23)
    laundry_end: int = Field(17, ge=1, le=24)
    water_heating_start: int = Field(5, ge=0, le=23)
    water_heating_end: int = Field(22, ge=1, le=24)
    flexible_power_kw: float = Field(90, gt=0, le=500)
    outage_start: int = Field(18, ge=0, le=23)
    outage_end: int = Field(23, ge=1, le=24)
    generator_capacity_kw: float = Field(220, ge=0, le=2000)
    generator_tank_litres: float = Field(400, gt=0, le=10000)
    generator_fuel_pct: float = Field(55, ge=0, le=100)
    generator_litres_per_kwh: float = Field(0.27, gt=0, le=2)
    generator_fuel_inr_per_litre: float = Field(95, ge=0, le=500)
    generator_emissions_kg_per_litre: float = Field(2.68, ge=0, le=10)
    generator_available: bool = True
    generator_failure_hour: int | None = Field(None, ge=0, le=23)

    @model_validator(mode="after")
    def coherent_settings(self):
        for label, start, end in [
            ("Laundry", self.laundry_start, self.laundry_end),
            ("Water heating", self.water_heating_start, self.water_heating_end),
            ("Outage", self.outage_start, self.outage_end),
        ]:
            if start >= end:
                raise ValueError(f"{label}: start must be earlier than end (same-day windows).")
        if self.comfort_max_c - self.comfort_min_c < 0.5:
            raise ValueError("Comfort maximum must be at least 0.5°C above the minimum.")
        if self.cost_weight + self.carbon_weight <= 0:
            raise ValueError("At least one objective weight must be above zero.")
        return self


class ForecastOverride(StrictModel):
    hour: int = Field(ge=0, le=23)
    field: Literal["demand_kwh", "occupancy_pct", "solar_kwh"]
    value: float = Field(ge=0, le=50000)

    @model_validator(mode="after")
    def valid_occupancy(self):
        if self.field == "occupancy_pct" and self.value > 100:
            raise ValueError("Occupancy must be between 0 and 100%.")
        return self


class HourlyEdit(StrictModel):
    hour: int = Field(ge=0, le=23)
    hvac_kwh: float | None = Field(None, ge=0, le=10000)
    laundry_kwh: float | None = Field(None, ge=0, le=10000)
    water_heating_kwh: float | None = Field(None, ge=0, le=10000)
    grid_charge_kwh: float | None = Field(None, ge=0, le=10000)
    battery_discharge_kwh: float | None = Field(None, ge=0, le=10000)


class PlanRequest(StrictModel):
    date: Date
    day_type: DayType = "normal"
    settings: Settings = Field(default_factory=Settings)
    forecast_overrides: list[ForecastOverride] = Field(default_factory=list, max_length=72)
    hourly_edits: list[HourlyEdit] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def unique_edits(self):
        if len({e.hour for e in self.hourly_edits}) != len(self.hourly_edits):
            raise ValueError("Only one detailed edit object is allowed per hour.")
        keys = [(o.hour, o.field) for o in self.forecast_overrides]
        if len(set(keys)) != len(keys):
            raise ValueError("Only one forecast adjustment is allowed per hour and field.")
        return self


class VerifyRequest(PlanRequest):
    plan_id: str | None = None


class ApprovalRequest(StrictModel):
    revision: int = Field(ge=1)


class PresetRequest(StrictModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field("Custom simulated planning settings.", max_length=300)
    settings: Settings

    @model_validator(mode="after")
    def clean_name(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Preset name cannot be blank.")
        return self


class OutageRequest(PlanRequest):
    day_type: DayType = "grid_outage"
    plan_id: str | None = None
    # Optional override applies only to this rehearsal, never to the carry ledger.
    initial_soc_pct_override: float | None = Field(None, ge=0, le=100)
    refill_hour: int | None = Field(None, ge=0, le=23)
    refill_to_pct: float = Field(100, ge=0, le=100)


class AssistantRequest(StrictModel):
    message: str = Field(min_length=1, max_length=1500)
    plan_id: str | None = None
    date: Date | None = None
    day_type: DayType = "normal"


class ResetRequest(StrictModel):
    initial_soc_pct: float = Field(70, ge=10, le=100)
