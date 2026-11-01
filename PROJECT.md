# Project instructions and assumptions

## Scope

Gridwell is a local browser-based day-ahead hospital energy planning prototype.
The fictional facility is Cedar General Hospital in India. It does not access
patient data, meters, machines or utility tariffs. Optional live hourly weather
forecasts come from Open-Meteo, with an automatic synthetic fallback so the app
still works offline. A server-side Gemini adapter explains app values; local sample replies
remain available without a key and during provider failures.
No commits, pushes, publication or deployment are authorized by this project.

The supplied workspace initially contained only `Pasted text.txt` (the full
requirements) and `verdant-campus-energy-login.html` (a visual reference).
No existing GridMind / hackathonv1 source, README, PROJECT or AGENTS files were
available. A standalone FastAPI + Pydantic + SQLite backend and React/Vite
frontend were therefore implemented in this folder. The reference is not part
of the runtime and none of its campus data/login behavior was reused.

## Working principles

- Keep dispatch, accounting, constraints, comparison, alternatives and sample
  assistant context on the Python backend. Frontend arithmetic is limited to
  presentation (chart scales, source display, formatting).
- Keep code understandable. The current planner is a deterministic look-ahead
  heuristic. Never call it a certified optimizer, trained forecasting model,
  clinical controller or reinforcement-learning system.
- Keep all assumptions and units visible. `kWh` is energy; `kW` is power.
- Use deterministic date seeds. Do not replace synthetic values on reload.
- Fetch optional Open-Meteo weather only for new forecasts, cache for one hour,
  and freeze the weather values and provenance in every saved plan. Reloading,
  verifying or recalculating a stored plan must reuse that snapshot, including
  a saved synthetic fallback. Seeded historical records always stay synthetic.
- Hard constraints belong in backend code, not editable flags in a preset.
- Use the same date, adjusted forecast, opening storage and equipment/comfort
  settings for the recommended plan and usual-routine baseline.
- Mark infeasibility explicitly. Physical execution can be bounded while
  retaining an error describing an impossible request; never silently approve it.
- Approval records simulation history only. No equipment commands exist.
- Preserve later-day consistency. Re-approval of an earlier day invalidates
  downstream records and drafts; recalculation uses the new battery carry.

## Initial illustrative values

- About 5,200 kWh/day demand; 100 kWp solar; 1,000 kWh battery, 250 kW power.
- Roughly 75% occupancy with hourly low/expected/high values.
- Earliest recorded day only: adjustable 70% opening battery assumption.
- Subsequent days: prior recorded ending battery, never a per-date reset.
- 20% ordinary reserve initially; editable from 10–90%.
- 95% charge and 95% discharge efficiency initially.
- 22–26°C illustrative comfort limits; editable, not a medical standard.
- 220 kW generator; 400 L tank; 55% opening fuel; 0.27 L/kWh fuel rate;
  ₹95/L and 2.68 kg CO2e/L illustrative factors.
- Evening outage initially 18:00–23:00, configurable within the same day.

The 5,200 figure was supplied as a rounded national-survey proxy in the brief.
No survey document was supplied or independently verified. It is never
represented as a measured hospital value or as a Pune-specific average. All
other prices, carbon intensities, compartment shares and actuals are invented
simulation settings. Weather is an external forecast when available; fallback
weather and scenario modifiers remain synthetic. See README and
`docs/planner.md` for limitations.

## Non-negotiable safety behavior

1. Medical critical demand cannot be shifted/reduced by scheduling, presets or
   hourly edits. An aggregate forecast cannot delete the original critical
   demand floor; an adjustment below that floor is infeasible.
2. Check HVAC temperature against the configured comfort bounds. The thermal
   replay is illustrative; it is not a validated hospital/building model.
3. Battery energy stays in [0, capacity]; normal end-of-hour reserve and battery
   input/output power are checked. No simultaneous charging/discharging.
4. Generator stays off whenever the city grid is available.
5. During an outage, solar and battery above 10% supply critical load / HVAC.
   At 10%, start the available fueled generator. Preserve the final 10% until
   generator failure, unavailability or fuel exhaustion.
6. Supply critical demand first, then HVAC. Pause noncritical labs, lighting
   and other loads explicitly. Essential lab/lighting circuits are included
   in critical demand. Laundry/water heating must move within allowed windows
   and retain daily energy, or the draft is infeasible.
