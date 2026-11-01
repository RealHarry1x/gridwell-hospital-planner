# Gridwell · Hospital energy planner

A complete **browser web app** with a React frontend, a FastAPI Python backend,
and SQLite storage. It prepares a 24-hour energy plan for **Cedar General
Hospital**, a fictional Indian hospital. Hospital demand, operations, tariffs
and energy results are simulated. Optional hourly **Open-Meteo weather
forecasts** supply outdoor temperature, cloud cover and the solar estimate;
unavailable weather automatically falls back to synthetic data. The app works
offline. No real equipment, patient data or utility feed is used. The AI Guide
can optionally use Gemini for friendly general chat and to explain simulated
energy data. Greetings work locally, and sample replies remain available
without a key or when Gemini is unavailable.

The supplied files contained the requirements and a Verdant design reference,
but **no GridMind or existing hackathonv1 source**. This is a new standalone
project, not a claimed merge with GridMind. Its cream/burgundy cards, sidebar and
theme were inspired by the reference; hospital data and behavior were built for
this brief.

## The easiest way to run it

You need these installed once:

1. **Python 3.12 or newer**. On Windows, enable **Add Python to PATH** during installation.
2. **Node.js 22.12 or newer**. A current LTS version is fine. This also installs `npm`.
3. An internet connection **for the first setup** to download code dependencies.

Download and extract the project ZIP. Open the extracted `hackathonv1` folder in
VS Code. Choose **Terminal → New Terminal**. Make sure the terminal is inside
the folder containing `run.py` and this README.

On **Windows**, run:

```powershell
py -3.12 run.py --setup
```

If you installed a newer Python and the `-3.12` selector is unavailable, use:

```powershell
py run.py --setup
```

On **macOS / Linux**, run:

```bash
python3 run.py --setup
```

The launcher creates `.venv`, installs Python dependencies, installs React/Vite,
builds the frontend, starts the Python server, and opens your browser at:

**http://127.0.0.1:8000**

Keep the terminal open while using the app. **Ctrl+C** stops it. The database is
stored in `data/demo.sqlite3`, so saved presets, plans and approved days survive
a restart. After initial setup, planning and Sample mode work without internet.
Internet is used for optional live weather and Gemini explanations. Only Gemini
needs an API key; all planning remains available offline with synthetic weather.

### The next time you run it

Windows:

```powershell
py run.py
```

macOS / Linux:

```bash
python3 run.py
```

Add `--no-browser` if you want to open the URL yourself. If port 8000 is busy:

```bash
python3 run.py --port 8001
```

Use the equivalent `py run.py --port 8001` on Windows.

### Common first-time problems

| Message / symptom | What to do |
| --- | --- |
| `python` / `py` is not recognized | Install Python 3.12+ with PATH enabled, then reopen VS Code. |
| Node/npm missing or too old | Install Node.js 22.12+ and reopen the terminal. |
| `npm.ps1` cannot run in PowerShell | Use the one-command Python launcher, which invokes `npm.cmd`, or type `npm.cmd` in place of `npm`. You do not need to change PowerShell policy. |
| Package download fails | Check internet/proxy access and rerun `--setup`. It is safe to rerun. |
| Port already in use | Close an older terminal running the app or use `--port 8001`. |
| Browser says “Cannot reach Python backend” | Keep the server terminal open, read its error, and rerun the launcher. |
| You see old frontend changes | Rebuild with `npm run build` inside `frontend`, restart Python, and refresh the browser. |
| You moved/copied `.venv` to another computer | Delete the copied `.venv` folder and rerun `--setup`; environments are machine-specific. |

## Weather: live when available, offline when needed

Weather needs **no API key**. Python calls Open-Meteo for three local forecast
days using Pune by default (latitude 18.52, longitude 73.86, Asia/Kolkata).
The Overview weather strip shows hourly temperature, cloud cover, radiation and
estimated solar energy. Its source badge always distinguishes **Open-Meteo live
forecast** from **Synthetic fallback (live weather unavailable)**. A weather
forecast is not an observation or a hospital meter reading.

To use another location, optionally add these **non-secret** settings to your
existing root `.env`, beside `run.py`, then restart Python:

