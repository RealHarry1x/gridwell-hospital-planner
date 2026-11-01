"""Invariant tests, not snapshots of one particular heuristic schedule."""
from datetime import date

import pytest

from app.forecast import make_forecast
from app.models import HourlyEdit, Settings
from app.planner import create_plan, simulate

DAY = date(2026, 11, 1)


@pytest.mark.parametrize("scenario", ["normal", "heatwave", "low_solar", "grid_outage"])
@pytest.mark.parametrize("goal", ["balanced", "cost", "emissions"])
def test_scenarios_and_hourly_energy_invariants(scenario, goal):
    settings = Settings(objective=goal)
    forecast = make_forecast(DAY, scenario, settings)
    result = create_plan(forecast, settings, 700, include_suggestions=False)
    assert result["valid"], [w for w in result["warnings"] if w["severity"] == "error"]
    assert result["risk_case"]["valid"]
    for row in result["hours"]:
        supplied = row["solar_to_load_kwh"] + row["grid_to_load_kwh"] + row["battery_discharge_to_load_kwh"] + row["generator_to_critical_kwh"] + row["generator_to_hvac_kwh"]
        assert row["demand_kwh"] == pytest.approx(supplied + row["unserved_kwh"])
        assert row["solar_available_kwh"] == pytest.approx(row["solar_to_load_kwh"] + row["solar_to_battery_kwh"] + row["solar_curtailed_kwh"])
        assert row["battery_soc_end_kwh"] == pytest.approx(row["battery_soc_start_kwh"] + (row["solar_to_battery_kwh"] + row["grid_to_battery_kwh"]) * settings.charge_efficiency - row["battery_discharge_to_load_kwh"] / settings.discharge_efficiency)
        assert 0 <= row["battery_soc_end_kwh"] <= settings.battery_capacity_kwh + 1e-6
        assert row["solar_to_battery_kwh"] + row["grid_to_battery_kwh"] <= settings.battery_power_kw + 1e-6
        assert row["battery_discharge_to_load_kwh"] <= settings.battery_power_kw + 1e-6
        assert not (row["battery_discharge_to_load_kwh"] > 1e-6 and row["solar_to_battery_kwh"] + row["grid_to_battery_kwh"] > 1e-6)
        assert row["generator_fuel_end_pct"] >= 0
        assert row["generator_to_critical_kwh"] + row["generator_to_hvac_kwh"] <= settings.generator_capacity_kw + 1e-6
        if row["grid_available"]:
            assert not row["generator_running"]
        else:
            assert row["grid_to_load_kwh"] == row["grid_to_battery_kwh"] == 0
            assert row["flexible_loads_kwh"]["laundry"] == row["flexible_loads_kwh"]["water_heating"] == 0
        assert row["critical_status"] == "protected"
        assert row["comfort_status"] == "within_limits"


def test_demand_budgets_and_fair_baseline():
    s = Settings()
    f = make_forecast(DAY, "normal", s)
    plan = create_plan(f, s, 700, include_suggestions=False)
    assert plan["summary"]["demand_kwh"] == pytest.approx(sum(r["demand_kwh"]["expected"] for r in f["hours"]), abs=0.001)
    for name in ("hvac", "laundry", "water_heating"):
        assert sum(r["flexible_loads_kwh"][name] for r in plan["hours"]) == pytest.approx(sum(r["components_kwh"][name] for r in f["hours"]))
    baseline = plan["comparison"]["baseline"]
    assert baseline["demand_kwh"] == pytest.approx(plan["summary"]["demand_kwh"])
    assert baseline["battery_discharge_to_load_kwh"] == baseline["grid_to_battery_kwh"] == 0
    assert plan["summary"]["battery_soc_end_kwh"] == pytest.approx(700)
    assert plan["comparison"]["savings"]["cost_inr"] == pytest.approx(baseline["cost_inr"] - plan["summary"]["cost_inr"])


def test_cost_emissions_and_battery_losses_counted_once():
    s = Settings()
    f = make_forecast(DAY, "normal", s)
    plan = create_plan(f, s, 700, include_suggestions=False)
    assert plan["summary"]["grid_to_battery_kwh"] > 0
    for r in plan["hours"]:
        grid = r["grid_to_load_kwh"] + r["grid_to_battery_kwh"]
        litres = (r["generator_to_critical_kwh"] + r["generator_to_hvac_kwh"]) * s.generator_litres_per_kwh
        assert r["cost_inr"] == pytest.approx(grid * r["grid_price_inr_per_kwh"] + litres * s.generator_fuel_inr_per_litre)
        assert r["emissions_kg_co2e"] == pytest.approx(grid * r["grid_carbon_kg_per_kwh"] + litres * s.generator_emissions_kg_per_litre)


