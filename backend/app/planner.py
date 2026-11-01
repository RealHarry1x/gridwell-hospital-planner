"""A transparent hourly heuristic, NOT a certified optimizer or clinical model.

Energy is kWh per one-hour interval. The numerical kW limit therefore also
bounds each interval's energy. Every load/source and storage loss is accounted
once. The doc in docs/planner.md explains the policy in plain language.
"""

import math

from .forecast import CATEGORIES, materialize_hours
from .models import Settings

EPS = 1e-6
EMERGENCY_PCT = 10  # Deliberately not configurable through presets.
THERMAL_COEFFICIENT = 0.018  # Illustrative °C/kWh; not a building model.
THERMAL_RETENTION = 0.87


def issue(message, code="information", hour=None, severity="warning"):
    return {"message": message, "code": code, "hour": hour, "severity": severity}


def weights(settings):
    if settings.objective == "cost":
        return 1.0, 0.0
    if settings.objective == "emissions":
        return 0.0, 1.0
    if settings.objective == "balanced":
        return 0.55, 0.45
    total = settings.cost_weight + settings.carbon_weight
    return settings.cost_weight / total, settings.carbon_weight / total


def allocate_activity(name, raw, settings, scores, edits, baseline, warnings):
    """Keep the SAME daily laundry/heating energy; only its hours may move."""
    budget = sum(h["parts"][name] for h in raw)
    start, end = getattr(settings, f"{name}_start"), getattr(settings, f"{name}_end")
    editable = f"{name}_kwh"
    schedule = [0.0] * 24
    fixed = {}
    for hour, edit in edits.items():
        value = edit.get(editable)
        if value is not None:
            fixed[hour] = value
            schedule[hour] = value
            if value > EPS and not (start <= hour < end and raw[hour]["grid_available"]):
                warnings.append(issue(f"{name.replace('_', ' ').title()} cannot run at {hour:02d}:00 outside its available window or during an outage.", "activity_window", hour, "error"))
            if value > settings.flexible_power_kw + EPS:
                warnings.append(issue(f"{name}: requested {value:.1f} kWh exceeds the {settings.flexible_power_kw:g} kW activity limit.", "activity_power", hour, "error"))
    remaining = budget - sum(fixed.values())
    eligible = [h for h in range(start, end) if h not in fixed and raw[h]["grid_available"]]
    if remaining < -EPS:
        warnings.append(issue(f"Edited {name} energy exceeds its {budget:.1f} kWh daily budget by {-remaining:.1f} kWh.", "activity_budget", severity="error"))
        remaining = 0
    if baseline:
        # Preserve usual timing as far as the same windows/outage rules allow.
        preferred = sorted(eligible, key=lambda h: -raw[h]["parts"][name])
        for hour in preferred:
            value = min(raw[hour]["parts"][name], remaining, settings.flexible_power_kw)
            schedule[hour] += value
            remaining -= value
        # Only outage/window recovery is allowed here, not price dispatch.
        order = eligible
    else:
        order = sorted(eligible, key=lambda h: (scores[h], h))
    for hour in order:
        value = min(settings.flexible_power_kw - schedule[hour], remaining)
        schedule[hour] += max(0, value)
        remaining -= max(0, value)
    if remaining > EPS:
        warnings.append(issue(f"{remaining:.1f} kWh of {name.replace('_', ' ')} cannot fit its window and power limit. Widen the window or undo edits.", "activity_shortfall", severity="error"))
    return schedule