7. Respect generator power and fuel. No generator-to-battery path exists.
8. Warn at/below 40% fuel; urgent below 30%. Refills require the explicit
   simulation-only human-report action.
9. Report critical shortfalls/comfort failures. Expected-case or adverse-case
   hard failures block approval. A client cannot override this check.

## Checks and run commands

There were no pre-existing checks in the supplied files. Added checks:

- `.venv/bin/python -m pytest -q` (Windows: `.venv\Scripts\python.exe -m pytest -q`).
- `npm run build` from `frontend`.
- `npm test` from `frontend` after installing `requirements-dev.txt`: React DOM
  interaction checks with jsdom and API fixtures, without a server or internet.
- API tests cover the forecast → edit → generate → hourly edit → recalculate →
  approve → compare → breakdown → outage → assistant workflow, plus preset CRUD,
  stale approval rejection, idempotence, carried storage and explicit reset.

The README provides beginner-friendly setup and the browser walkthrough.

## Future work boundaries

Obtaining the original GridMind source is required before merging its actual
interface. Gemini explanations now use the official `google-genai` SDK, with
`GEMINI_API_KEY` and `GEMINI_MODEL` read only on Python startup from the server
environment or root `.env`. Default `gemini-3.8-flash` is a publicly listed
stable model; actual account access is confirmed by a successful reply. Never
expose credentials or raw SDK errors. The guide is read-only and has no tools,
database access, planner access or mutation API access. Hospital questions use
allowlisted simulated values and a normalized energy question. Ordinary general
questions can be sent as a single message after sensitive-content checks,
without hospital context. Do not send patient details, full records or chat
history. Local greetings and general-chat replies must be labeled separately
from simulated hospital information. Failed calls use labeled Sample
mode. Live Gemini requires the user's locally supplied key, accessible model,
network and quota/billing; automated tests use mocks. The planner's constraints
must not be changed for assistant integration. Real forecasting/control,
identity, operational safety, multi-operator concurrency and equipment
integration remain separate future work.

Server diagnostics now report key presence/source, root `.env` status and
selected model at startup, followed by actual SDK HTTP/API status and sanitized
error messages on failure. Redact known credentials and common secret forms
before logging. Never dump full exceptions, headers, response bodies, prompts,
replies or thought text. Current GenerateContent finish/block/visible-text
outcomes must be distinguished from HTTP errors; missing statuses must not be
invented. Keep those diagnostic details in the server Terminal and preserve the
existing friendly Sample-mode JSON fallback.

## Weather and operator controls

`backend/app/weather.py` requests only public coordinates, temperature, cloud
cover and shortwave radiation from Open-Meteo. Default Pune coordinates are
18.52 / 73.86; `WEATHER_LAT` / `WEATHER_LON` can be set on the server or in the
root `.env`. Use a 10-second HTTP timeout and one-hour cache. Errors, invalid
payloads and dates outside the three-day forecast return None, never an error
to the planning caller. No patient data, plan, chat or key goes to Open-Meteo.
Use a named 0.8 solar performance ratio for weather-based solar estimates.

Forecast `source.weather_source` distinguishes Open-Meteo from the synthetic
fallback. Keep raw weather in `weather_hours` and the selected scenario's
effects separate. A heatwave modifies outdoor heat and cooling demand; never
silently widen indoor comfort permissions. The weather suggestion uses visible
demo thresholds, not an invented AI prediction. The human selects a scenario
and explicitly applies any suggested working settings. Gemini can explain;
it cannot select, alter or approve a plan.

Overview's seven-day popup must disclose that recorded energy is simulated and
is context, not training data for the current seeded demand model. Graph range
decoration may be hidden; original ranges must remain available to the backend
adverse replay and optional forecast review. Duplicate comparison cards may be
removed without deleting the baseline calculation or its checks.

Reset must visibly clear drafts, approvals and edits, restore the controls and
report reset counts. It rebuilds deterministic history rather than randomizing
the same date. Recalculation must show the new revision and explicitly explain
matching results when inputs are unchanged. Goal-only presets preserve the
operator's resources; full custom presets are explicitly loaded. Outage
controls belong to an independent rehearsal and must not mutate draft settings
or carried battery history. Keep all arithmetic in the Python backend apart
from existing chart geometry and display formatting.
