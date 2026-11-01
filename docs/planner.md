# How the planner works

The planner in `backend/app/planner.py` is an understandable deterministic
look-ahead **heuristic**. It does not prove optimality. No neural network,
reinforcement learning, solver service or external AI is used.

## 1. Forecast and adjustments

A SHA-256 date seed creates stable simulated hospital demand, occupancy, tariffs
and carbon intensity. Optional hourly Open-Meteo forecasts supply outdoor
temperature, cloud cover and shortwave radiation for the selected date. The
public endpoint uses Pune (18.52, 73.86), a three-day horizon and Asia/Kolkata;
server/root `.env` values `WEATHER_LAT` / `WEATHER_LON` can change coordinates.
The backend has a 10-second HTTP timeout and one-hour in-memory cache, including
failures. Invalid/unavailable weather or dates outside that horizon use the
unchanged deterministic synthetic profile. No key or Gemini call is needed.

When weather is available, expected hourly solar energy is
`solar_capacity_kwp * (radiation_wm2 / 1000) * SOLAR_PERFORMANCE_RATIO`, where
`SOLAR_PERFORMANCE_RATIO = 0.8`. Open-Meteo shortwave radiation is a preceding-hour
mean in W/m², used here as a representative one-hour input. This horizontal-
radiation approximation does not model panel tilt, shading or inverter detail.
It estimates potential generation, not measured production or electricity used.

Day templates remain explicit modifiers on that baseline: heatwave adds 7°C
and multiplies the simulated HVAC demand by 1.55; low-solar multiplies the
baseline solar estimate by 0.24; outage removes grid availability inside the
operator's interval. All scenarios share the protected medical base demand.
Indoor comfort bounds remain operator-selected; changing the weather never
automatically loosens them. Demand, occupancy and solar retain their original
low/expected/high bands for adverse checks, although the Overview graph no
longer displays the range decoration. Bands are illustrative, not calibrated
confidence intervals.

A saved forecast contains raw `weather_hours`, display-ready `weather_strip`
and `source.weather_source`, location and fetched timestamp. New forecasts can
fetch the current cached weather. Saved-plan reload, verification and
recalculation reuse the stored raw snapshot, even if the provider later changes,
the app restarts or a previously offline forecast becomes online. Changing
array size recomputes solar from those same stored radiation values. Old plans
without weather snapshots stay on their original synthetic basis. Historical
seed records always pass an explicit synthetic snapshot and never fetch weather.

The seven-day demand popup shows recorded simulated energy and a backend
average for context. Demand still starts from the brief's 5,200 kWh reference
with date/scenario variation; it is not trained on those seven records.

The optional day suggestion uses disclosed demo thresholds: base-weather peak
at least 35°C suggests a heatwave test; otherwise mean daylight cloud cover at
least 75% suggests a low-solar test. Weather never predicts a grid outage.
`guidance.py` supplies optional reserve/work-window patches for explicit human
review. Those patches do not change equipment, comfort bounds or hard rules.
Daily activity budgets and feasibility remain the planner's responsibility.

An adjustment is stored beside the original band, never written over it. An
out-of-band edit warns. Aggregate demand edits scale noncritical demand while
retaining at least the original medical-critical floor. A requested total
below that floor is marked infeasible. Critical demand cannot be edited as an
hourly scheduling choice.

## 2. Place flexible activities

Daily laundry and water-heating energy is conserved. First honor explicit
hourly edits, then place the remaining budget in available window hours under
the activity power limit. The recommendation prefers lower weighted cost / 
carbon hours. The baseline keeps original timing where possible and only
moves work to recover from outages / respect the same allowed window.

No window can disable critical-load protection. A window that cannot fit its
daily activity budget makes the plan infeasible; work is not silently erased.
HVAC may shift a small amount to an earlier better hour. Explicit HVAC edits
rebalance unedited hours to retain the daily cooling-energy budget.

## 3. Rank grid hours and schedule storage

The cost score is hourly price divided by that day's maximum price; the carbon
score is intensity divided by its maximum. Balanced weights them 55/45, cost
uses 100/0, emissions uses 0/100, and custom nonnegative weights are normalized.

Solar serves demand first. Solar surplus can charge the battery, bounded by
capacity, efficiency and input power; unused surplus is explicitly curtailed.

Grid charging is considered when a later expensive/dirty interval offers a
benefit after charge * discharge efficiency and a 0.035 normalized benefit
margin. This margin discourages low-value cycling; it is not a battery aging
model or monetary degradation cost. Upcoming outage energy is protected before
ordinary economic discharge. No grid charging occurs if permission is off.

The heuristic discharges in high-score hours while retaining the ordinary
reserve and outage stock. Ordinary days with grid charging enabled restore at
least opening battery stock by midnight; the look-ahead holds enough energy
to make that terminal recharge possible within remaining power limits. This
does not guarantee a globally optimal charging time or low peak draw.

## 4. Account for every flow

For each one-hour interval (all energy in kWh):