def simulate(forecast, settings: Settings, start_soc, hourly_edits=(), baseline=False,
             stress=False, fixed_rows=None, refill_hour=None, refill_to_pct=100):
    raw = materialize_hours(forecast, stress)
    warnings = []
    for data in raw:
        if data["below_critical_floor"]:
            warnings.append(issue("Adjusted total demand is below protected medical demand. The critical floor is retained; raise this forecast adjustment.", "critical_forecast_floor", data["hour"], "error"))
    edits = {e.hour: e.model_dump(exclude_none=True) for e in hourly_edits}
    cw, ew = weights(settings)
    max_price = max(h["grid_price_inr_per_kwh"] for h in raw)
    max_carbon = max(h["grid_carbon_kg_per_kwh"] for h in raw)
    scores = [cw * h["grid_price_inr_per_kwh"] / max_price + ew * h["grid_carbon_kg_per_kwh"] / max_carbon for h in raw]
    if fixed_rows:
        laundry = [h["flexible_loads_kwh"]["laundry"] for h in fixed_rows]
        heating = [h["flexible_loads_kwh"]["water_heating"] for h in fixed_rows]
        hvac = [h["flexible_loads_kwh"]["hvac"] for h in fixed_rows]
    else:
        laundry = allocate_activity("laundry", raw, settings, scores, edits, baseline, warnings)
        heating = allocate_activity("water_heating", raw, settings, scores, edits, baseline, warnings)
        hvac = [h["parts"]["hvac"] for h in raw]
        if not baseline:
            # Move a small amount of cooling to an earlier better-scored hour.
            # The temperature replay below remains a HARD check of the result.
            for hour in range(2, 24):
                if raw[hour]["grid_available"] and hour not in edits:
                    earlier = min(range(hour - 2, hour), key=lambda h: scores[h])
                    if raw[earlier]["grid_available"] and scores[earlier] + 0.08 < scores[hour]:
                        shift = hvac[hour] * 0.12
                        hvac[hour] -= shift
                        hvac[earlier] += shift
        for hour, edit in edits.items():
            if edit.get("hvac_kwh") is not None:
                hvac[hour] = edit["hvac_kwh"]
        # HVAC is shifted, never silently removed or added by an hourly edit.
        hvac_difference = sum(hvac) - sum(h["parts"]["hvac"] for h in raw)
        fixed_hvac = {h for h, e in edits.items() if e.get("hvac_kwh") is not None}
        if fixed_hvac and abs(hvac_difference) > EPS:
            unfixed = [h for h in range(24) if h not in fixed_hvac]
            available = sum(hvac[h] for h in unfixed)
            if available - hvac_difference < -EPS or not unfixed:
                warnings.append(issue("HVAC edits cannot preserve the daily cooling budget. Reduce the edited values.", "hvac_budget", severity="error"))
            elif available > EPS:
                for hour in unfixed:
                    hvac[hour] *= max(0, (available - hvac_difference) / available)

    capacity = settings.battery_capacity_kwh
    power = settings.battery_power_kw
    reserve = capacity * settings.reserve_pct / 100
    emergency = capacity * EMERGENCY_PCT / 100
    eta_c, eta_d = settings.charge_efficiency, settings.discharge_efficiency
    soc = start_soc
    fuel = settings.generator_tank_litres * settings.generator_fuel_pct / 100
    start_fuel = fuel
    generator_started = False
    midpoint = (settings.comfort_min_c + settings.comfort_max_c) / 2
    temperature = midpoint
    rows = []
    has_outage = any(not h["grid_available"] for h in raw)
    # Closing stock is restored on ordinary days when grid charging is allowed.
    closing_target = max(start_soc, reserve) if not has_outage and settings.allow_grid_charging and not baseline else None
    if start_soc < -EPS or start_soc > capacity + EPS:
        warnings.append(issue("Opening battery energy is outside this capacity. Restore the capacity or reset the demo explicitly.", "initial_soc", severity="error"))
    soc = min(capacity, max(0, soc))
    high_cutoff = sorted(scores)[17]
    for hour, data in enumerate(raw):
        parts = dict(data["parts"])
        parts.update(hvac=hvac[hour], laundry=laundry[hour], water_heating=heating[hour])
        row_warnings = []
        grid_on = data["grid_available"]
        paused = 0.0
        if not grid_on:
            # Life-safety lighting / essential laboratory equipment are already
            # in 'critical'. This remainder is explicitly noncritical.
            paused = sum(parts[k] for k in ("labs", "lighting", "other", "laundry", "water_heating"))
            for key in ("labs", "lighting", "other", "laundry", "water_heating"):
                parts[key] = 0.0
        load = sum(parts.values())
        critical = parts["critical"]
        pv = data["pv"]
        soc_start = soc
        fuel_added = 0.0
        if refill_hour == hour:
            new_fuel = settings.generator_tank_litres * refill_to_pct / 100
            fuel_added = max(0, new_fuel - fuel)
            fuel = max(fuel, new_fuel)
            row_warnings.append("Human-reported refill recorded for this simulation only.")
        fuel_start = fuel
        solar_load = min(load, pv)
        need = max(0, load - solar_load)
        excess_solar = max(0, pv - solar_load)
        discharge = grid_charge = solar_charge = grid_load = gen_critical = gen_hvac = 0.0
        requested = edits.get(hour, {})
        if fixed_rows:
            requested = {
                "grid_charge_kwh": fixed_rows[hour]["grid_to_battery_kwh"],
                "battery_discharge_kwh": fixed_rows[hour]["battery_discharge_to_load_kwh"],
            }
        if not grid_on:
            if not fixed_rows and requested.get("battery_discharge_kwh") is not None:
                warnings.append(issue("Outage battery dispatch follows the protected critical-load / 10% generator rule and cannot be manually overridden. Clear this hourly battery edit.", "protected_outage_dispatch", hour, "error"))
            failed = not settings.generator_available or (settings.generator_failure_hour is not None and hour >= settings.generator_failure_hour)
            # Above 10%, storage helps first. Reaching 10% starts the generator;
            # the ordinary reserve never acts as the generator-start threshold.
            battery_above_emergency = max(0, soc - emergency) * eta_d
            discharge = min(need, power, battery_above_emergency)
            soc -= discharge / eta_d
            need -= discharge
            if soc <= emergency + EPS:
                generator_started = True
            if generator_started and not failed and fuel > EPS:
                generator_limit = min(settings.generator_capacity_kw, fuel / settings.generator_litres_per_kwh)
                critical_remaining = max(0, critical - solar_load - discharge)
                gen_critical = min(critical_remaining, generator_limit)
                gen_hvac = min(max(0, need - gen_critical), max(0, generator_limit - gen_critical))
                fuel -= (gen_critical + gen_hvac) * settings.generator_litres_per_kwh
                need -= gen_critical + gen_hvac
            failed_or_empty = failed or fuel <= EPS
            if failed_or_empty and need > EPS:
                # Release the emergency reserve only on failure/unavailability
                # (including fuel exhaustion). Critical load has first call.
                extra = min(need, max(0, power - discharge), soc * eta_d)
                soc -= extra / eta_d
                discharge += extra
                need -= extra
                row_warnings.append("Generator unavailable / failed / fuel exhausted: emergency battery reserve released; critical load first.")
            if requested.get("grid_charge_kwh", 0) > EPS:
                warnings.append(issue("Grid charging was requested during an outage.", "grid_unavailable", hour, "error"))
            if requested.get("battery_discharge_kwh", 0) > power + EPS:
                warnings.append(issue("Requested battery discharge exceeds its power limit.", "battery_power", hour, "error"))
        else:
            generator_started = False
            # Reserve stored energy for the upcoming outage before spending it.
            future_outage = [h for h in range(hour + 1, 24) if not raw[h]["grid_available"]]
            outage_target = emergency + sum(max(0, raw[h]["parts"]["critical"] + hvac[h] - raw[h]["pv"]) for h in future_outage) / eta_d
            hold = min(capacity, max(reserve, outage_target)) if future_outage else reserve
            if closing_target is not None:
                # Keep enough stock to restore the opening level by midnight.
                hold = max(hold, closing_target - (23 - hour) * power * eta_c)
            intentional_discharge = 0.0
            if not baseline and scores[hour] >= high_cutoff and not future_outage:
                intentional_discharge = min(need, power, max(0, soc - hold) * eta_d)
            if requested.get("battery_discharge_kwh") is not None:
                intentional_discharge = requested["battery_discharge_kwh"]
                if intentional_discharge > power + EPS or intentional_discharge > need + EPS or intentional_discharge > max(0, soc - hold) * eta_d + EPS:
                    warnings.append(issue(f"{hour:02d}:00 battery discharge request exceeds the power, available load, or reserve limit. Executed energy is bounded; approval is blocked.", "battery_edit", hour, "error"))
            discharge = min(intentional_discharge, need, power, max(0, soc - hold) * eta_d)
            soc -= discharge / eta_d
            need -= discharge
            grid_load = need
            need = 0.0

        if discharge <= EPS:
            solar_charge = min(excess_solar, power, max(0, capacity - soc) / eta_c)
            soc += solar_charge * eta_c
        if grid_on and discharge <= EPS:
            future_high = max(scores[hour + 1:], default=0)
            future_demand = sum(max(0, sum(h["parts"].values()) - h["pv"]) for h in raw[hour + 1:] if scores[h["hour"]] >= high_cutoff)
            # Compare future weighted cost/carbon after round-trip losses and
            # an explicit small cycling-benefit margin, not price alone.
            valuable = future_high * eta_c * eta_d - scores[hour] > 0.035
            target = min(capacity, reserve + future_demand / eta_d) if valuable and not baseline else reserve
            if not baseline and any(not raw[h]["grid_available"] for h in range(hour + 1, 24)):
                target = max(target, min(capacity, emergency + sum(max(0, raw[h]["parts"]["critical"] + hvac[h] - raw[h]["pv"]) for h in range(hour + 1, 24) if not raw[h]["grid_available"]) / eta_d))
            if closing_target is not None:
                # At the last available intervals restore terminal stock even
                # if the immediate objective score is not attractive.
                target = max(target, closing_target - (23 - hour) * power * eta_c)
            # Baseline may recover a breached reserve for safety, but never
            # charges deliberately for future price/carbon arbitrage.
            proposed = max(0, target - soc) / eta_c if settings.allow_grid_charging and (not baseline or soc < reserve) else 0.0
            if requested.get("grid_charge_kwh") is not None:
                proposed = requested["grid_charge_kwh"]
                if proposed > EPS and not settings.allow_grid_charging:
                    warnings.append(issue("Grid charging is disabled but was requested in an hourly edit.", "grid_charging_disabled", hour, "error"))
                if proposed + solar_charge > power + EPS or proposed * eta_c + soc > capacity + EPS:
                    warnings.append(issue("Requested battery charging exceeds its power or capacity limit.", "battery_edit", hour, "error"))
            if stress and fixed_rows and settings.allow_grid_charging:
                # Contingency reserve recovery is a safety fallback, not a
                # newly optimized price/carbon dispatch in the adverse replay.
                proposed = max(proposed, max(0, reserve - soc) / eta_c)
            if settings.allow_grid_charging:
                grid_charge = min(proposed, max(0, power - solar_charge), max(0, capacity - soc) / eta_c)
                soc += grid_charge * eta_c
        elif requested.get("grid_charge_kwh", 0) > EPS and discharge > EPS:
            warnings.append(issue("Charging and discharging in the same hourly interval is not allowed.", "simultaneous_battery", hour, "error"))

        fuel = max(0, fuel)
        solar_curtailed = max(0, excess_solar - solar_charge)
        served = solar_load + grid_load + discharge + gen_critical + gen_hvac
        unserved = max(0, load - served)
        # All non-generator sources serve critical first. Generator-critical
        # accounting is separately assigned above; no generator charging exists.
        critical_served = min(critical, solar_load + discharge + grid_load + gen_critical)
        critical_unserved = max(0, critical - critical_served)
        hvac_served = min(parts["hvac"], max(0, served - critical)) if not grid_on else parts["hvac"]
        temperature = midpoint + THERMAL_RETENTION * (temperature - midpoint) + THERMAL_COEFFICIENT * (data["parts"]["hvac"] - hvac_served)
        comfort_ok = settings.comfort_min_c - EPS <= temperature <= settings.comfort_max_c + EPS
        if unserved > EPS:
            row_warnings.append(f"Unserved demand: {unserved:.2f} kWh; critical shortfall: {critical_unserved:.2f} kWh.")
        if not comfort_ok:
            row_warnings.append(f"Illustrative zone temperature {temperature:.2f}°C is outside {settings.comfort_min_c:g}–{settings.comfort_max_c:g}°C.")
        fuel_pct = fuel / settings.generator_tank_litres * 100
        if not grid_on and fuel_pct <= 40 + EPS:
            row_warnings.append(("URGENT: fuel below 30%." if fuel_pct < 30 else "Fuel at or below the 40% warning level.") + " Human refill required; no automatic refuelling.")
        grid_energy = grid_load + grid_charge
        fuel_used = (gen_critical + gen_hvac) * settings.generator_litres_per_kwh
        cost = grid_energy * data["grid_price_inr_per_kwh"] + fuel_used * settings.generator_fuel_inr_per_litre
        grid_emissions = grid_energy * data["grid_carbon_kg_per_kwh"]
        generator_emissions = fuel_used * settings.generator_emissions_kg_per_litre
        row = {
            "hour": hour, "occupancy_pct": data["occupancy"], "demand_kwh": load,
            "critical_demand_kwh": critical, "flexible_loads_kwh": {k: parts[k] for k in ("hvac", "laundry", "water_heating")},
            "components_kwh": parts, "solar_available_kwh": pv,
            "solar_to_load_kwh": solar_load, "solar_to_battery_kwh": solar_charge,
            "solar_curtailed_kwh": solar_curtailed, "grid_to_load_kwh": grid_load,
            "grid_to_battery_kwh": grid_charge, "battery_discharge_to_load_kwh": discharge,
            "battery_soc_start_kwh": soc_start, "battery_soc_end_kwh": soc,
            "battery_charging_loss_kwh": (solar_charge + grid_charge) * (1 - eta_c),
            "battery_discharging_loss_kwh": discharge * (1 / eta_d - 1),
            "generator_to_critical_kwh": gen_critical, "generator_to_hvac_kwh": gen_hvac,
            "generator_fuel_start_pct": fuel_start / settings.generator_tank_litres * 100,
            "generator_fuel_end_pct": fuel_pct, "generator_fuel_used_litres": fuel_used,
            "generator_fuel_added_litres": fuel_added,
            "generator_running": gen_critical + gen_hvac > EPS,
            "grid_price_inr_per_kwh": data["grid_price_inr_per_kwh"],
            "grid_carbon_kg_per_kwh": data["grid_carbon_kg_per_kwh"], "grid_available": grid_on,
            "cost_inr": cost, "grid_emissions_kg_co2e": grid_emissions,
            "generator_emissions_kg_co2e": generator_emissions,
            "emissions_kg_co2e": grid_emissions + generator_emissions,
            "comfort_status": "within_limits" if comfort_ok else "violation",
            "temperature_c": temperature, "critical_status": "protected" if critical_unserved <= EPS else "at_risk",
            "unserved_kwh": unserved, "critical_unserved_kwh": critical_unserved,
            "paused_noncritical_kwh": paused, "warnings": row_warnings,
            "energy_balance_error_kwh": load - served - unserved,
        }
        rows.append(row)

    total = lambda key: sum(r[key] for r in rows)
    closing_ok = closing_target is None or soc + EPS >= closing_target
    battery_bounds_ok = all(-EPS <= r["battery_soc_end_kwh"] <= capacity + EPS for r in rows)
    normal_reserve_ok = all(r["battery_soc_end_kwh"] + EPS >= reserve for r in rows if r["grid_available"])
    checks = [
        {"name": "Critical loads", "passed": total("critical_unserved_kwh") <= EPS, "detail": f'{total("critical_unserved_kwh"):.3f} kWh critical energy unserved'},
        {"name": "Comfort", "passed": all(r["comfort_status"] == "within_limits" for r in rows), "detail": f"Illustrative thermal model within {settings.comfort_min_c:g}–{settings.comfort_max_c:g}°C"},
        {"name": "Battery limits", "passed": battery_bounds_ok and normal_reserve_ok, "detail": f"Normal reserve {settings.reserve_pct:g}%; outage generator start fixed at 10%"},
        {"name": "Power limits", "passed": all(r["solar_to_battery_kwh"] + r["grid_to_battery_kwh"] <= power + EPS and r["battery_discharge_to_load_kwh"] <= power + EPS and r["generator_to_critical_kwh"] + r["generator_to_hvac_kwh"] <= settings.generator_capacity_kw + EPS for r in rows), "detail": f"Battery {power:g} kW; generator {settings.generator_capacity_kw:g} kW"},
        {"name": "Energy balance", "passed": all(abs(r["energy_balance_error_kwh"]) < EPS for r in rows), "detail": "Every hour: supply + explicit unmet energy = scheduled demand"},
        {"name": "Fuel limits", "passed": all(r["generator_fuel_end_pct"] >= -EPS for r in rows), "detail": "Generator output bounded by fuel and capacity; generator never charges battery"},
        {"name": "Schedule / edits", "passed": not any(w["severity"] == "error" for w in warnings), "detail": "Daily flexible energy conserved; invalid requests block approval"},
        {"name": "Closing battery stock", "passed": closing_ok, "detail": f"Target {closing_target:.1f} kWh restored" if closing_target is not None else "No terminal recharge requirement during outage / grid-charge-off mode"},
    ]
    for check in checks:
        if not check["passed"]:
            warnings.append(issue(f'{check["name"]} failed: {check["detail"]}.', "hard_constraint", severity="error"))
    for row in rows:
        for message in row["warnings"]:
            warnings.append(issue(message, "outage_or_comfort", row["hour"], "error" if row["critical_status"] == "at_risk" or row["comfort_status"] == "violation" else "warning"))
    if not settings.allow_grid_charging and soc < start_soc - EPS:
        warnings.append(issue("Ending battery stock is lower than opening stock. Today's purchase savings include use of previously stored energy; replacement energy is not priced today.", "stock_difference"))
    shifted = sum(abs(laundry[h] - raw[h]["parts"]["laundry"]) + abs(heating[h] - raw[h]["parts"]["water_heating"]) + abs(hvac[h] - raw[h]["parts"]["hvac"]) for h in range(24)) / 2
    summary = {
        "cost_inr": total("cost_inr"), "emissions_kg_co2e": total("emissions_kg_co2e"),
        "grid_emissions_kg_co2e": total("grid_emissions_kg_co2e"), "generator_emissions_kg_co2e": total("generator_emissions_kg_co2e"),
        "peak_grid_kw": max(r["grid_to_load_kwh"] + r["grid_to_battery_kwh"] for r in rows),
        "demand_kwh": total("demand_kwh"), "solar_available_kwh": total("solar_available_kwh"),
        "solar_to_load_kwh": total("solar_to_load_kwh"), "solar_to_battery_kwh": total("solar_to_battery_kwh"),
        "solar_curtailed_kwh": total("solar_curtailed_kwh"), "grid_to_load_kwh": total("grid_to_load_kwh"),
        "grid_to_battery_kwh": total("grid_to_battery_kwh"), "battery_discharge_to_load_kwh": total("battery_discharge_to_load_kwh"),
        "battery_soc_start_kwh": start_soc, "battery_soc_end_kwh": soc,
        "battery_soc_min_kwh": min([start_soc] + [r["battery_soc_end_kwh"] for r in rows]),
        "battery_charging_loss_kwh": total("battery_charging_loss_kwh"), "battery_discharging_loss_kwh": total("battery_discharging_loss_kwh"),
        "generator_to_critical_kwh": total("generator_to_critical_kwh"), "generator_to_hvac_kwh": total("generator_to_hvac_kwh"),
        "generator_fuel_used_litres": total("generator_fuel_used_litres"),
        "generator_fuel_end_pct": fuel / settings.generator_tank_litres * 100,
        "flexible_shifted_kwh": shifted, "paused_noncritical_kwh": total("paused_noncritical_kwh"),
        "critical_unserved_kwh": total("critical_unserved_kwh"), "unserved_kwh": total("unserved_kwh"),
        "critical_status": "protected" if total("critical_unserved_kwh") <= EPS else "at_risk",
        "comfort_status": "within_limits" if all(r["comfort_status"] == "within_limits" for r in rows) else "violation",
        "terminal_target_kwh": closing_target,
    }
    return {"hours": rows, "summary": summary, "checks": checks, "warnings": warnings,
            "valid": all(c["passed"] for c in checks)}


