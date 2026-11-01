"""Simulated hospital demand with optional Open-Meteo weather inputs."""

from copy import deepcopy
import hashlib
import math
import random
from datetime import date

from .models import Settings
from . import weather
from .guidance import planning_guidance

CATEGORIES = ("critical", "hvac", "labs", "lighting", "laundry", "water_heating", "other")
SOLAR_PERFORMANCE_RATIO = 0.8
_FRESH_WEATHER = object()


def seeded_rng(day: date, scenario: str, salt: str = "forecast") -> random.Random:
    digest = hashlib.sha256(f"gridwell-v1:{day}:{scenario}:{salt}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def band(value: float, spread: float, ceiling: float | None = None):
    high = value * (1 + spread)
    return {
        "low": round(max(0, value * (1 - spread)), 5),
        "expected": round(value, 5),
        "high": round(min(high, ceiling) if ceiling is not None else high, 5),
    }


def make_forecast(day: date, day_type: str, settings: Settings, overrides=(), *, weather_snapshot=_FRESH_WEATHER):
    # Explicit None freezes synthetic fallback (including seeded history).
    # A stored forecast freezes the original weather even after cache expiry,
    # capacity changes, scenario changes or a later provider outage.
    if weather_snapshot is _FRESH_WEATHER:
        weather_hours = weather.fetch_hourly_weather(day)
        weather_source = weather.LIVE_SOURCE if weather_hours else weather.FALLBACK_SOURCE
        place, fetched_at = weather.location(), weather.fetched_at(day)
    else:
        snapshot = weather_snapshot or {}
        weather_hours = deepcopy(snapshot.get("weather_hours"))
        old_source = snapshot.get("source")
        old_source = old_source if isinstance(old_source, dict) else {}
        weather_source = weather.LIVE_SOURCE if weather_hours else weather.FALLBACK_SOURCE
        place = old_source.get("weather_location", weather.location())
        fetched_at = old_source.get("weather_fetched_at")
    # Scenario templates change heat/PV/outage, not the medical base load.
    rng = seeded_rng(day, "shared-day")
    # A deliberately synthetic 5,200 kWh/day reference. Weather and daily variation
    # are generated from a date seed so refreshes cannot change the selected day.
    daily_reference = 5200 * (0.98 + rng.random() * 0.04)
    shapes = [0.79 + 0.24 * math.exp(-((h - 13) / 5) ** 2)
              + 0.10 * math.exp(-((h - 20) / 2.8) ** 2) for h in range(24)]
    normalization = daily_reference / sum(shapes)
    rows = []
    for hour in range(24):
        total = shapes[hour] * normalization
        # These are adjustable prototype assumptions, not surveyed departments.
        parts = {"critical": total * 0.43, "hvac": total * 0.27,
                 "labs": total * 0.10, "lighting": total * 0.07,
                 "laundry": total * 0.045, "water_heating": total * 0.035,
                 "other": total * 0.05}
        if day_type == "heatwave":
            parts["hvac"] *= 1.55
        # Give laundry/water heating a usual routine, keeping daily budgets fixed.
        parts["laundry"] = daily_reference * 0.045 / 8 if 8 <= hour < 16 else 0
        parts["water_heating"] = daily_reference * 0.035 / 8 if hour in (5, 6, 7, 8, 17, 18, 19, 20) else 0
        total = sum(parts.values())
        pv_factor = 0.24 if day_type == "low_solar" else 1
        sunlight = max(0, math.sin(math.pi * (hour - 6) / 12))
        pv = settings.solar_capacity_kwp * 0.83 * sunlight * pv_factor * (0.96 + rng.random() * 0.08)
        occupancy = min(94, max(50, 74 + 6 * math.sin((hour - 6) / 24 * math.pi * 2) + rng.uniform(-1, 1)))
        price = 7.2 if 0 <= hour < 6 else 8.5
        if 10 <= hour < 16:
            price = 6.8
        if 18 <= hour < 22:
            price = 13.5
        if hour >= 22:
            price = 8.2
        price += rng.uniform(-0.12, 0.12)
        carbon = 0.69 - 0.25 * sunlight + (0.10 if 18 <= hour < 22 else 0) + rng.uniform(-0.012, 0.012)
        outdoor = 27 + 6 * sunlight + (7 if day_type == "heatwave" else 0)
        cloud_cover = round(25 + 15 * (1 - sunlight), 2)
        radiation = pv / settings.solar_capacity_kwp / SOLAR_PERFORMANCE_RATIO / pv_factor * 1000 if settings.solar_capacity_kwp else 0
        base_temperature = outdoor - (7 if day_type == "heatwave" else 0)
        if weather_hours:
            observation = weather_hours[hour]
            base_temperature = observation["temperature_c"]
            outdoor = base_temperature + (7 if day_type == "heatwave" else 0)
            cloud_cover = observation["cloud_cover_pct"]
            radiation = observation["radiation_wm2"]
            pv = settings.solar_capacity_kwp * (radiation / 1000) * SOLAR_PERFORMANCE_RATIO * pv_factor
        unavailable = day_type == "grid_outage" and settings.outage_start <= hour < settings.outage_end
        rows.append({
            "hour": hour, "demand_kwh": band(total, 0.10),
            "occupancy_pct": band(occupancy, 0.08, 100), "solar_kwh": band(pv, 0.25),
            "critical_demand_kwh": parts["critical"],
            "flexible_loads_kwh": {k: parts[k] for k in ("hvac", "laundry", "water_heating")},
            "components_kwh": parts, "grid_price_inr_per_kwh": round(price, 5),
            "grid_carbon_kg_per_kwh": round(carbon, 5), "grid_available": not unavailable,
            "outdoor_temperature_c": round(outdoor, 2), "scenario": day_type,
            "base_temperature_c": round(base_temperature, 2),
            "cloud_cover_pct": cloud_cover, "radiation_wm2": radiation,
            "weather": weather_source,
        })
    warnings, changes = [], []
    for override in overrides:
        row = rows[override.hour]
        original = row[override.field]["expected"]
        row.setdefault("adjusted", {})[override.field] = override.value
        outside = override.value < row[override.field]["low"] or override.value > row[override.field]["high"]
        changes.append({"hour": override.hour, "field": override.field, "original": original,
                        "adjusted": override.value, "outside_range": outside})
        if outside:
            warnings.append(f"{override.hour:02d}:00 {override.field}: adjustment {override.value:g} is outside the original forecast range.")
    forecast = {
        "date": day.isoformat(), "day_type": day_type, "hours": rows, "adjustments": changes,
        "weather_hours": deepcopy(weather_hours),
        "weather_strip": [{"hour": row["hour"], "temperature_c": row["base_temperature_c"],
                           "scenario_temperature_c": row["outdoor_temperature_c"],
                           "cloud_cover_pct": row["cloud_cover_pct"], "radiation_wm2": row["radiation_wm2"],
                           "solar_expected_kwh": row["solar_kwh"]["expected"]} for row in rows],
        "warnings": warnings,
        "daily": {
            "demand_kwh": {key: round(sum(r["demand_kwh"][key] for r in rows), 2) for key in ("low", "expected", "high")},
            "solar_kwh": {key: round(sum(r["solar_kwh"][key] for r in rows), 2) for key in ("low", "expected", "high")},
            "occupancy_pct": {key: round(sum(r["occupancy_pct"][key] for r in rows) / 24, 2) for key in ("low", "expected", "high")},
            "cheapest_hours": sorted(range(24), key=lambda h: rows[h]["grid_price_inr_per_kwh"])[:4],
            "cleanest_hours": sorted(range(24), key=lambda h: rows[h]["grid_carbon_kg_per_kwh"])[:4],
            "price_min_inr_per_kwh": min(r["grid_price_inr_per_kwh"] for r in rows),
            "price_max_inr_per_kwh": max(r["grid_price_inr_per_kwh"] for r in rows),
            "carbon_min_kg_per_kwh": min(r["grid_carbon_kg_per_kwh"] for r in rows),
            "carbon_max_kg_per_kwh": max(r["grid_carbon_kg_per_kwh"] for r in rows),
            "outdoor_min_c": min(r["outdoor_temperature_c"] for r in rows),
            "outdoor_max_c": max(r["outdoor_temperature_c"] for r in rows),
            "hvac_kwh": round(sum(r["components_kwh"]["hvac"] for r in rows), 2),
            "solar_capacity_kwp": settings.solar_capacity_kwp,
        },
        "source": {
            "description": "Hospital demand, occupancy, prices and carbon remain date-seeded simulations. Weather is a forecast, never a live hospital meter reading.",
            "demand_source": "Seeded 5,200 kWh/day reference with date variation and scenario modifiers; not fitted to historical meter data.",
            "weather_source": weather_source, "weather_location": place,
            "weather_fetched_at": fetched_at if weather_hours else None,
            "solar_method": "Solar capacity × hourly shortwave radiation / 1000 × performance ratio, then the selected scenario modifier. Simplified horizontal-radiation estimate, not a panel engineering model."
                            if weather_hours else "Date-seeded synthetic daylight profile with the selected scenario modifier. Displayed radiation is an illustrative equivalent, not an external forecast.",
            "solar_performance_ratio": SOLAR_PERFORMANCE_RATIO,
            "range_note": "Illustrative low/high bands are retained for the safety replay, not calibrated confidence intervals.",
        },
    }
    forecast["planning_guidance"] = planning_guidance(forecast, settings)
    return forecast


def materialize_hours(forecast, stress=False):
    result = []
    for original in forecast["hours"]:
        adjusted = original.get("adjusted", {})
        demand = adjusted.get("demand_kwh", original["demand_kwh"]["expected"])
        pv = adjusted.get("solar_kwh", original["solar_kwh"]["expected"])
        occupancy = adjusted.get("occupancy_pct", original["occupancy_pct"]["expected"])
        if stress:
            demand = max(demand, original["demand_kwh"]["high"])
            pv = min(pv, original["solar_kwh"]["low"])
            occupancy = max(occupancy, original["occupancy_pct"]["high"])
        original_total = sum(original["components_kwh"].values())
        original_critical = original["components_kwh"]["critical"]
        # An aggregate forecast edit is not a back door for deleting protected
        # medical load. Below the original critical floor is explicitly invalid.
        critical = original_critical * max(1, demand / original_total)
        noncritical_factor = max(0, demand - critical) / (original_total - original_critical)
        row = dict(original)
        row["parts"] = {key: (critical if key == "critical" else val * noncritical_factor) for key, val in original["components_kwh"].items()}
        row["below_critical_floor"] = demand + 1e-6 < original_critical
        row["pv"] = pv
        row["occupancy"] = occupancy
        result.append(row)
    return result