```text
hospital demand = solar_to_load + grid_to_load + battery_discharge_to_load
                + generator_to_critical + generator_to_hvac + unserved

solar available = solar_to_load + solar_to_battery + solar_curtailed

SOC_end = SOC_start
          + (solar_to_battery + grid_to_battery) * charge_efficiency
          - battery_discharge_to_load / discharge_efficiency

charging loss = charging input * (1 - charge_efficiency)
discharging loss = delivered battery output * (1/discharge_efficiency - 1)

grid draw = grid_to_load + grid_to_battery
cost = grid draw * hourly price + generator litres * assumed fuel price
CO2e = grid draw * hourly intensity + generator litres * assumed fuel factor
```

Battery discharge is **not** another grid purchase or emissions event. No
generator-to-battery flow exists. Since the interval is one hour, a 250 kW
input/output cap also limits that interval's energy to 250 kWh. Peak grid draw
is the maximum hourly grid energy divided by one hour, reported in kW.

## 5. Replay comfort

This is a deliberately simple one-zone illustrative check:

```text
mid = (comfort_min + comfort_max) / 2
T_next = mid + 0.87*(T_previous - mid)
             + 0.018*(reference_HVAC_kWh - served_HVAC_kWh)
```

The reference cooling profile includes the synthetic heatwave demand change.
With the reference HVAC served, the zone stays at the midpoint. Shifting,
under-supply or excessive cooling can cross either configured bound; those
violations are shown and block approval. This toy model is **not** a medical
comfort recommendation, calibrated thermodynamics or equipment control policy.

## 6. Outage policy

- Grid paths are zero during configured outage hours.
- Solar and battery above 10% serve medical demand first, then HVAC.
- Reaching 10% during an interval starts the available, fueled generator.
  Switching is approximated inside the hour; this is not a transient model.
- Generator supplies remaining critical load first, then HVAC, within its
  power and remaining-fuel energy cap.
- If unavailable, failed or out of fuel, remaining battery energy is released,
  still prioritizing critical demand. Any unmet critical demand or out-of-bound
  temperature is explicit infeasibility.
- Laundry and water heating move outside outage hours within their windows.
  Noncritical lab/lighting/other energy is explicitly marked as paused. Essential
  circuits are already included in the protected critical compartment.
- Fuel warnings occur at/below 40%; below 30% is urgent. Only an explicit refill
  report at a selected hour adds simulated fuel.

Ordinary reserve is checked at normal end-of-hour boundaries. At grid return,
charging may need to recover the normal reserve; if permission/power cannot
achieve it, the plan reports a failed check. During outage the 10% emergency
rule supersedes the ordinary economic reserve. Manual outage battery dispatch
cannot replace this rule.

## 7. Adverse replay and approval

The expected recommendation is replayed with high-band demand/occupancy and
low-band solar. The chosen flexible and battery schedules are retained.
Available grid / generator may supply residual demand, and permitted grid
charging may recover ordinary reserve. This is a safety fallback, not a second
round of economic optimization. It produces separate cost, peak, storage,
comfort and critical-coverage results. Either case failing a hard check blocks
approval on the server.

Occupancy is shown as a forecast/risk indicator; it is not independently
converted into extra medical demand a second time. The high-demand profile
already represents that synthetic energy uncertainty. Forecast edits are still
assumptions, and the replay does not claim coverage of every possible event.

Hourly requests that are impossible remain visible as errors even when their
executed physical flows are bounded. The draft cannot be approved by bypassing
the UI: the approval route also checks feasibility and revision.

## 8. Baseline and suggestions

The usual routine has the same adjusted forecast, starting battery, capacities,
fuel, windows, comfort and outage rules. It uses solar first and grid next;
it does not intentionally grid-charge/discharge for cost/carbon savings. It
still stores excess solar and uses storage/generator under the same outage
rules. Hospital activity budgets are conserved; shifting is what differs.

The comparison displays both closing battery states, charging losses,
noncritical outage pauses and safety checks. Outage/grid-charge-off cases may
have different ending stock, so today's purchases are not a multi-day saving
guarantee. Suggestions rerun actual alternative settings with the same forecast
and hourly edits and report signed metric changes, even if a change is worse.

## 9. SQLite carry and repeatability

Eight synthetic recent records are seeded once, starting at the adjustable
70% assumption; one includes an outage. Drafts never consume stored energy.
Only approval records a new ending stock. A selected date's opening energy is
the last recorded ending stock strictly before it. Gaps without approved
records are not silently simulated. Reset explicitly rebuilds this history.

Approving an earlier/revised day removes downstream history and marks future
drafts stale. Approval checks its revision and carried opening energy in a
SQLite write transaction. Repeating the same approval is idempotent. Full
optimistic concurrency for simultaneous draft editors is future work.

Reset reports deleted plan/history counts and preserved custom presets, then
rebuilds the same eight example days with the chosen earliest-day opening
assumption. Identical dates/inputs can produce identical numbers after reset.
The frontend refreshes its state and shows the completed reset without a full
page reload. Recalculation records a new revision/timestamp; unchanged inputs
and pinned weather are explicitly reported rather than silently appearing idle.
