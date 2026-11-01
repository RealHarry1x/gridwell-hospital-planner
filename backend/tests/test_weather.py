"""Real weather is optional; every provider request here is intercepted."""

from copy import deepcopy
from datetime import timedelta

import httpx
import pytest

from app import weather
from app.forecast import SOLAR_PERFORMANCE_RATIO, make_forecast
from app.models import Settings


def provider_data():
    today = weather.datetime.now(weather.INDIA).date()
    stamps = [f'{today + timedelta(days=offset)}T{hour:02d}:00' for offset in range(3) for hour in range(24)]
    return {'hourly': {'time': stamps, 'temperature_2m': [28.0] * 72,
                       'cloud_cover': [35.0] * 72, 'shortwave_radiation': [800.0 if 7 <= hour < 18 else 0.0 for _ in range(3) for hour in range(24)]}}


@pytest.fixture
def provider(monkeypatch, tmp_path):
    monkeypatch.setattr(weather, 'PROJECT_ROOT', tmp_path)
    monkeypatch.delenv('WEATHER_LAT', raising=False)
    monkeypatch.delenv('WEATHER_LON', raising=False)
    payload, requests = provider_data(), []

    def get(url, *, params, timeout):
        requests.append({'url': url, 'params': deepcopy(params), 'timeout': timeout})
        return httpx.Response(200, json=deepcopy(payload), request=httpx.Request('GET', url))

    monkeypatch.setattr(weather.httpx, 'get', get)
    return payload, requests


def planning_day():
    return weather.datetime.now(weather.INDIA).date() + timedelta(days=1)


def test_fetch_and_radiation_solar_conversion_are_server_side(provider):
    _, requests = provider
    rows = weather.fetch_hourly_weather(planning_day())
    assert len(rows) == 24 and [row['hour'] for row in rows] == list(range(24))
    assert rows[12] == {'hour': 12, 'temperature_c': 28, 'cloud_cover_pct': 35, 'radiation_wm2': 800}
    fc = make_forecast(planning_day(), 'normal', Settings(solar_capacity_kwp=100))
    expected = 100 * .8 * SOLAR_PERFORMANCE_RATIO
    assert fc['hours'][12]['solar_kwh']['expected'] == pytest.approx(expected)
    assert fc['hours'][12]['solar_kwh']['low'] == pytest.approx(expected * .75)
    assert fc['hours'][12]['solar_kwh']['high'] == pytest.approx(expected * 1.25)
    assert fc['hours'][12]['outdoor_temperature_c'] == 28
    assert fc['source']['weather_source'] == weather.LIVE_SOURCE
    assert requests == [{'url': weather.URL, 'timeout': 10, 'params': {
        'latitude': 18.52, 'longitude': 73.86, 'hourly': 'temperature_2m,cloud_cover,shortwave_radiation',
        'forecast_days': 3, 'timezone': 'Asia/Kolkata'}}]


def test_cache_reuses_three_day_response_and_expires_after_one_hour(provider, monkeypatch):
    _, requests = provider
    clock = [10.0]
    monkeypatch.setattr(weather, 'monotonic', lambda: clock[0])
    rows = weather.fetch_hourly_weather(planning_day())
    rows[12]['temperature_c'] = 999
    assert weather.fetch_hourly_weather(planning_day())[12]['temperature_c'] == 28
    assert weather.fetch_hourly_weather(planning_day() + timedelta(days=1)) is not None
    assert len(requests) == 1
    clock[0] += 3601
    assert weather.fetch_hourly_weather(planning_day()) is not None
    assert len(requests) == 2


def test_coordinates_read_root_env_and_environment_override(provider, monkeypatch, tmp_path):
    _, requests = provider
    (tmp_path / '.env').write_text('WEATHER_LAT=31.326\nWEATHER_LON=75.576\nGEMINI_API_KEY=dummy-not-used\n')
    assert weather.fetch_hourly_weather(planning_day())
    assert requests[-1]['params']['latitude'] == 31.326
    monkeypatch.setenv('WEATHER_LAT', '30.34')
    monkeypatch.setenv('WEATHER_LON', '76.38')
    assert weather.fetch_hourly_weather(planning_day())
    assert requests[-1]['params']['latitude'] == 30.34
    assert requests[-1]['params']['longitude'] == 76.38


@pytest.mark.parametrize('failure', ['timeout', 'http', 'json', 'missing', 'null', 'nan', 'duplicate'])
def test_failure_never_raises_and_uses_repeatable_fallback(monkeypatch, failure):
    def get(url, **kwargs):
        if failure == 'timeout':
            raise httpx.ReadTimeout('Test timeout')
        if failure == 'http':
            return httpx.Response(503, request=httpx.Request('GET', url))
        if failure == 'json':
            return httpx.Response(200, content=b'not-json', request=httpx.Request('GET', url))
        payload = provider_data()
        if failure == 'missing':
            del payload['hourly']['cloud_cover']
        elif failure == 'null':
            payload['hourly']['shortwave_radiation'] = [None] * 72
        elif failure == 'nan':
            payload['hourly']['temperature_2m'] = ['not-a-number'] * 72
        else:
            payload['hourly']['time'][24:48] = [payload['hourly']['time'][24]] * 24
        return httpx.Response(200, json=payload, request=httpx.Request('GET', url))
    monkeypatch.setattr(weather.httpx, 'get', get)
    assert weather.fetch_hourly_weather(planning_day()) is None
    fc = make_forecast(planning_day(), 'normal', Settings())
    assert fc['source']['weather_source'] == weather.FALLBACK_SOURCE and fc['weather_hours'] is None
    assert fc == make_forecast(planning_day(), 'normal', Settings(), weather_snapshot=None)