def comparison(plan, baseline):
    recommended, usual = plan["summary"], baseline["summary"]
    savings = {key: usual[key] - recommended[key] for key in ("cost_inr", "emissions_kg_co2e", "peak_grid_kw")}
    savings["cost_pct"] = savings["cost_inr"] / usual["cost_inr"] * 100 if usual["cost_inr"] else 0
    return {"recommended": recommended, "baseline": usual, "savings": savings,
            "recommended_checks": plan["checks"], "baseline_checks": baseline["checks"],
            "baseline_valid": baseline["valid"], "recommended_valid": plan["valid"],
            "method": "Same date, adjusted forecast, opening battery, capacities, comfort and outage rules. Usual routine uses solar first, grid next, and no intentional cost/carbon battery dispatch or load shifting. Outage recovery still moves paused laundry/heating within the same windows. All grid charging and diesel costs/emissions are counted at draw time.",
            "boundary_note": "Demand budgets are held constant; noncritical outage pauses are explicit. Compare closing battery stock as well as today's purchases. Ordinary recommended plans with grid charging restore their opening stock. Different HVAC timing can change comfort feasibility in a stress case."}


def explain(plan, settings):
    s, rows = plan["summary"], plan["hours"]
    cheap = sorted(rows, key=lambda r: r["grid_price_inr_per_kwh"])[:3]
    clean = sorted(rows, key=lambda r: r["grid_carbon_kg_per_kwh"])[:3]
    return [
        {"question": "Use solar now or save it?", "answer": f'{s["solar_to_load_kwh"]:.0f} kWh goes directly to the hospital; {s["solar_to_battery_kwh"]:.0f} kWh charges storage; {s["solar_curtailed_kwh"]:.0f} kWh is curtailed. Direct use avoids storage losses.'},
        {"question": "How much battery stays in reserve?", "answer": f'Ordinary reserve is {settings.reserve_pct:g}% ({settings.battery_capacity_kwh * settings.reserve_pct / 100:.0f} kWh). The lowest planned level is {s["battery_soc_min_kwh"]:.0f} kWh. The outage generator-start threshold stays fixed at 10%.'},
        {"question": "Should the battery charge from the grid?", "answer": f'{s["grid_to_battery_kwh"]:.0f} kWh of grid charging is scheduled. The heuristic compares later cost/carbon benefit after {settings.charge_efficiency * settings.discharge_efficiency * 100:.1f}% round-trip efficiency, reserve needs, and closing stock.'},
        {"question": "When is grid power cheaper or cleaner?", "answer": f'Cheaper: {", ".join(f"{r["hour"]:02d}:00 (₹{r["grid_price_inr_per_kwh"]:.2f})" for r in cheap)}. Cleaner: {", ".join(f"{r["hour"]:02d}:00 ({r["grid_carbon_kg_per_kwh"]:.2f} kg/kWh)" for r in clean)}.'},
        {"question": "Which activities can move?", "answer": f'{s["flexible_shifted_kwh"]:.0f} kWh changes timing across HVAC, laundry and water heating versus the original routine. Daily activity budgets are conserved. Critical medical demand never moves.'},
        {"question": "Are the hard limits respected?", "answer": f'Critical loads: {s["critical_status"].replace("_", " ")}. Comfort: {s["comfort_status"].replace("_", " ")}. {sum(c["passed"] for c in plan["checks"])}/{len(plan["checks"])} expected-case checks pass. A separate high-demand / low-solar replay is checked before approval.'},
    ]


