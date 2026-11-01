"""Optional Open-Meteo forecasts. No key, raw error logging or caller failures."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import math
import os
from pathlib import Path
from threading import Lock
from time import monotonic

from dotenv import dotenv_values
import httpx

URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 10
CACHE_SECONDS = 3600
LIVE_SOURCE = "Open-Meteo live forecast"
FALLBACK_SOURCE = "Synthetic fallback (live weather unavailable)"
INDIA = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CACHE = {}
_LOCK = Lock()


def location():
    """Only public coordinates are returned; other .env values stay private."""
    try:
        values = dotenv_values(PROJECT_ROOT / ".env", interpolate=False)
        lat = float(os.environ.get("WEATHER_LAT", values.get("WEATHER_LAT") or "18.52"))
        lon = float(os.environ.get("WEATHER_LON", values.get("WEATHER_LON") or "73.86"))
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Invalid coordinates")
        return {"latitude": lat, "longitude": lon, "timezone": "Asia/Kolkata",
                "name": "Pune, India" if (lat, lon) == (18.52, 73.86) else "Configured weather location", "valid": True}
    except Exception:
        return {"latitude": None, "longitude": None, "timezone": "Asia/Kolkata",
                "name": "Weather location unavailable", "valid": False}


def _number(value, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Missing weather value")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("Invalid weather value")
    return float(value)


def _parse_day(payload, day):
    hourly = payload["hourly"]
    times = hourly["time"]
    fields = [hourly[name] for name in ("temperature_2m", "cloud_cover", "shortwave_radiation")]
    if not isinstance(times, list) or any(not isinstance(values, list) or len(values) != len(times) for values in fields):
        raise ValueError("Incomplete hourly weather")
    rows = {}
    for index, stamp in enumerate(times):
        moment = datetime.fromisoformat(stamp)
        if moment.date() != day:
            continue
        if moment.minute or moment.second or moment.hour in rows:
            raise ValueError("Invalid hourly timestamps")
        rows[moment.hour] = {
            "hour": moment.hour,
            "temperature_c": _number(fields[0][index], -100, 80),
            "cloud_cover_pct": _number(fields[1][index], 0, 100),
            "radiation_wm2": _number(fields[2][index], 0, 2000),
        }
    if set(rows) != set(range(24)):
        raise ValueError("Date outside the complete forecast")
    return [rows[hour] for hour in range(24)]


def fetch_hourly_weather(planning_date):
    """Return 24 local hourly dictionaries or None; cache all three days 1h.

    Failed requests are cached too, so offline navigation does not repeatedly
    wait ten seconds. Historical seeded records always use synthetic weather.
    """
    try:
        day = date.fromisoformat(str(planning_date))
        today = datetime.now(INDIA).date()
        if not today <= day < today + timedelta(days=3):
            return None
        place = location()
        if not place["valid"]:
            return None
        key = (place["latitude"], place["longitude"], str(day))
        with _LOCK:
            now = monotonic()
            cached = _CACHE.get(key)
            if cached and cached[0] > now:
                return deepcopy(cached[1])
            for old_key in list(_CACHE):
                if _CACHE[old_key][0] <= now:
                    del _CACHE[old_key]
            try:
                response = httpx.get(URL, params={
                    "latitude": place["latitude"], "longitude": place["longitude"],
                    "hourly": "temperature_2m,cloud_cover,shortwave_radiation",
                    "forecast_days": 3, "timezone": "Asia/Kolkata",
                }, timeout=TIMEOUT_SECONDS)
                response.raise_for_status()
                payload = response.json()
                fetched_at = datetime.now(INDIA).isoformat()
                for offset in range(3):
                    forecast_day = today + timedelta(days=offset)
                    try:
                        rows = _parse_day(payload, forecast_day)
                    except Exception:
                        rows = None
                    _CACHE[(place["latitude"], place["longitude"], str(forecast_day))] = (
                        monotonic() + CACHE_SECONDS, rows, fetched_at if rows else None)
            except Exception:
                for offset in range(3):
                    forecast_day = today + timedelta(days=offset)
                    _CACHE[(place["latitude"], place["longitude"], str(forecast_day))] = (monotonic() + CACHE_SECONDS, None, None)
            return deepcopy(_CACHE[key][1])
    except Exception:
        return None


def fetched_at(planning_date):
    place = location()
    with _LOCK:
        cached = _CACHE.get((place["latitude"], place["longitude"], str(planning_date)))
        return cached[2] if cached else None


def clear_cache():
    """Used by isolated tests; saved plans never depend on this cache."""
    with _LOCK:
        _CACHE.clear()