```dotenv
WEATHER_LAT=18.52
WEATHER_LON=73.86
```

Keep any existing Gemini key/model lines. Server environment values override
`.env`. Weather requests have a 10-second timeout, and three-day results
(including unavailable results) are cached for one hour. No internet, invalid
responses, invalid coordinates or dates outside the provider horizon trigger
the repeatable synthetic fallback. Restarting Python clears the in-memory
cache; existing plans keep their stored weather regardless.

With live weather, Python estimates hourly solar potential as **array kWp ×
shortwave radiation / 1000 × 0.8**, then applies the selected scenario modifier.
The 0.8 performance ratio is an illustrative constant. This estimates energy
that could be generated, not measured production, and does not model detailed
panel tilt/shading. Open-Meteo supplies preceding-hour mean radiation in W/m².
Weather attribution: [Open-Meteo](https://open-meteo.com/) and its
[forecast API documentation](https://open-meteo.com/en/docs).

Saved plans store raw weather and its source. Reloading, verifying or
recalculating a saved plan reuses those values, including a saved synthetic
fallback. In Day Plan, choose **New draft with current weather** to create a
new plan using the current weather cache (one hour). The old record and history
are kept. Seeded history always uses synthetic weather. Demand still follows the
date-seeded model; Overview's seven-day popup shows simulated history for
context and explicitly explains that the current model is not trained on it.

## Optional Gemini setup for the AI Guide

The backend uses the official **Google GenAI Python SDK** (`google-genai`), not
the legacy `google-generativeai` library. The default is **`gemini-3.8-flash`**,
verified as stable in Google's official model list on 31 October 2026. Your
key's model access, quota and billing are checked by the actual API request;
public listing alone does not guarantee access for your account.

1. Stop the running app with **Ctrl+C**. Open the **`hackathonv1` folder** that
   contains `run.py`, `requirements.txt` and `.env.example`.
2. Create **`hackathonv1/.env`**, **beside `run.py`**. It does not belong in
   `backend/`, `frontend/`, or `frontend/src/`. If you do not already have an
   `.env`, copy the supplied `.env.example`:

   Windows PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

   macOS / Linux:

   ```bash
   cp .env.example .env
   ```

   Keep an existing `.env` when upgrading; do not overwrite your local settings.
   The filename must be `.env`, not `.env.txt`.
3. Edit that file **on your own computer**. Put your actual key after
   `GEMINI_API_KEY=` and keep or change the fixed model ID:

   ```dotenv
   GEMINI_API_KEY=
   GEMINI_MODEL=gemini-3.8-flash
   ```

   The blank key above is intentional: enter it locally, never in Codex/ChatGPT.
   If this model is unavailable to your key, set `GEMINI_MODEL` to another
   **stable text model** your account supports. Preview, experimental, rolling
   `latest`, image, speech, embedding and live-model IDs are not used here.
4. From the same `hackathonv1` folder, install the updated dependencies, rebuild
   the frontend and restart:

   | Computer | Command |
   | --- | --- |
   | Windows | `py run.py --setup` |
   | macOS / Linux | `python3 run.py --setup` |

   On subsequent restarts, use `py run.py` or `python3 run.py`. If only `.env`
   changed, Ctrl+C and the normal restart are enough; no rebuild is needed.
   For two-terminal development, restart the **Python/uvicorn terminal** after
   changing `.env`; rebuild/restart Vite only for frontend code changes.
5. Open **http://127.0.0.1:8000**, generate a plan, visit **AI Guide**, and ask
   **“Explain my plan”**. Before the first reply, **Gemini configured · awaiting
   reply** means setup was detected, not that a paid/API request succeeded.
   A successful reply is labeled **Gemini mode · simulated data** and shows the
   model name. A fallback is labeled **Sample mode**, with a friendly reason.

**Never commit `.env`, put the key in frontend code or a `VITE_*` variable,
paste it into this chat, or share it with the team in a ZIP.** `.gitignore`
continues to ignore `.env` and `.env.*`, while allowing the empty-key
`.env.example`. The local file is read explicitly from the project root with
`python-dotenv`; exported server environment values take precedence, and no
variable interpolation is performed. An explicitly empty exported key disables
Gemini even if `.env` has a value. Configuration is loaded on Python startup.

The browser calls only **`POST /api/assistant`** on Python. The key stays on the
server. General questions are sent to Gemini as a single message after local
sensitive-content checks, **without hospital data**. Energy-plan questions use
a normalized energy interpretation plus relevant hours and allowlisted current
simulated values. Full records, database history and previous chat messages
are not forwarded. Recognized patient identifiers, emails, phone-like
identifiers and secrets receive a local privacy reply; hospital action requests
receive a read-only refusal. Do not enter personal or patient information.

Gemini is an **explainer only**. It has no tools, database/write access, plan
approval function or equipment connection. Its instructions require using only
the supplied numbers, acknowledging missing data, reporting failed checks and
never overriding hard rules. General knowledge may use ordinary facts and
reasoning; those replies are labeled **General chat**, not simulated readings.
Review the recorded plan if an explanation seems
wrong. The optimizer and hard constraints are unchanged.

Each Gemini call has a **45-second SDK HTTP timeout**. If the first call
returns HTTP **503 or 504**, the backend waits **2 seconds** and makes **one
retry** with the same model and minimized context. There are at most two
calls; SDK-internal retries and automatic continuation remain disabled.
A **100-second overall deadline** covers both calls, the pause and cleanup.
Other errors (including quota/billing, authentication, local transport errors
and unusable/blocked replies) go straight to Sample mode without a retry.
The guide is asked for **2–5 concise sentences, at most about 120 words**.
The 1,500-token cap includes internal thinking, so it is retained to leave room
for a complete short answer. Low thinking remains configured for Gemini 3.x.
Missing
keys, rejected/invalid keys, inaccessible models, quota errors, timeouts,
provider failures and empty/blocked/incomplete responses use local Sample mode.
The app never silently claims Gemini succeeded or switches to a different model.
Privacy/read-only replies may intentionally use Sample mode even when Gemini
is configured. Ordinary general questions are no longer rejected as outside
the energy domain.

### Friendly chat and energy context

- **“hi” / “hello”** → “Hi! What can I help you with?” This is a **Local reply**
  and does not call Gemini or verify your key. Thanks and goodbyes also get
  natural local replies.
- **“What is Python?”** → general knowledge in **Gemini mode · general chat**
  when available. No hospital forecast or plan is sent for this question.
- **“Explain my plan” / “How much does this cost?”** → the selected backend
  plan and forecast, labeled **Simulated Gridwell data**. Missing/live hospital
  readings and uncomputed savings are never invented.
- With no key/provider access, **Sample mode** retains the energy explanation
  and a few offline answers (Python, recursion, photosynthesis, simple
  arithmetic, etc.). It admits when a general question needs broader Gemini
  support; it is not a complete offline language model.

The chat answers one message at a time; earlier messages stay in the browser
and are not forwarded as model history. General answers are informational and
cannot browse live sources or perform actions. Plan approval, settings,
equipment controls and all optimizer rules remain outside the chatbot.
To check Gemini connectivity, ask a general or energy question, rather than
using a local greeting as the connection test.

**Gemini usage follows your Google API project's quota, model access and
account billing. It is separate from any ChatGPT subscription.** A token cap
does not make calls free; timed-out requests may still be billed by Google.
Check usage and limits in your own Google AI Studio account.

Official references:

- [Stable Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
- [Official Google GenAI libraries](https://ai.google.dev/gemini-api/docs/libraries)
- [Model availability/listing API](https://ai.google.dev/api/models)
- [Gemini quota and rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing)
- [Official SDK error handling](https://googleapis.github.io/python-genai/#error-handling)
- [Gemini API troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting)
- [GenerateContent thinking / output token limits](https://ai.google.dev/gemini-api/docs/generate-content/thinking)

### Diagnose a Sample-mode fallback in the server Terminal

Earlier versions deliberately hid SDK exception details. That made an invalid
key, inaccessible model, quota error, proxy failure and a response without
complete text all look like the same fallback. The backend now prints safe
`[Gridwell AI]` diagnostic lines in the **Terminal running Python**, without
turning on SDK/HTTP debug logging. The browser still gets only a friendly
Sample-mode notice.

At startup, `event="configuration"` reports:

- `env_file`: the exact project-root `.env` path being read.
- `env_file_status`: `present`, `missing` or `unreadable`.
- `key_present`: a boolean only, never the key, its prefix, length or fingerprint.
- `key_source`: `.env`, `environment` or `missing` (`provided` in injected tests).
- `model` and `model_source`: the actual model selection; invalid IDs are hidden.

For a normal local `.env`, expect `key_source=".env"`, `key_present=true` and
your chosen `model`. If `key_source="environment"` and `key_present=false`, an
empty exported variable is overriding the file. To use `.env` instead, remove
that override in the terminal you will use to restart Python:

macOS / Linux:

```bash
unset GEMINI_API_KEY
```

Windows PowerShell:

```powershell
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
```

Likewise remove an unintended `GEMINI_MODEL` environment override if it selects
a different model from your file. Do not print either variable's value.
`key_present` and `model_valid` check local configuration, not credential
validity, model access or quota; only a usable `gemini_success` reply confirms
generation succeeded.

Ask **“Explain my plan”** or **“How much does this cost?”** in AI Guide and look
for one of these events:

| Terminal event / field | What it establishes |
| --- | --- |
| `gemini_request` | The backend is attempting generation with the displayed model; SDK initialization can still fail before any HTTP request. |
| `gemini_error`, `http_status` | The actual SDK/HTTP error status, when supplied. |
| `api_status` and `message` | The provider's symbolic status and sanitized message, not a generic guessed cause. |
| `generation_unusable`, `finish_reason`, `block_reason` | Google completed a request but no complete usable text was available; this is different from an API authentication/quota error. |
| `gemini_success` | A usable Gemini explanation was accepted. |
| `sample_fallback`, `api_called=false` | A missing/invalid local configuration or privacy/read-only gate prevented a Gemini call. |

Illustrative error-line excerpt, **not a diagnosis of your account**:

```text
[Gridwell AI] {"event":"gemini_error","model":"gemini-3.8-flash","http_status":429,"api_status":"RESOURCE_EXHAUSTED","message":"Quota exceeded for the selected model.","fallback":"quota"}
```

Use the **actual message** rather than assuming every fallback is quota-related:

| Status / outcome | What to inspect before retrying |
| --- | --- |
| 400 / `INVALID_ARGUMENT` | Whether the message names an invalid key, unsupported parameter or another malformed request. |
| 401 / 403 | Local key validity and the Google project's model/inference permissions or restrictions, as stated in the message. |
| 404 | Exact `GEMINI_MODEL` ID and that model's availability to your key/API method. |
| 402 / 429 | The account's API quota/billing status and any rate-limit wait; the app makes no billing changes. |
| 503 / `UNAVAILABLE` | The backend waits 2 seconds and retries once, then uses Sample mode if the retry fails. |
| 504 / `DEADLINE_EXCEEDED` | Google's request deadline was exceeded. The app retries once after 2 seconds; another 504 uses the friendly timeout Sample reply. This status alone does not mean the key is invalid. |
| `MAX_TOKENS` | Thinking also uses the 1,500-token output cap. A request may have succeeded but stopped before a complete answer. Try a focused question; truncated content is not presented as a complete explanation. |
| `SAFETY` / another block reason | The provider blocked or stopped the response. Safety filters are not disabled to force an answer. |
| `http_status="not_reported"`, `ImportError` or a network error | No HTTP status was supplied. Read the safe SDK/proxy/timeout message; do not mistake it for a made-up Google 4xx error. |

For example, if the message specifically says `socksio` is missing and you
intentionally use a SOCKS proxy, that is a local HTTPX dependency issue. Install
`httpx[socks]` in the project's `.venv`, then restart. Do not disable a required
network proxy just to make a request succeed.

The normal `POST /api/assistant` access log can still say **200** because a
Sample reply is a successful app response. That is not Google's status; use
the separate `[Gridwell AI]` event line. The SDK does not expose an HTTP status
on every successful/empty response, so those diagnostics say `not_reported`
and show the actual generation outcome instead of inventing a status.

Logs select only scalar error/configuration fields and redact the known key,
other credential-like environment values, common authorization/token/password
forms, URLs, email addresses and long identifiers **before** logging. Full
exceptions, headers, response bodies, prompts, replies and thought text are
not dumped. Do not turn on SDK/HTTP debug logs or share `.env`. If requesting
further help, share only the sanitized `[Gridwell AI]` error line.

The Terminal now shows a safe `request_policy` startup event containing the
45-second HTTP timeout, 100-second overall deadline and single 2-second retry
policy. A `gemini_retry` event reports the first failure's actual HTTP/API
status and sanitized message, plus `next_attempt="2 of 2"`. The next result is
`gemini_success`, or `gemini_error` followed by `sample_fallback`. The overall
deadline includes the retry delay; it never starts a background retry after a
Sample reply has been returned. Temporary errors can still persist at Google;
the retry improves resilience without guaranteeing an answer. Each attempt
uses your account's API quota/billing.

### Update your existing `hackathonv1 4` folder

This update changes both Python and React source, so replace the source and
rebuild. The easiest safe route is to keep the old folder as a backup:

1. Stop the running app with **Ctrl+C**. Rename your current folder to
   **`hackathonv1 4 backup`**; keep it until the updated app works.
2. Download and unzip the updated `gridwell-hospital-planner.zip`. Rename the
   extracted `hackathonv1` folder to **`hackathonv1 4`** if you want the same name.
3. Copy **`.env`** and the **`data` folder** from your backup into the new folder.
   `.env` belongs beside `run.py`. On macOS, **Command+Shift+.** in Finder shows
   hidden files. Keep your existing Gemini key/model; do not copy `.venv`,
   `node_modules`, old frontend source or build files over the update.
4. Open Terminal in the new **`hackathonv1 4`** folder. On macOS, type `cd `
   (with a space), drag the folder into Terminal, then press Enter. Run:
   **`python3 run.py --setup`**. Windows: **`py -3.12 run.py --setup`**.
   This installs the pinned runtime HTTPX dependency, installs frontend packages,
   rebuilds React and starts the app. This rebuild is required for the new UI.
5. Refresh **http://127.0.0.1:8000**. Saved old plans keep their original synthetic
   forecast; use **New draft with current weather** in Day Plan to use the weather integration. Existing
   presets and history remain in the copied SQLite database. Reset only when
   you explicitly want to clear those saved plans/approvals and reseed history.

After setup, normal restarts use `python3 run.py` (Windows: `py run.py`). Never
commit `.env` or include it in a ZIP for your team. No changes are pushed or
published by this update.

## A five-minute hackathon demo

1. **Overview**: read expected hospital demand and click **Last 7 days &
   estimate basis**. The popup shows simulated recorded energy, its average and
   the true seeded-model explanation. Check **Solar potential for this day**
   and the weather strip's provider/fallback label. The graph shows expected
   demand and solar without the distracting low/high range decoration.
2. **Day Plan → Choose the conditions**: review the weather-based suggestion,
   then explicitly select Normal, Heatwave, Low solar or Grid outage. Suggestions
   use disclosed demo thresholds, not an AI weather prediction. Outdoor
   temperature, cooling demand and solar change with the selected case. Indoor
   comfort bounds remain your chosen limits. Grid outages are selected by you,
   never inferred from weather.
3. Optionally choose **Apply suggested working settings** to set the displayed
   reserve/work windows; it keeps equipment and comfort limits and clears
   manual hourly overrides. Then choose Balanced, Lowest cost, Lowest emissions
   or custom weights. Read the visible trade-off under each goal.
4. Review the resource controls, then **Generate recommendation**. Change a
   setting and choose **Recalculate with these settings**. The revision,
   timestamp, result notice and changes show that the action completed. With
   identical inputs and saved weather, matching figures are expected and
   explicitly explained. Optional hourly edits and original forecast bands
   remain available below the basic workflow.
5. **Comparison** retains the calculated cost/emissions/peak differences and
   detailed same-input table; duplicate safety summary cards are removed.
   **Energy Breakdown** and **Suggestions** explain flows and evaluate changes.
6. **Outage Readiness**: choose the cut window, available generator/fuel and
   optional beginning-of-day battery. Toggle a failure/refill event, then run.
   The timeline shows supply, fuel, paused energy, critical shortfalls and
   temperature. Changes affect only this rehearsal; results are marked pending
   if you edit controls after a run. Expected and adverse checks are separate.
7. **Presets**: goals change priorities without replacing equipment. Save a
   named full resource setup in the separate editor, explicitly load it when
   needed and return to Day Plan to calculate. Editing a saved setup leaves
   the current plan alone. Trends and Energy Breakdown retain their existing
   data views.
8. **AI Guide**: ask about the current plan, or use the day-type explanation
   link. Gemini can explain labeled weather and simulated energy estimates; it
   cannot apply settings, approve or operate equipment. Sample mode still works
   without a key. A local “hi” reply does not test Gemini connectivity.
9. **Overview → Data sources, assumptions & resetting the demo**: choose the
   earliest history day's opening battery, press Reset demo and confirm. The
   completion panel reports removed plans, replaced history and kept presets.
   Controls and drafts reset immediately. Same dates still have repeatable
   forecasts; resetting is not a random-data generator.

To intentionally show blocked approval, request **999 kWh** grid charging in
an hourly edit and recalculate. The requested action is reported as invalid,
the executed flow stays bounded, and approval is blocked. Clear hourly edits
and recalculate to recover.

## What is included

- Nine working views: Overview, Day Plan, Comparison, Trends, Outage Readiness,
  Energy Breakdown, Suggestions, AI Guide and Presets.
- Responsive desktop/mobile browser layout, keyboard controls, visible units,
  light/dark appearance and lightweight CSS transitions.
- Stable date-seeded hospital demand with optional Open-Meteo weather, pinned
  weather snapshots, explicit source labels and editable original ranges.
- Transparent 24-hour **look-ahead heuristic** in Python, with reserve,
  efficiency, flexible windows, capacities and comfort settings.
- Explicit source flows, storage losses, cost/emissions accounting, curtailment,
  critical shortfalls and simplified thermal checks for every hour.
- Generator threshold/failure/fuel/refill simulation, risk replay and
  server-enforced approval blocking.
- Same-input baseline comparison and backend-calculated alternatives.
- SQLite persistence for drafts, approval history, battery carry and presets.
- Optional backend-only Gemini explainer with local sample fallback, per-reply
  mode labels, privacy filtering and bounded requests; CSV schedule export.
- Tests for the planner invariants and complete API workflow.
- No commits, pushes, publishing or deployment have been performed.

## Initial assumptions

| Setting | Illustrative starting value |
| --- | --- |
| Daily energy reference | About 5,200 kWh/day; brief-supplied national-survey proxy, not a measured/Pune average |
| Solar | 100 kWp |
| Battery | 1,000 kWh; 250 kW max charge/discharge |
| Occupancy | About 75%, with synthetic hourly ranges |
| Very first simulated day | 70% initial battery; adjustable through **Overview → assumptions → Reset demo** |
| Subsequent days | Last recorded ending battery energy; changing dates does not reset it |
| Normal reserve | Editable, starts at 20%; minimum 10% |
| Charge/discharge efficiency | 95% each; 90.25% round trip |
| Comfort | Editable 22–26°C placeholder; not a medical standard |
| Outage | 18:00–23:00 initially; editable same-day interval |
| Generator | 220 kW, 400 L tank, 55% initial fuel |
| Diesel assumptions | 0.27 L/kWh, ₹95/L, 2.68 kg CO2e/L; illustrative, not verified local values |
| Generator start | Fixed at 10% battery during outage; emergency reserve released on failure/unavailability/fuel exhaustion |
| Fuel warnings | At/below 40%; urgent below 30% |

Eight recent synthetic days are seeded on first launch, including an outage to
demonstrate carry. Therefore tomorrow's opening battery can differ from the
first day's 70%. The earliest day's assumption is visible in Trends. Reset
rebuilds history; it does not force every day back to 70%.

## If you want to edit the code

The launcher serves the **built React app and API together from Python**. For
development, use two terminals after initial setup.

Terminal 1, from the project root:

Windows:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

macOS / Linux:

```bash
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Terminal 2:

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to Python on port 8000. The
frontend only displays API data and sends edits; dispatch, cost, carbon and
safety logic stay in the backend. Stop both terminals with Ctrl+C.

After frontend edits, run `npm run build` inside `frontend` to refresh the
single-server version used by `run.py`.

### Run the checks

Windows, from the project root:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
cd frontend
npm test
npm run build
```

macOS / Linux:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
cd frontend
npm test
npm run build
```

Interactive API documentation is at **http://127.0.0.1:8000/docs** while Python
is running. See [api-contract.md](api-contract.md), [PROJECT.md](PROJECT.md) and
[docs/planner.md](docs/planner.md) for the shared data contract and assumptions.

```text
hackathonv1/
  run.py                    # one-command setup / run
  requirements*.txt         # Python runtime and optional tests
  backend/
    app/
      main.py               # API routes and demo initialization
      models.py             # validated API request models
      forecast.py           # simulated demand + optional weather-based solar
      weather.py            # Open-Meteo fetch, validation and 1-hour cache
      guidance.py           # explained day types and goal trade-offs
      planner.py            # dispatch, constraints and comparisons
      storage.py            # SQLite persistence / battery carry
      assistant.py          # read-only Gemini + sample adapters / safe projection
      ai_config.py          # private root .env / server environment loading
    tests/                  # planner and API checks
  frontend/
    src/
      App.jsx               # shared state and API orchestration
      api.js                # common JSON API helper
      components.jsx        # reusable UI and SVG charts
      pages/                # the nine browser views
      PlanningHelp.jsx      # weather strip, scenario and goal choices
      ResourceControls.jsx  # grouped equipment and work-limit inputs
      styles.css            # responsive cream/burgundy themes
    tests/                  # React DOM interaction checks with mock API data
    package-lock.json       # reproducible npm dependency versions
  docs/planner.md
  api-contract.md
  PROJECT.md
```

## Known limits and future integration

The planner is a deterministic heuristic, **not a certified optimizer** or trained
hospital-demand forecasting model or reinforcement-learning controller. Forecast bands are
illustrative, not calibrated confidence intervals. Comfort uses a deliberately
simple one-zone thermal replay; it is not a clinical standard or building
simulation. Intervals are one hour, so generator switching is only approximated
within an interval. No battery aging model, demand-charge tariff, grid
interconnection model or multi-day optimal control is implemented.

During outages, noncritical lab/lighting/other demand is explicitly paused.
Critical medical equipment includes essential labs, life-safety lighting and
other critical circuits. Laundry and water heating move within their allowed
windows or the draft becomes infeasible. No safety rule is silently relaxed.

Day comparisons use the same forecast and activity energy budgets. Cost/carbon
improvements can raise peak grid demand. Ordinary grid-charge-enabled plans
restore opening battery stock by midnight; outage/grid-charge-off plans may
finish with a different stock, and the comparison displays that boundary.
There is no invented savings percentage.

The brief's national-survey reference was not accompanied by a source. Its
5,200 kWh/day value is used only as a labeled assumption, not a verified claim.

The app has no real login and is intended for a local, single-operator demo.
Real use would need authenticated roles, validated forecasts and equipment
adapters, clinical/engineering review, stronger concurrency/version handling
for simultaneous editors, and a tested operational safety system.

Optional Gemini explanations are implemented in `backend/app/assistant.py`.
An accessible Gemini model, a locally configured server-side key and account
quota/billing are needed to verify live Gemini replies. No key is needed for
the planner or Sample mode. Automated tests use intercepted SDK requests and
dummy credentials, never your `.env` or billable API calls. The original
GridMind interface still depends on obtaining its actual source files.

## Sharing on GitHub later

Source files, a dependency lockfile, documentation and `.gitignore` are ready.
Do not upload `.venv`, `node_modules`, `data`, `.env`, database files or generated
logs. The downloadable ZIP intentionally excludes those local dependencies and
runtime records. Anyone can rebuild them with `--setup`.

No Git repository was initialized or committed for you, and nothing has been
pushed, published or deployed. Add your preferred license and create a GitHub
repository only when your team is ready.
