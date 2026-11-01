"""FastAPI entry point. Run from backend: python -m uvicorn app.main:app."""

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.concurrency import run_in_threadpool

from .assistant import AssistantService, conversation_scope
from .forecast import CATEGORIES, make_forecast, seeded_rng
from .models import (ApprovalRequest, AssistantRequest, DayType, OutageRequest,
                     PlanRequest, PresetRequest, ResetRequest, Settings, VerifyRequest)
from .planner import create_plan
from .storage import Store
from . import weather
from .guidance import GOALS, SCENARIOS, planning_guidance

INDIA = timezone(timedelta(hours=5, minutes=30))
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def local_today():
    return datetime.now(INDIA).date()


def envelope(data):
    return {"data": data, "meta": {"simulated": True, "mode": "local-demo", "api_version": "1.0"}}


def history_entry(day, plan, forecast, source):
    entry = dict(plan["summary"])
    rng = seeded_rng(day, forecast["day_type"], "actual")
    expected = forecast["daily"]["demand_kwh"]["expected"]
    actual = expected * rng.uniform(0.95, 1.05)
    entry.update(date=day.isoformat(), source=source, day_type=forecast["day_type"],
                 forecast_demand_kwh=expected, actual_demand_kwh=actual,
                 occupancy_pct=forecast["daily"]["occupancy_pct"]["expected"],
                 forecast_error_pct=abs(actual - expected) / actual * 100,
                 actual_source="Seeded synthetic actuals; not meter readings")
    return entry


def seed_history(store):
    if store.meta("seeded", False):
        return
    store.set_meta("initial_soc_pct", store.meta("initial_soc_pct", 70))
    start = 1000 * store.meta("initial_soc_pct", 70) / 100
    today = local_today()
    for offset in range(7, -1, -1):
        day = today - timedelta(days=offset)
        scenario = "grid_outage" if offset == 2 else "normal"
        settings = Settings()
        forecast = make_forecast(day, scenario, settings, weather_snapshot=None)
        plan = create_plan(forecast, settings, start, include_suggestions=False)
        store.save_history(history_entry(day, plan, forecast, "seeded simulated history"))
        start = plan["summary"]["battery_soc_end_kwh"]
    store.set_meta("seeded", True)


def builtin_presets():
    return [{"id": f"builtin-{goal['id']}", "name": goal["name"], "description": goal["description"],
             "built_in": True, "scope": "goal_only", "goal": goal,
             "settings": Settings(objective=goal["id"]).model_dump(),
             "settings_patch": {"objective": goal["id"]}}
            for goal in GOALS if goal["id"] != "custom"]


def display_values(result, settings):
    """Presentation values are calculated here, never in browser arithmetic."""
    result["display"] = {
        "normal_reserve_kwh": settings.battery_capacity_kwh * settings.reserve_pct / 100,
        "generator_threshold_kwh": settings.battery_capacity_kwh * .1,
        "generator_total_kwh": result["summary"]["generator_to_critical_kwh"] + result["summary"]["generator_to_hvac_kwh"],
        "goal": next(goal for goal in GOALS if goal["id"] == settings.objective),
    }
    for row in result["hours"]:
        row["grid_draw_kwh"] = row["grid_to_load_kwh"] + row["grid_to_battery_kwh"]
        row["generator_total_kwh"] = row["generator_to_critical_kwh"] + row["generator_to_hvac_kwh"]
    return result


