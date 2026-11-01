"""Transparent planning guidance; never changes a setting or a hard rule."""

GOALS = [
    {"id": "balanced", "name": "Balanced", "weights": "55% cost · 45% emissions",
     "description": "Weigh the electricity bill and carbon intensity together.",
     "tradeoff": "A compromise; it may not give the cheapest or lowest-carbon result."},
    {"id": "cost", "name": "Lowest cost", "weights": "100% cost · 0% emissions",
     "description": "Prefer cheaper hours after allowing for battery losses and fuel cost.",
     "tradeoff": "Lower cost can mean higher emissions or a higher grid peak."},
    {"id": "emissions", "name": "Lowest emissions", "weights": "0% cost · 100% emissions",
     "description": "Prefer hours with lower estimated grid carbon intensity.",
     "tradeoff": "A cleaner schedule can cost more. These are simulated emissions."},
    {"id": "custom", "name": "Custom priorities", "weights": "Your weights, normalized by Python",
     "description": "Choose the relative importance of cost and emissions.",
     "tradeoff": "Weights affect hour ranking; all hard constraints still apply."},
]

SCENARIOS = [
    {"id": "normal", "name": "Normal day", "description": "Use the weather forecast as the base case.",
     "effect": "Standard cooling demand and solar estimate; grid available."},
    {"id": "heatwave", "name": "Heatwave", "description": "Stress-test a hotter day on top of the forecast.",
     "effect": "+7°C outdoor temperature and 55% more cooling demand; indoor limits stay yours."},
    {"id": "low_solar", "name": "Low solar", "description": "Stress-test a much weaker solar day.",
     "effect": "Solar potential is reduced to 24% of the weather-based estimate."},
    {"id": "grid_outage", "name": "Grid outage", "description": "Use this when rehearsing a known or possible power cut.",
     "effect": "Grid unavailable in your chosen interval; critical demand is protected first."},
]


def _work_window(start, end, preferred_start, preferred_end):
    candidates = [(0, start), (end, 24)]
    left, right = max(candidates, key=lambda interval: interval[1] - interval[0])
    if left == right:
        return preferred_start, preferred_end
    begin, finish = max(left, preferred_start), min(right, preferred_end)
    return (begin, finish) if finish - begin >= 3 else (left, right)


def planning_guidance(forecast, settings):
    weather = forecast.get("weather_hours")
    suggested = "normal"
    reason = "Live weather is unavailable. Start with Normal day, or explicitly choose a stress-test scenario."
    if weather:
        peak = max(row["temperature_c"] for row in weather)
        daytime = [row for row in weather if row["radiation_wm2"] > 0]
        cloud = sum(row["cloud_cover_pct"] for row in daytime) / len(daytime) if daytime else 100
        if peak >= 35:
            suggested, reason = "heatwave", f"The base weather forecast reaches {peak:g}°C. Consider a heatwave stress test."
        elif cloud >= 75:
            suggested, reason = "low_solar", f"Daylight cloud cover averages {cloud:.0f}%. Consider a low-solar stress test."
        else:
            reason = "The base weather forecast does not cross the demo heat/cloud thresholds. Normal day is a reasonable starting case."
    scenario = forecast["day_type"]
    patch = {
        "normal": {"reserve_pct": 20, "laundry_start": 8, "laundry_end": 17, "water_heating_start": 5, "water_heating_end": 22},
        "heatwave": {"reserve_pct": 30, "laundry_start": 7, "laundry_end": 16, "water_heating_start": 5, "water_heating_end": 18},
        "low_solar": {"reserve_pct": 30, "laundry_start": 9, "laundry_end": 17, "water_heating_start": 5, "water_heating_end": 20},
        "grid_outage": {"reserve_pct": 40},
    }[scenario]
    if scenario == "grid_outage":
        for activity, begin, finish in (("laundry", 8, 17), ("water_heating", 5, 22)):
            left, right = _work_window(settings.outage_start, settings.outage_end, begin, finish)
            patch[f"{activity}_start"], patch[f"{activity}_end"] = left, right
    return {
        "suggested_day_type": suggested, "reason": reason,
        "method": "Weather-based demo rules (35°C peak / 75% daylight cloud). Not an AI weather prediction or an outage warning.",
        "selected_effect": next(item["effect"] for item in SCENARIOS if item["id"] == scenario),
        "settings_patch": patch,
        "settings_preview": [f"Normal reserve: {patch['reserve_pct']}%",
                             f"Laundry: {patch['laundry_start']:02d}:00–{patch['laundry_end']:02d}:00",
                             f"Water heating: {patch['water_heating_start']:02d}:00–{patch['water_heating_end']:02d}:00"],
        "comfort_note": f"Indoor limits remain {settings.comfort_min_c:g}–{settings.comfort_max_c:g}°C. Outdoor weather changes the scenario, not the hospital's comfort permission.",
        "apply_notice": "Only applies reserve and flexible-work windows to your draft after you choose Apply. Equipment sizes, fuel, comfort limits and hard rules are kept. Recalculate to test feasibility.",
    }