def create_plan(forecast, settings, start_soc, hourly_edits=(), refill_hour=None, refill_to_pct=100, include_suggestions=True):
    plan = simulate(forecast, settings, start_soc, hourly_edits, refill_hour=refill_hour, refill_to_pct=refill_to_pct)
    baseline = simulate(forecast, settings, start_soc, baseline=True, refill_hour=refill_hour, refill_to_pct=refill_to_pct)
    risk = simulate(forecast, settings, start_soc, hourly_edits, stress=True, fixed_rows=plan["hours"], refill_hour=refill_hour, refill_to_pct=refill_to_pct)
    plan["expected_case_valid"] = plan["valid"]
    plan["risk_case"] = {"label": "High demand + low solar replay", "valid": risk["valid"],
                         "summary": risk["summary"], "warnings": risk["warnings"], "checks": risk["checks"],
                         "method": "Replays the planned battery and flexible-load schedule with high-band demand / occupancy and low-band solar. Available grid or generator covers residual load; no new cost dispatch is optimized."}
    # A known critical/comfort failure in the adverse replay blocks approval.
    plan["valid"] = plan["valid"] and risk["valid"]
    if not risk["valid"]:
        plan["warnings"].append(issue("The high-demand / low-solar replay fails a hard constraint. Review the Risk case panel; approval is blocked.", "risk_case", severity="error"))
    plan["warnings"] += [issue(w, "forecast_adjustment") for w in forecast["warnings"]]
    plan["comparison"] = comparison(plan, baseline)
    plan["explanations"] = explain(plan, settings)
    plan["suggestions"] = []
    if include_suggestions:
        candidates = [
            ("cost", "Compare the lowest-cost goal", {"objective": "cost"}, "Weights the same forecast toward rupee cost; critical and comfort rules remain hard constraints."),
            ("emissions", "Compare the lowest-emissions goal", {"objective": "emissions"}, "Weights hourly grid carbon intensity after battery losses; includes generator emissions."),
            ("grid", "Review grid charging permission", {"allow_grid_charging": not settings.allow_grid_charging}, "Tests the value of charging at another hour, including losses, reserve protection and terminal stock."),
        ]
        for key, title, patch, why in candidates:
            if all(getattr(settings, k) == v for k, v in patch.items()):
                continue
            candidate_settings = Settings(**(settings.model_dump() | patch))
            alternative = create_plan(forecast, candidate_settings, start_soc, hourly_edits, include_suggestions=False)
            plan["suggestions"].append({"id": key, "title": title, "reason": why,
                "settings_patch": patch, "safety_label": "Checks pass in expected and risk cases" if alternative["valid"] else "Infeasible alternative — approval would be blocked",
                "valid": alternative["valid"], "estimated_effect": {
                    "cost_inr": alternative["summary"]["cost_inr"] - plan["summary"]["cost_inr"],
                    "emissions_kg_co2e": alternative["summary"]["emissions_kg_co2e"] - plan["summary"]["emissions_kg_co2e"],
                    "peak_grid_kw": alternative["summary"]["peak_grid_kw"] - plan["summary"]["peak_grid_kw"],
                }})
    return plan
