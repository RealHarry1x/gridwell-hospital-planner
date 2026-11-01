# Shared frontend / Python API contract · v1.0

Base path: `/api`. Dates use `YYYY-MM-DD`; hours are integers 0–23. Same-day
window ends may be 24. Money is INR, energy kWh, power kW, emissions kg CO2e,
intensity kg CO2e/kWh, temperature °C. Hospital energy data is simulated;
optional external weather forecasts and ordinary AI Guide chat are labeled
separately. Weather inputs do not turn plan outputs into live hospital data.

## Common JSON shape

Every successful JSON route returns:

```json
{
  "data": {},
  "meta": { "simulated": true, "mode": "local-demo", "api_version": "1.0" }
}
```

`data` may be an object, array, or `null` for “no stored draft”. Errors use
HTTP 4xx and this shape (validation can include `details`):

```json
{
  "error": {
    "message": "Check the highlighted request values.",
    "details": [{ "field": "body.settings.reserve_pct", "message": "Input should be greater than or equal to 10" }]
  }
}
```

422 = invalid inputs; 404 = missing record; 403 = protected preset / unrelated
cross-origin write; 409 = invalid/stale plan or outdated revision. The optional
CSV export returns CSV instead of this JSON envelope.

## Routes

| Method | Route | Request / result |
| --- | --- | --- |
| GET | `/config?date=YYYY-MM-DD` | Settings defaults, simulated assumptions, hard rules, day templates, India-local today/tomorrow, carry, and non-secret assistant configuration status. |
| GET | `/forecast?date=YYYY-MM-DD&day_type=normal` | Original forecast; optional `solar_capacity_kwp`, `outage_start`, `outage_end` query values. |
| GET | `/weather?date=YYYY-MM-DD` | 24 raw hourly Open-Meteo values or `hours: null` on fallback, plus source, location and fetched timestamp. |
| GET | `/demand-context?date=YYYY-MM-DD&day_type=normal&plan_id=...` | Up to seven earlier recorded days, backend average and honest explanation of the seeded demand model. Optional plan ID uses that saved forecast. |
| POST | `/forecast/verify` | PlanRequest; returns original forecast plus adjustments, without saving a plan. |
| POST | `/plans/generate` | PlanRequest; creates a draft, returns Plan, HTTP 201. |
| POST | `/plans/{plan_id}/recalculate` | Full PlanRequest for the same date; replaces draft calculations and increments revision. |
| POST | `/plans/{plan_id}/approve` | `{ "revision": 1 }`; checks expected + adverse feasibility, current carry and revision; writes simulation history. |
| GET | `/plans/{date}/comparison?plan_id=...` | Same-input recommended/baseline summaries, checks, savings and boundary notes. Optional ID selects the exact draft. |
| GET | `/trends?days=7` | Up to 1–60 recent recorded days with synthetic actuals, demand/cost/CO2e/solar/occupancy/error and battery carry. |
| GET | `/energy-breakdown?date=YYYY-MM-DD&plan_id=...` | Backend compartment totals (`consumption`) and source summary (`supply`). |
| POST | `/outage/simulate` | OutageRequest; independent full-day rehearsal, never saved to carry. |
| GET | `/presets` | Array of built-in + custom presets. |
| POST | `/presets` | PresetRequest; creates a custom preset, HTTP 201. |
| PUT | `/presets/{preset_id}` | PresetRequest; updates custom preset only. |
| DELETE | `/presets/{preset_id}` | Deletes custom preset only; returns `{ "deleted": "..." }`. |
| POST | `/assistant` | Same question / selected-plan request; read-only Gemini explanation when available, otherwise a labeled local sample reply. |
| GET | `/health` | Local server status. |
| GET | `/plans?date=YYYY-MM-DD` | Latest stored Plan or `null`; used to restore the workspace after reload. |
| GET | `/plans/{plan_id}` | Exact stored Plan. |
| GET | `/plans/{plan_id}/export.csv` | Download scalar hourly schedule columns as CSV. |
| POST | `/demo/reset` | `{ "initial_soc_pct": 70 }`; clears plans/history, reseeds first-day assumption, keeps custom presets. |