def test_pv_surplus_storage_and_curtailment():
    s = Settings(solar_capacity_kwp=2000)
    result = simulate(make_forecast(DAY, "normal", s), s, 700)
    assert result["summary"]["solar_to_battery_kwh"] > 0
    assert result["summary"]["solar_curtailed_kwh"] > 0
    for row in result["hours"]:
        assert row["solar_available_kwh"] == pytest.approx(row["solar_to_load_kwh"] + row["solar_to_battery_kwh"] + row["solar_curtailed_kwh"])


def test_distinct_scenarios_and_reproducibility():
    s = Settings()
    n = make_forecast(DAY, "normal", s)
    assert n == make_forecast(DAY, "normal", s)
    hot = make_forecast(DAY, "heatwave", s)
    dark = make_forecast(DAY, "low_solar", s)
    assert hot["daily"]["demand_kwh"]["expected"] > n["daily"]["demand_kwh"]["expected"]
    assert dark["daily"]["solar_kwh"]["expected"] < n["daily"]["solar_kwh"]["expected"] * .3
    assert [r['critical_demand_kwh'] for r in hot['hours']] == [r['critical_demand_kwh'] for r in n['hours']]


def test_manual_battery_power_violation_is_not_silently_accepted():
    s = Settings()
    p = create_plan(make_forecast(DAY, "normal", s), s, 700, [HourlyEdit(hour=12, grid_charge_kwh=999)], include_suggestions=False)
    assert not p["valid"]
    assert any(w["code"] == "battery_edit" for w in p["warnings"])
    assert p["hours"][12]["grid_to_battery_kwh"] <= s.battery_power_kw


def test_comfort_and_impossible_windows_block_approval():
    s = Settings(laundry_start=8, laundry_end=9, flexible_power_kw=5)
    p = create_plan(make_forecast(DAY, "normal", s), s, 700, include_suggestions=False)
    assert not p["valid"]
    assert any(w["code"] == "activity_shortfall" for w in p["warnings"])
    s = Settings()
    edits = [HourlyEdit(hour=h, hvac_kwh=0) for h in range(24)]
    p = create_plan(make_forecast(DAY, "normal", s), s, 700, edits, include_suggestions=False)
    assert not p["valid"]
    assert p["summary"]["comfort_status"] == "violation"


def test_exact_outage_threshold_failure_and_fuel_rules():
    s = Settings(outage_start=0, outage_end=6, allow_grid_charging=False)
    f = make_forecast(DAY, "grid_outage", s)
    p = simulate(f, s, 150)
    first = p["hours"][0]
    assert first["generator_running"]
    assert first["battery_soc_end_kwh"] == pytest.approx(100)  # not ordinary 20% reserve
    s = Settings(outage_start=0, outage_end=10, generator_available=False, allow_grid_charging=False)
    p = simulate(make_forecast(DAY, "grid_outage", s), s, 150)
    assert p["summary"]["battery_soc_min_kwh"] == pytest.approx(0)
    assert p["summary"]["critical_unserved_kwh"] > 0
    assert not p["valid"]
    s = Settings(outage_start=0, outage_end=6, generator_fuel_pct=29, generator_tank_litres=10)
    p = simulate(make_forecast(DAY, "grid_outage", s), s, 100)
    assert any("URGENT" in w["message"] for w in p["warnings"])
    assert p["summary"]["generator_fuel_used_litres"] <= 2.9 + 1e-6
    assert p["summary"]["critical_unserved_kwh"] > 0


def test_human_refill_is_explicit_not_automatic():
    s = Settings(outage_start=0, outage_end=6, generator_fuel_pct=29, generator_tank_litres=100)
    f = make_forecast(DAY, "grid_outage", s)
    without = simulate(f, s, 100)
    with_refill = simulate(f, s, 100, refill_hour=1, refill_to_pct=100)
    assert all(r["generator_fuel_added_litres"] == 0 for r in without["hours"])
    assert with_refill["hours"][1]["generator_fuel_added_litres"] > 0


def test_outage_baseline_applies_same_reserve_recovery():
    s = Settings()
    p = create_plan(make_forecast(DAY, 'grid_outage', s), s, 200, include_suggestions=False)
    assert p['comparison']['baseline_valid']
    assert p['comparison']['baseline']['battery_soc_end_kwh'] >= 200 - 1e-6