def test_out_of_range_invalid_date_and_invalid_location_do_not_call_http(provider, monkeypatch):
    _, requests = provider
    assert weather.fetch_hourly_weather(planning_day() + timedelta(days=10)) is None
    assert weather.fetch_hourly_weather('not-a-date') is None
    monkeypatch.setenv('WEATHER_LAT', 'nan')
    assert weather.fetch_hourly_weather(planning_day()) is None
    assert requests == []


def test_scenarios_modify_live_inputs_without_changing_critical_floor_or_comfort(provider):
    settings = Settings()
    normal = make_forecast(planning_day(), 'normal', settings)
    hot = make_forecast(planning_day(), 'heatwave', settings)
    dark = make_forecast(planning_day(), 'low_solar', settings)
    outage = make_forecast(planning_day(), 'grid_outage', settings)
    assert hot['hours'][12]['outdoor_temperature_c'] == 35
    assert hot['daily']['hvac_kwh'] == pytest.approx(normal['daily']['hvac_kwh'] * 1.55, abs=.02)
    assert dark['daily']['solar_kwh']['expected'] == pytest.approx(normal['daily']['solar_kwh']['expected'] * .24, abs=.02)
    assert all(row['grid_available'] is False for row in outage['hours'][18:23])
    assert [row['critical_demand_kwh'] for row in hot['hours']] == [row['critical_demand_kwh'] for row in normal['hours']]
    patch = hot['planning_guidance']['settings_patch']
    assert 'comfort_min_c' not in patch and 'comfort_max_c' not in patch
    assert '22–26' in hot['planning_guidance']['comfort_note']


def test_saved_plan_weather_is_frozen_on_reload_verify_recalculate_and_rehearsal(client, provider):
    payload, requests = provider
    day = str(planning_day())
    plan = client.post('/api/plans/generate', json={'date': day}).json()['data']
    captured_weather = deepcopy(plan['forecast']['weather_hours'])
    assert captured_weather and len(requests) == 1
    payload['hourly']['temperature_2m'] = [17.0] * 72
    payload['hourly']['shortwave_radiation'] = [200.0] * 72
    weather.clear_cache()
    assert client.get(f"/api/plans/{plan['id']}").json()['data']['forecast']['weather_hours'] == captured_weather
    assert client.get(f'/api/plans?date={day}').json()['data']['forecast']['weather_hours'] == captured_weather
    verified = client.post('/api/forecast/verify', json={'date': day, 'plan_id': plan['id']}).json()['data']
    assert verified['weather_hours'] == captured_weather
    revised = client.post(f"/api/plans/{plan['id']}/recalculate", json={'date': day, 'settings': {'solar_capacity_kwp': 200}}).json()['data']
    assert revised['forecast']['weather_hours'] == captured_weather
    assert revised['forecast']['hours'][12]['solar_kwh']['expected'] == plan['forecast']['hours'][12]['solar_kwh']['expected'] * 2
    rehearsal = client.post('/api/outage/simulate', json={'date': day, 'plan_id': plan['id']}).json()['data']
    assert rehearsal['forecast']['weather_hours'] == captured_weather
    assert len(requests) == 1  # None of the saved-plan operations contacts the provider.
    fresh = client.get(f'/api/forecast?date={day}').json()['data']
    assert fresh['weather_hours'][12]['temperature_c'] == 17 and len(requests) == 2


def test_weather_route_labels_live_forecast_and_offline_fallback(client, provider):
    response = client.get(f'/api/weather?date={planning_day()}').json()
    assert response['meta']['simulated'] is False and response['data']['source'] == weather.LIVE_SOURCE
    assert len(response['data']['hours']) == 24
    response = client.get(f'/api/weather?date={planning_day() + timedelta(days=5)}').json()
    assert response['meta']['simulated'] is True and response['data']['hours'] is None
    assert response['data']['source'] == weather.FALLBACK_SOURCE


@pytest.mark.parametrize(('temperature', 'cloud', 'expected'), [(38, 20, 'heatwave'), (28, 90, 'low_solar'), (28, 20, 'normal')])
def test_weather_suggestion_is_transparent_and_never_predicts_an_outage(provider, temperature, cloud, expected):
    payload, _ = provider
    payload['hourly']['temperature_2m'] = [temperature] * 72
    payload['hourly']['cloud_cover'] = [cloud] * 72
    guidance = make_forecast(planning_day(), 'normal', Settings())['planning_guidance']
    assert guidance['suggested_day_type'] == expected
    assert 'Not an AI weather prediction' in guidance['method']