`day_type` is `normal`, `heatwave`, `low_solar`, or `grid_outage`. Objectives are
`balanced`, `cost`, `emissions`, or `custom`. Full validated input definitions
and defaults are in `backend/app/models.py` and `/docs` while the app is running.

## PlanRequest

Send a full snapshot on recalculation, including all settings / overrides you
want to retain. Omitted settings use defaults; requests reject unknown fields.

```json
{
  "date": "2026-11-01",
  "day_type": "normal",
  "settings": {
    "objective": "balanced",
    "reserve_pct": 20,
    "allow_grid_charging": true,
    "comfort_min_c": 22,
    "comfort_max_c": 26,
    "laundry_start": 8,
    "laundry_end": 17
  },
  "forecast_overrides": [
    { "hour": 12, "field": "demand_kwh", "value": 270 }
  ],
  "hourly_edits": [
    { "hour": 10, "laundry_kwh": 30 }
  ]
}
```

Settings are optional; `/config.data.defaults` returns a complete settings
object for the frontend to send. Supported fields:

| Group | Fields |
| --- | --- |
| Goal | `objective`, `cost_weight`, `carbon_weight` (custom weights must have a positive sum) |
| Storage | `battery_capacity_kwh`, `battery_power_kw`, `reserve_pct`, `charge_efficiency`, `discharge_efficiency`, `allow_grid_charging` |
| Solar / comfort | `solar_capacity_kwp`, `comfort_min_c`, `comfort_max_c` |
| Flexible windows | `laundry_start`, `laundry_end`, `water_heating_start`, `water_heating_end`, `flexible_power_kw` |
| Outage | `outage_start`, `outage_end` |
| Generator | `generator_capacity_kw`, `generator_tank_litres`, `generator_fuel_pct`, `generator_litres_per_kwh`, `generator_fuel_inr_per_litre`, `generator_emissions_kg_per_litre`, `generator_available`, `generator_failure_hour` (nullable) |

`forecast_overrides[].field` is `demand_kwh`, `occupancy_pct`, or `solar_kwh`.
An occupancy adjustment must be 0–100. One edit per hour/field is allowed.
Ranges remain immutable. Demand cannot remove the original critical floor.

`hourly_edits` accepts at most one object per hour, with any subset of
`hvac_kwh`, `laundry_kwh`, `water_heating_kwh`, `grid_charge_kwh`, and
`battery_discharge_kwh`. Numbers are nonnegative. Critical demand is not an
editable schedule field. Outage battery dispatch is protected; an attempted
manual override is flagged rather than silently applied. Unknown “disable
safety” flags are rejected by Pydantic.

## Forecast response

`data` contains `date`, `day_type`, `hours` (24 rows), `daily`, `adjustments`,
`warnings` and `source`. It also includes `weather_hours` (24 raw dictionaries
or null), `weather_strip` and `planning_guidance`. Every ranged property uses exactly:

```json
{ "low": 180, "expected": 200, "high": 220 }
```

The example numbers above describe the shape, not a fixed returned forecast.
Each hourly row has:

- `hour`, `demand_kwh` (range), `occupancy_pct` (range), `solar_kwh` (range).
- `critical_demand_kwh` (expected scalar), `flexible_loads_kwh` with `hvac`,
  `laundry`, `water_heating`; `components_kwh` adds `critical`, `labs`,
  `lighting`, `other`.
- `grid_price_inr_per_kwh`, `grid_carbon_kg_per_kwh`, `grid_available`.
- `outdoor_temperature_c` (after scenario modifiers), `base_temperature_c`,
  `cloud_cover_pct`, `radiation_wm2`, `scenario`, `weather` (source label).
- Optional `adjusted` map beside the original range, such as
  `{ "demand_kwh": 270 }`.

`daily` holds summed demand/solar ranges, average occupancy ranges, and
`cheapest_hours` / `cleanest_hours` arrays. These are original forecast values;
the generated plan uses the adjustments. Example adjustment record:

```json
{
  "hour": 12,
  "field": "demand_kwh",
  "original": 250,
  "adjusted": 400,
  "outside_range": true
}
```