def create_app(db_path=None, *, assistant_service=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(db_path)
        seed_history(app.state.store)
        app.state.assistant = assistant_service or AssistantService()
        app.state.assistant.log_configuration()
        yield

    app = FastAPI(title="Gridwell hospital energy planner", version="1.0.0", lifespan=lifespan,
                  description="Simulated hospital energy planning with optional Open-Meteo forecasts and read-only Gemini explanations. No equipment control.")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def local_demo_headers(request, call_next):
        # Browser requests stay on this backend. Optional AI credentials remain server-side.
        if request.url.path.startswith("/api"):
            origin = request.headers.get("origin")
            if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
                allowed = {f"{request.url.scheme}://{request.url.netloc}", "http://localhost:5173", "http://127.0.0.1:5173"}
                same_host = urlsplit(origin).netloc == request.url.netloc and urlsplit(origin).scheme in ("http", "https")
                if origin not in allowed and not same_host:
                    return JSONResponse(status_code=403, content={"error": {"message": "Cross-origin writes are disabled in this local demo."}})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"error": {"message": str(exc.detail)}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        details = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"error": {"message": "Check the highlighted request values.", "details": details}})

    def load_plan(plan_id):
        plan = app.state.store.get_plan(plan_id)
        if not plan:
            raise HTTPException(404, "Plan not found. Generate a new plan.")
        return saved_display(plan)

    def saved_display(plan):
        if plan is None:
            return None
        settings = Settings(**plan["settings"])
        fc = plan["forecast"]
        # Older databases remain usable. Derive display-only metadata from
        # their saved values without fetching weather or changing the ledger.
        fc.setdefault("planning_guidance", planning_guidance(fc, settings))
        fc["daily"].setdefault("outdoor_min_c", min(row["outdoor_temperature_c"] for row in fc["hours"]))
        fc["daily"].setdefault("outdoor_max_c", max(row["outdoor_temperature_c"] for row in fc["hours"]))
        fc["daily"].setdefault("hvac_kwh", round(sum(row["components_kwh"]["hvac"] for row in fc["hours"]), 2))
        fc["daily"].setdefault("solar_capacity_kwp", settings.solar_capacity_kwp)
        return display_values(plan, settings)

    def snapshot_for(plan_id, day):
        if not plan_id:
            return None
        previous = load_plan(plan_id)
        if previous["date"] != str(day):
            raise HTTPException(422, "Selected plan and forecast date do not match.")
        return previous["forecast"]

    def assemble(request, plan_id=None, revision=1, previous=None):
        carry = app.state.store.carry(request.date, request.settings.battery_capacity_kwh)
        if carry["energy_kwh"] > request.settings.battery_capacity_kwh:
            raise HTTPException(422, "The carried battery energy is larger than this capacity. Restore the capacity or explicitly reset the demo.")
        options = {"weather_snapshot": previous["forecast"]} if previous else {}
        forecast = make_forecast(request.date, request.day_type, request.settings, request.forecast_overrides, **options)
        plan = create_plan(forecast, request.settings, carry["energy_kwh"], request.hourly_edits)
        plan.update(id=plan_id or str(uuid4()), date=str(request.date), day_type=request.day_type,
                    revision=revision, status="draft", settings=request.settings.model_dump(),
                    input=request.model_dump(mode="json"), forecast=forecast, battery_carry=carry,
                    approved_at=None)
        same_inputs = previous is not None and previous["input"] == plan["input"]
        plan["calculation"] = {"calculated_at": datetime.now(INDIA).isoformat(), "same_inputs": same_inputs,
                               "message": "Recalculated with the same inputs and saved weather. Matching figures are expected. Change a setting or an hourly value to compare a new result."
                               if same_inputs else "Calculated from your selected scenario, settings and hourly edits. Review the updated figures and checks."}
        display_values(plan, request.settings)
        return plan

    @app.get("/api/health")
    def health():
        configured = app.state.assistant.public_status()["configured"]
        return envelope({"status": "ok", "database": "SQLite", "assistant": "gemini-configured" if configured else "sample-responses"})

    @app.get("/api/config")
    def config(planning_date: date | None = Query(None, alias="date")):
        tomorrow = local_today() + timedelta(days=1)
        return envelope({
            "product": "Gridwell", "hospital": "Cedar General Hospital · fictional",
            "today": str(local_today()), "tomorrow": str(tomorrow), "timezone": "Asia/Kolkata",
            "defaults": Settings().model_dump(), "initial_soc_pct": app.state.store.meta("initial_soc_pct", 70),
            "assistant": app.state.assistant.public_status(),
            "battery_carry": app.state.store.carry(planning_date or tomorrow, 1000),
            "day_types": SCENARIOS, "goals": GOALS, "weather_location": weather.location(),
            "outage_event_hour": 19,
            "assumptions": [
                "Hospital demand, occupancy, prices, carbon intensities and actuals are synthetic and date-seeded. Open-Meteo weather is optional, with an automatic synthetic fallback.",
                "Approximately 5,200 kWh/day is a rounded national-survey proxy supplied in the brief, not a measured hospital or Pune average. The survey itself was not supplied or independently verified.",
                "100 kWp solar, 1,000 kWh storage, 250 kW battery power and 75% occupancy are illustrative demo settings.",
                "22–26°C comfort, 95% charge/discharge efficiency, and generator / fuel assumptions are illustrative, not clinical or engineering standards.",
                "The planner is a deterministic look-ahead heuristic, not a trained AI model or a certified optimizer.",
                "The initial battery assumption applies only to the earliest day. Later days carry the last recorded ending energy; approval writes simulation history only.",
            ],
            "hard_rules": ["Never reduce or move critical demand", "Check editable comfort bounds", "Respect battery capacity and power",
                           "Generator stays off with the grid available", "Start generator at 10% during outage; hold emergency battery for failure",
                           "No generator-to-battery charging", "Respect generator power and fuel", "Block approval when expected or risk checks fail"],
            "generator_start_pct": 10, "fuel_warning_pct": 40, "fuel_urgent_below_pct": 30,
        })

    @app.get("/api/forecast")
    def forecast(day: date = Query(alias="date"), day_type: DayType = "normal",
                 solar_capacity_kwp: float = Query(100, ge=0, le=2000),
                 outage_start: int = Query(18, ge=0, le=23), outage_end: int = Query(23, ge=1, le=24)):
        if outage_start >= outage_end:
            raise HTTPException(422, "Outage start must be before outage end.")
        return envelope(make_forecast(day, day_type, Settings(solar_capacity_kwp=solar_capacity_kwp, outage_start=outage_start, outage_end=outage_end)))

    @app.post("/api/forecast/verify")
    def verify(request: VerifyRequest):
        options = {"weather_snapshot": snapshot_for(request.plan_id, request.date)} if request.plan_id else {}
        return envelope(make_forecast(request.date, request.day_type, request.settings, request.forecast_overrides, **options))

    @app.get("/api/weather")
    def weather_forecast(day: date = Query(alias="date")):
        hours = weather.fetch_hourly_weather(day)
        result = envelope({"date": str(day), "hours": hours,
                           "source": weather.LIVE_SOURCE if hours else weather.FALLBACK_SOURCE,
                           "location": weather.location(), "fetched_at": weather.fetched_at(day),
                           "note": "Hourly weather forecast, not an observation or a hospital meter reading. Saved plans retain their own snapshot."})
        result["meta"]["simulated"] = hours is None
        return result

    @app.get("/api/demand-context")
    def demand_context(day: date = Query(alias="date"), day_type: DayType = "normal", plan_id: str | None = None):
        saved = snapshot_for(plan_id, day) if plan_id else None
        fc = saved or make_forecast(day, day_type, Settings())
        recent = app.state.store.history(7, before=day)
        values = [{"date": row["date"], "energy_kwh": row["actual_demand_kwh"], "source": row["actual_source"]} for row in recent]
        return envelope({"date": str(day), "days": values,
                         "average_kwh": round(sum(row["energy_kwh"] for row in values) / len(values), 2) if values else None,
                         "forecast_expected_kwh": fc["daily"]["demand_kwh"]["expected"],
                         "history_used_for_forecast": False,
                         "method": "The current demand model starts near 5,200 kWh/day, adds deterministic date variation and the chosen day-type modifier. The seven recorded days are shown for context; they are not training data or a measured basis for this estimate.",
                         "source": "Simulated recorded energy; no real hospital meters are connected."})

    @app.post("/api/plans/generate", status_code=201)
    def generate(request: PlanRequest):
        plan = assemble(request)
        app.state.store.save_plan(plan)
        return envelope(plan)

    @app.get("/api/plans")
    def find_plan(day: date = Query(alias="date")):
        return envelope(saved_display(app.state.store.latest_plan(day)))

    @app.get("/api/plans/{plan_id}")
    def get_plan(plan_id: str):
        return envelope(load_plan(plan_id))

    @app.post("/api/plans/{plan_id}/recalculate")
    def recalculate(plan_id: str, request: PlanRequest):
        existing = load_plan(plan_id)
        if str(request.date) != existing["date"]:
            raise HTTPException(422, "Recalculation must keep the plan's date. Generate a new plan for another date.")
        plan = assemble(request, plan_id, existing["revision"] + 1, previous=existing)
        plan["changes"] = {key: plan["summary"][key] - existing["summary"][key]
                           for key in ("cost_inr", "emissions_kg_co2e", "peak_grid_kw", "battery_soc_end_kwh")}
        # The old approval's carry remains until the replacement is approved.
        # Other drafts will be invalidated atomically by approval.
        app.state.store.save_plan(plan)
        return envelope(plan)

    @app.post("/api/plans/{plan_id}/approve")
    def approve(plan_id: str, request: ApprovalRequest):
        plan = load_plan(plan_id)
        if request.revision != plan["revision"]:
            raise HTTPException(409, "A newer revision exists. Review it before approval.")
        if plan["status"] == "stale":
            raise HTTPException(409, "An earlier day's approval changed the battery carry. Recalculate this plan.")
        if not plan["valid"]:
            raise HTTPException(409, "This plan fails a hard constraint in the expected or adverse case. Resolve warnings before approval.")
        carry = app.state.store.carry(plan["date"], plan["settings"]["battery_capacity_kwh"])
        if abs(carry["energy_kwh"] - plan["battery_carry"]["energy_kwh"]) > 1e-5:
            raise HTTPException(409, "The opening battery carry changed. Recalculate before approval.")
        plan["status"] = "approved"
        plan["approved_at"] = plan["approved_at"] or datetime.now(INDIA).isoformat()
        entry = history_entry(date.fromisoformat(plan["date"]), plan, plan["forecast"], "approved simulation")
        try:
            invalidated = app.state.store.approve(plan, entry)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        plan["invalidated_future_plan_ids"] = invalidated
        plan["approval_notice"] = "Approved for simulation only. No commands were sent to equipment. Later recorded days are invalidated when an earlier day is re-approved."
        return envelope(plan)

    @app.get("/api/plans/{day}/comparison")
    def get_comparison(day: date, plan_id: str | None = None):
        plan = load_plan(plan_id) if plan_id else app.state.store.latest_plan(day)
        if not plan:
            raise HTTPException(404, "Generate a plan for this date first.")
        if plan["date"] != str(day):
            raise HTTPException(422, "Plan and comparison date do not match.")
        return envelope(plan["comparison"])

    @app.get("/api/trends")
    def trends(days: int = Query(7, ge=1, le=60)):
        history = app.state.store.history(days)
        return envelope({"days": history, "source": "Seeded synthetic actuals and approved simulations, never live meters"})

    @app.get("/api/energy-breakdown")
    def breakdown(day: date = Query(alias="date"), plan_id: str | None = None):
        plan = load_plan(plan_id) if plan_id else app.state.store.latest_plan(day)
        if not plan:
            raise HTTPException(404, "Generate a plan for this date first.")
        if plan["date"] != str(day):
            raise HTTPException(422, "Plan and breakdown date do not match.")
        labels = {"critical": "Critical medical equipment", "hvac": "HVAC", "labs": "Noncritical labs", "lighting": "Noncritical lighting",
                  "laundry": "Laundry", "water_heating": "Water heating", "other": "Other"}
        values = [{"id": key, "label": labels[key], "energy_kwh": sum(h["components_kwh"][key] for h in plan["hours"])} for key in CATEGORIES]
        return envelope({"date": str(day), "consumption": values, "supply": plan["summary"],
                         "note": "Consumption is scheduled demand. Outage pauses and unserved energy are shown explicitly. Charging is a separate flow, not hospital consumption."})

    @app.post("/api/outage/simulate")
    def outage(request: OutageRequest):
        carry = app.state.store.carry(request.date, request.settings.battery_capacity_kwh)
        start = carry["energy_kwh"]
        if request.initial_soc_pct_override is not None:
            start = request.settings.battery_capacity_kwh * request.initial_soc_pct_override / 100
            carry = {"energy_kwh": start, "from_date": None, "source": "rehearsal-only opening override", "note": "Not saved to battery history."}
        options = {"weather_snapshot": snapshot_for(request.plan_id, request.date)} if request.plan_id else {}
        forecast = make_forecast(request.date, "grid_outage", request.settings, request.forecast_overrides, **options)
        result = create_plan(forecast, request.settings, start, request.hourly_edits,
                             refill_hour=request.refill_hour, refill_to_pct=request.refill_to_pct, include_suggestions=False)
        result.update(date=str(request.date), day_type="grid_outage", battery_carry=carry,
                      settings=request.settings.model_dump(), saved_to_history=False, forecast=forecast,
                      note="Independent rehearsal. Refill represents a human report; failure is simulated. This action does not approve a day plan or alter stored carry.")
        display_values(result, request.settings)
        result["rehearsal"] = {
            "generator_started_at_hour": next((row["hour"] for row in result["hours"] if row["generator_running"]), None),
            "first_critical_shortfall_hour": next((row["hour"] for row in result["hours"] if row["critical_unserved_kwh"] > 1e-6), None),
            "refill_hour": request.refill_hour, "refill_to_pct": request.refill_to_pct,
            "failure_hour": request.settings.generator_failure_hour,
            "calculated_at": datetime.now(INDIA).isoformat(),
        }
        return envelope(result)

    @app.get("/api/presets")
    def presets():
        return envelope(builtin_presets() + app.state.store.presets())

    @app.post("/api/presets", status_code=201)
    def save_preset(request: PresetRequest):
        preset = request.model_dump(mode="json") | {"id": str(uuid4()), "built_in": False}
        app.state.store.save_preset(preset)
        return envelope(preset)

    @app.put("/api/presets/{preset_id}")
    def update_preset(preset_id: str, request: PresetRequest):
        if preset_id.startswith("builtin-"):
            raise HTTPException(403, "Built-in presets cannot be changed. Save a custom copy.")
        if not any(p["id"] == preset_id for p in app.state.store.presets()):
            raise HTTPException(404, "Custom preset not found.")
        preset = request.model_dump(mode="json") | {"id": preset_id, "built_in": False}
        app.state.store.save_preset(preset)
        return envelope(preset)

    @app.delete("/api/presets/{preset_id}")
    def delete_preset(preset_id: str):
        if preset_id.startswith("builtin-"):
            raise HTTPException(403, "Built-in presets cannot be deleted.")
        if not app.state.store.delete_preset(preset_id):
            raise HTTPException(404, "Custom preset not found.")
        return envelope({"deleted": preset_id})

    @app.post("/api/assistant")
    async def assistant(request: AssistantRequest):
        plan = forecast = None
        if conversation_scope(request.message) == "gridwell":
            plan = load_plan(request.plan_id) if request.plan_id else None
            forecast = None if plan else await run_in_threadpool(make_forecast, request.date or local_today() + timedelta(days=1), request.day_type, Settings())
        reply = await app.state.assistant.reply(request.message, plan, forecast)
        result = envelope(reply)
        result["meta"]["simulated"] = reply["uses_simulated_data"]
        return result

    @app.post("/api/demo/reset")
    def reset(request: ResetRequest):
        counts = app.state.store.reset(request.initial_soc_pct)
        seed_history(app.state.store)
        history = app.state.store.history(8)
        return envelope({"reset": True, "initial_soc_pct": request.initial_soc_pct, **counts,
                         "history_records_created": len(history), "first_history_date": history[0]["date"],
                         "first_history_battery_kwh": history[0]["battery_soc_start_kwh"],
                         "note": "Saved plans, hourly edits and approvals were cleared. Eight deterministic example days were rebuilt; identical forecasts are expected with the same inputs. Custom presets were kept."})

    @app.get("/api/plans/{plan_id}/export.csv")
    def export(plan_id: str):
        import csv
        import io
        plan = load_plan(plan_id)
        output = io.StringIO()
        fields = [key for key, val in plan["hours"][0].items() if not isinstance(val, (dict, list))]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(plan["hours"])
        return Response(output.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="gridwell-{plan["date"]}.csv"'})

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}")
        def frontend(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Unknown API route.")
            return FileResponse(FRONTEND_DIST / "index.html")
    return app


app = create_app()
