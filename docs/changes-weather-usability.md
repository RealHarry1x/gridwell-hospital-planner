# Weather and workspace usability update

## What changed for the operator

- Overview: explicit demand and solar meanings, seven-day history popup with
  the true model explanation, hourly weather/source strip and no range legend.
  Reset has its own confirmation and persistent counts; it refreshes state
  without a page reload. Deterministic forecasts are intentionally repeatable.
- Day Plan: choose a scenario, choose a goal, review resources, then calculate.
  Weather suggestions use disclosed rules; the AI Guide can explain them.
  Applying suggested reserve/work windows is an explicit action. Heatwave
  outdoor/cooling values differ while operator comfort permissions are retained.
  Recalculation shows a revision, timestamp and a same-input explanation.
  New draft with current weather requests a separate draft and keeps the old
  snapshot/record and approval history (the one-hour weather cache applies).
- Comparison: redundant Recommended/Usual safety cards removed; real baseline,
  differences and detailed table retained.
- Outage Readiness: staged local controls for cut, generator/fuel, failure and
  refill; visible result/timeline and pending-input warning. A rehearsal never
  edits the day plan or ledger.
- Presets: explained goal weights/trade-offs, resource-preserving goal changes,
  full custom inventory cards, separate editor and explicit load/delete actions.
  Trends and Energy Breakdown keep their working views.

## Files and purpose

| Files | Purpose |
| --- | --- |
| `backend/app/weather.py` | New Open-Meteo client, coordinate configuration, strict hourly parsing, 10-second timeout and one-hour cache/fallback. |
| `backend/app/forecast.py` | Weather-driven outdoor/solar inputs, named 0.8 performance ratio, pinned snapshots, source metadata and display-ready values; original synthetic fallback and risk bands retained. |
| `backend/app/guidance.py` | New transparent scenario suggestions, optional work-window/reserve patches and goal descriptions. |
| `backend/app/main.py` | Weather/demand-context endpoints, stored snapshot reuse, calculation/reset result details and independent rehearsal metadata. |
| `backend/app/models.py` | Optional stored-plan IDs for forecast verification and outage rehearsal; existing safety fields/validators preserved. |
| `backend/app/storage.py` | History before a selected date and reset counts; database schema and carry/approval rules retained. |
| `backend/app/assistant.py` | Distinguishes real weather forecasts from simulated hospital results and projects only relevant numeric weather/guidance data. Key handling, retries and fallback remain. |
| `requirements.txt`, `requirements-dev.txt` | Move the unchanged `httpx==0.28.1` pin into runtime dependencies. |
| `frontend/src/App.jsx` | Hydrate saved plans without fetching new weather; observable reset/recalculation, explicit scenario settings and resource-preserving goal actions. |
| `frontend/src/components.jsx` | Accessible modal and optional action on statistic cards. |
| `frontend/src/PlanningHelp.jsx`, `ResourceControls.jsx` | New weather strip, scenario/goal choices and grouped resource controls; display backend values only. |
| `frontend/src/pages/Overview.jsx`, `Outage.jsx`, `Presets.jsx` | New readable page modules with the revised interactions. |
| `frontend/src/pages/DayPlan.jsx`, `Insights.jsx`, `Tools.jsx` | Guided day planning, simplified comparison and wiring to revised pages/AI explanations. |
| `frontend/src/styles.css` | Responsive planning cards, weather strip, clearer controls, modals and result notices. |
| `backend/tests/test_weather.py`, `test_workspace.py`, `conftest.py` | Offline weather, snapshot, action-reporting and safety regression tests; block weather network in all tests. |
| `backend/tests/export_ui_fixtures.py`, `frontend/tests/*` | FastAPI-derived fixtures and actual React click/input checks in jsdom. |
| `frontend/package.json`, `package-lock.json`, `.gitignore` | Reproducible UI test tools, test command and ignored temporary test output. `.env` remains ignored. |
| `PROJECT.md`, `README.md`, `api-contract.md`, `docs/planner.md`, `docs/verification.md` | Weather provenance, rules, API shape, beginner update steps and verification limits. |

`backend/app/planner.py` is unchanged. No commit, push or deployment was made.
Use the README's update procedure to preserve `.env` and `data/` while rebuilding
the frontend. Do not reset copied history unless you intend to clear it.