`source` is now an object containing `description`, `demand_source`,
`weather_source`, `weather_location`, `weather_fetched_at` (nullable),
`solar_method`, `solar_performance_ratio: 0.8` and `range_note`.
`weather_source` is exactly `Open-Meteo live forecast` or
`Synthetic fallback (live weather unavailable)`. Older saved plans may still
have their original string `source`; the frontend handles both without a fetch.

Raw weather rows are `{hour, temperature_c, cloud_cover_pct, radiation_wm2}`.
`weather_strip` adds the scenario temperature and estimated hourly solar energy,
already calculated in Python. `daily` adds `outdoor_min_c`, `outdoor_max_c`,
`hvac_kwh` and `solar_capacity_kwp`. No browser calculation is needed.
`planning_guidance` contains a weather-based `suggested_day_type`, disclosed
`reason`/`method`, `selected_effect`, optional `settings_patch`, human-readable
`settings_preview`, `comfort_note` and `apply_notice`. It is advisory and does
not apply settings or claim Gemini predicted the weather.

`POST /forecast/verify` accepts optional `plan_id` in addition to PlanRequest
fields. With a plan ID, its date must match and its weather snapshot is reused.
Verification never saves a plan. Recalculation always pins the selected plan's
weather, including a saved offline fallback; create a new plan for fresh inputs.

The weather endpoint keeps the normal envelope. Its `data` is
`{date, hours, source, location, fetched_at, note}`. `meta.simulated` is false
for an external weather forecast and true when no weather is available.
Other planning routes keep `meta.simulated: true`. Weather failures return
HTTP 200 with a fallback source, while malformed route dates still return 422.
The three-day provider horizon starts at today's Asia/Kolkata date.

## Plan response

Plan fields:

- `id` (UUID string), `date`, `day_type`, `revision`, `status` (`draft`,
  `approved`, `stale`), `approved_at` (nullable).
- `settings`, `input` (full PlanRequest), `forecast` (original plus adjustments).
- `battery_carry`: `energy_kwh`, `from_date` (nullable), `source`, `note`,
  and `first_day` on stored plans.
- `hours` (24 schedule rows), `summary`, `checks`, `warnings`,
  `expected_case_valid`, `valid` (expected and adverse cases must both pass).
- `risk_case`: `label`, `method`, `valid`, `summary`, `checks`, `warnings`.
- `comparison`, `explanations` (`question`, `answer`), `suggestions`.
- After recalculation, `changes` contains **new minus previous** cost,
  CO2e, grid peak and closing battery values, calculated in Python.
- `calculation` includes `calculated_at`, `same_inputs` and a result `message`.
  Matching outputs for unchanged inputs are expected; revision still advances.
- `display` supplies backend-calculated normal-reserve/threshold energy,
  generator total energy and the selected goal description. Hourly rows also
  contain `grid_draw_kwh` and `generator_total_kwh` for display.

Every hourly schedule row includes these exact names:

| Category | Properties |
| --- | --- |
| Demand | `hour`, `occupancy_pct`, `demand_kwh`, `critical_demand_kwh`, `flexible_loads_kwh`, `components_kwh` |
| Solar | `solar_available_kwh`, `solar_to_load_kwh`, `solar_to_battery_kwh`, `solar_curtailed_kwh` |
| Grid | `grid_to_load_kwh`, `grid_to_battery_kwh`, `grid_price_inr_per_kwh`, `grid_carbon_kg_per_kwh`, `grid_available` |
| Storage | `battery_discharge_to_load_kwh`, `battery_soc_start_kwh`, `battery_soc_end_kwh`, `battery_charging_loss_kwh`, `battery_discharging_loss_kwh` |
| Generator | `generator_to_critical_kwh`, `generator_to_hvac_kwh`, `generator_running`, `generator_fuel_start_pct`, `generator_fuel_end_pct`, `generator_fuel_used_litres`, `generator_fuel_added_litres` |
| Accounting | `cost_inr`, `emissions_kg_co2e`, `grid_emissions_kg_co2e`, `generator_emissions_kg_co2e`, `energy_balance_error_kwh` |
| Safety | `temperature_c`, `comfort_status`, `critical_status`, `unserved_kwh`, `critical_unserved_kwh`, `paused_noncritical_kwh`, `warnings` (string array) |

`comfort_status` is `within_limits` or `violation`; `critical_status` is
`protected` or `at_risk`. A top-level warning is:

```json
{
  "message": "Requested battery charging exceeds its power or capacity limit.",
  "code": "battery_edit",
  "hour": 12,
  "severity": "error"
}
```

Checks are `{ "name": "Critical loads", "passed": true, "detail": "..." }`.
Summary sums hourly flows/cost/emissions, reports peak/min/start/end storage,
fuel, flexible activity moved, paused and unserved demand, safety statuses,
and `terminal_target_kwh` (nullable). Do not recompute those in the frontend.

## Approval example

```http
POST /api/plans/PLAN_ID/approve
Content-Type: application/json
```

```json
{ "revision": 2 }
```

A successful `data` is the approved Plan with `status: "approved"`,
`approved_at`, `approval_notice`, and `invalidated_future_plan_ids`. Repeating
the same approval is idempotent. A hard failure or changed carry/revision gets
409. No hardware command is sent. Future stale drafts must be recalculated.

## Comparison and suggestions

Comparison contains `recommended`, `baseline` (summaries), `savings`,
`recommended_checks`, `baseline_checks`, `recommended_valid`, `baseline_valid`,
`method`, `boundary_note`. Savings are **baseline minus recommended** for
`cost_inr`, `emissions_kg_co2e`, `peak_grid_kw`; positive means reduction.
`cost_pct` uses baseline cost. Cost can increase and peak can rise.

A suggestion has `id`, `title`, `reason`, `settings_patch`, `valid`,
`safety_label`, and `estimated_effect`. Effects are **alternative minus current**
cost / emissions / peak, so negative means reduction. To apply, merge its
`settings_patch` into the current settings and submit a full recalculation.
The comparison's `recommended_valid` uses the expected + adverse approval
result, while baseline checks describe its expected-case routine.

## Outage rehearsal example

OutageRequest extends PlanRequest. The endpoint always uses the grid-outage
scenario. Extra fields: `initial_soc_pct_override` (nullable; beginning of
day), `refill_hour` (nullable) and `refill_to_pct` (default 100).
Optional `plan_id` pins the rehearsal's weather to the selected stored plan.

```json
{
  "date": "2026-11-01",
  "day_type": "grid_outage",
  "settings": {
    "outage_start": 0,
    "outage_end": 12,
    "generator_capacity_kw": 220,
    "generator_failure_hour": 1,
    "generator_fuel_pct": 35
  },
  "initial_soc_pct_override": 10,
  "refill_hour": 3,
  "refill_to_pct": 100
}
```

Response contains the same calculation/summary/check/risk fields as a Plan,
plus `settings`, `date`, `day_type`, `battery_carry`, `note`, and
`saved_to_history: false`. It has no stored ID/approval/revision. Refill is an
explicit simulated human report. Failure means a refill alone will not make
the generator operational. No approval/carry is changed by rehearsal.
The response also includes its `forecast`, `display` values and `rehearsal`
details: first generator-start hour, first critical-shortfall hour (nullable),
failure/refill inputs and calculation timestamp. Rehearsal controls are local
to that page and never mutate the day-plan draft.

## Preset example

```json
{
  "name": "Team balanced reserve",
  "description": "Extra ordinary reserve with a wider laundry window.",
  "settings": {
    "objective": "balanced",
    "reserve_pct": 30,
    "laundry_start": 7,
    "laundry_end": 18,
    "allow_grid_charging": true
  }
}
```

Returns `id`, `name`, `description`, **complete** `settings`, and
`built_in: false`. Built-in IDs start with `builtin-` and are immutable.
The frontend sends the complete edited settings to avoid losing hidden values.
Built-in entries additionally contain `scope: "goal_only"`, a descriptive
`goal`, and `settings_patch: {objective: ...}`. Selecting a built-in goal changes
only the priority; it preserves equipment, comfort limits, windows and hourly
edits. A custom preset remains a full settings snapshot and is explicitly
loaded into the draft. Editing a saved preset does not load it automatically.

## Reset and demand context

`POST /demo/reset` retains its request. The result now reports `deleted_plans`,
`deleted_history_records`, `kept_custom_presets`, `history_records_created`,
`first_history_date`, `first_history_battery_kwh` and an explanatory `note`.
The frontend clears drafts/edits, restores default controls and shows these
counts. Reset does not randomize a date-seeded forecast or remove custom presets.

Demand context returns `{date, days, average_kwh, forecast_expected_kwh,
history_used_for_forecast: false, method, source}`. Each day is
`{date, energy_kwh, source}`. An empty history has `average_kwh: null`. All
history is simulated; it is not training data for the current demand model.

## AI Guide: Gemini with sample fallback

The existing **`POST /api/assistant`** request and common JSON envelope are
preserved. The browser calls only this Python endpoint, never Google directly.
The client sends no key, provider settings, database history or conversation
history. Plan IDs are resolved by the backend; the model never fetches records.

```json
{ "message": "Are critical loads protected?", "plan_id": "PLAN_ID" }
```

Successful Gemini response data (answer text varies; shape shown below):

```json
{
  "mode": "Gemini mode · simulated data",
  "answer": "An explanation using only the supplied simulated plan values and checks.",
  "context": { "plan_id": "PLAN_ID", "revision": 2, "date": "2026-11-01" },
  "provider": "google-genai",
  "model": "gemini-3.8-flash",
  "fallback_reason": null,
  "notice": "Gemini explanation of simulated app data. The recorded backend plan remains authoritative."
}
```

Without `plan_id`, send `date` and optional `day_type`; the response explains
the original forecast. Its `context` remains `{ "date": "YYYY-MM-DD" }`.
There is no generated dispatch/cost/saving without a plan; the guide must say
when data are missing. Uncalculated edits are not supplied as an approved result.

Sample/fallback response data:

```json
{
  "mode": "Sample mode · simulated data",
  "answer": "A deterministic local reply using the selected backend data.",
  "context": { "plan_id": "PLAN_ID", "revision": 2, "date": "2026-11-01" },
  "provider": "deterministic-template",
  "fallback_reason": "not_configured",
  "notice": "Gemini is not configured on the Python server. Using a local sample response."
}
```

Fallbacks are normal **HTTP 200** assistant results; the rest of the app keeps
working. Reasons are `not_configured`, `invalid_configuration`, `timeout`,
`quota`, `model_unavailable`, `unavailable`, `empty_response`, `privacy`,
`read_only`, or `outside_scope`. `notice` is fixed friendly text, never a raw
provider exception. `model` is present on a successful Gemini reply only.
No error or response includes the credential. Missing-plan (404) remains for
energy questions that select an absent plan. General chat/greetings do not
resolve an irrelevant `plan_id`. Invalid-request (422) behavior is unchanged.

`GET /api/config` adds this safe status block:

```json
{
  "assistant": {
    "configured": true,
    "status": "gemini_configured_unverified",
    "notice": "Gemini is configured; the mode on each reply confirms whether it succeeded."
  }
}
```

With no usable server configuration, `configured` is false and `status` is
`sample`. This status checks local configuration only, sends no Gemini request,
and exposes no secret. **A successful reply's `provider: "google-genai"` and
`mode: "Gemini mode · simulated data"` confirm actual use.** A prior successful
reply does not mean a later failed request is also Gemini; each message retains
its own mode/notice/context.

### Server configuration, data minimization and authority

- Only Python reads `GEMINI_API_KEY` and `GEMINI_MODEL`. The model defaults to
  stable `gemini-3.8-flash`, confirmed in the official list on 2026-10-31.
  Actual access/quota depends on the key. Another fixed stable text ID can be
  configured; the app does not silently switch to an unrelated model.
- Optional root `hackathonv1/.env` loading is explicit, has no variable
  interpolation, reads the two Gemini settings, and respects existing
  server environment values. `.env` remains ignored; `.env.example` has no key.
  Restart Python after changing local configuration.
- Hospital questions use a local energy-only interpretation and optional
  `HH:00` focus hours plus allowlisted simulated values. General questions send
  the current message after sensitive-content checks, with **no hospital data**.
  Previous chat, full records/database history and credentials are not sent.
  Recognized sensitive or hospital-action requests receive local replies.
- Projected values can include original/adjusted demand, occupancy and solar
  ranges; selected hourly battery/source/tariff/carbon/flexible-load values;
  plan totals, normal reserve, current status and expected/adverse hard checks;
  and the backend's actual same-input baseline comparison. Arbitrary stored
  warning strings/preset descriptions/history are not forwarded.
- Gemini is told to use only supplied numbers for hospital facts and label
  those as simulated. General knowledge is labeled separately. It must disclose
  absent data and never compute a new hospital plan, approve, change settings,
  control equipment, refuel, or override a hard rule. It has no tools or write
  functions. The assistant module does not import the planner or storage.
  The optimizer's hard constraints remain unchanged. Optional weather is an
  input to the forecast; explanations are text, not commands or safety certification.
- SDK HTTP timeout: 45 seconds per call. Overall reply deadline: 100 seconds,
  including a 2-second delay and one retry on HTTP 503/504 only (at most two
  calls with the same model/context). SDK-internal retries remain disabled;
  other failures go directly to Sample mode. A final 504 uses reason `timeout`.
  No automatic continuation; concise answers target 2–5 sentences / 120 words,
  with at most 1,500 total output tokens including thinking. Empty,
  blocked or incomplete provider output uses Sample mode. Gemini calls use the
  API project's quota/billing; timeouts or local fallback do not guarantee that
  a request already processed by Google was free.

See the README's **Optional Gemini setup** section for local `.env`, model
selection, restart and mode-verification instructions.

### Friendly greetings and general chat

The request schema is unchanged. Responses add `scope` (`greeting`, `general`,
`gridwell`) and `uses_simulated_data` (boolean). The assistant endpoint's
`meta.simulated` matches that boolean; other app routes are unchanged.

For `{ "message": "hi" }`, `data` is:

```json
{
  "answer": "Hi! What can I help you with?",
  "mode": "Local reply · general chat",
  "provider": "deterministic-template",
  "context": {},
  "scope": "greeting",
  "uses_simulated_data": false,
  "fallback_reason": null,
  "notice": "Answered locally; no Gemini request or hospital data was needed."
}
```

Ordinary questions such as `{ "message": "What is Python?" }` use
`scope: "general"`, `uses_simulated_data: false`, `context: {}` and
`mode: "Gemini mode · general chat"` on Gemini success. The provider payload
is just `scope` and the current question, with no `app_data`, even if the
browser sent a selected plan ID. It can use ordinary knowledge/reasoning but
must admit uncertainty and cannot claim browsing or live hospital data.

General failures retain `provider: "deterministic-template"` and a friendly
Sample-mode answer. A small offline FAQ/arithmetic set is supported; unknown
general answers admit the limitation. Greetings are intentional local replies,
not failed Gemini requests. Operational refusals and secret redaction remain.

Energy questions keep their original selected plan/date/revision context,
`mode` suffix `simulated data`, and now also return `scope: "gridwell"` and
`uses_simulated_data: true`. Replies use backend numbers, not general model
knowledge as a substitute for missing hospital readings. No chat route has
tools or mutation access, and general question handling does not import or
change the optimizer or safety rules.

### Terminal diagnostics (no public API change)

The Python process now logs safe `[Gridwell AI]` events through the standard
Uvicorn terminal logger. Startup includes the root `.env` location/status,
boolean key presence, key/model source and configured model. These private
diagnostic fields are not added to `GET /api/config` or assistant JSON.

API failures include the real HTTP status when the SDK supplies one, symbolic
API status, exception type and a sanitized provider message. Full exception
strings, HTTP headers/bodies and request/reply content are not logged. Keys,
credential-like values, credential-bearing URLs and other common secret forms
are redacted before constructing the LogRecord. The browser retains the same
fixed friendly `notice` and Sample-mode envelope.

Current GenerateContent responses are read from the primary candidate's
non-thinking text parts. Only a complete usable explanation is returned;
blocked, tool/code, empty or `MAX_TOKENS` responses retain the `empty_response`
fallback and log their finish/block reasons and numerical thought-token count.
Other candidates do not override a valid primary response. Missing HTTP status
is logged as `not_reported`, never a guessed 400/429. A successful app fallback
HTTP 200 remains distinct from Google's error status in the terminal line.
