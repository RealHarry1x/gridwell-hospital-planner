"""Generate disposable UI fixtures through FastAPI; no network or real key."""

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app import weather
from app.ai_config import AssistantConfig
from app.assistant import AssistantService
from app.forecast import make_forecast
from app.main import create_app
from app.models import Settings


def export(destination):
    with TemporaryDirectory(prefix='gridwell-ui-fixtures-') as directory, patch.object(weather, 'fetch_hourly_weather', return_value=None):
        with TestClient(create_app(Path(directory) / 'ui.sqlite3', assistant_service=AssistantService(AssistantConfig()))) as client:
            config = client.get('/api/config').json()['data']
            day = config['tomorrow']
            forecasts = {scenario: client.get(f'/api/forecast?date={day}&day_type={scenario}&solar_capacity_kwp=150').json()['data']
                         for scenario in ('normal', 'heatwave', 'low_solar', 'grid_outage')}
            initial = client.post('/api/plans/generate', json={'date': day, 'settings': {
                'solar_capacity_kwp': 150, 'battery_capacity_kwh': 1500, 'reserve_pct': 25}}).json()['data']
            client.post('/api/presets', json={'name': 'Team resource setup', 'settings': {'battery_capacity_kwh': 1200, 'reserve_pct': 35}})
            fixtures = {'config': config, 'forecasts': forecasts, 'initial': initial,
                        'presets': client.get('/api/presets').json()['data'],
                        'history': client.get('/api/trends').json()['data'],
                        'demand_context': client.get(f"/api/demand-context?date={day}&plan_id={initial['id']}").json()['data']}
            fixtures['same'] = client.post(f"/api/plans/{initial['id']}/recalculate", json=initial['input']).json()['data']
            client.app.state.store.save_plan(initial)
            body = deepcopy(initial['input'])
            body['settings']['reserve_pct'] = 30
            fixtures['changed'] = client.post(f"/api/plans/{initial['id']}/recalculate", json=body).json()['data']
            client.app.state.store.save_plan(initial)
            fixtures['outage'] = client.post('/api/outage/simulate', json={
                'date': day, 'plan_id': initial['id'], 'initial_soc_pct_override': 10,
                'settings': {**initial['settings'], 'outage_start': 0, 'outage_end': 8, 'generator_available': False},
            }).json()['data']
            fixtures['reset'] = client.post('/api/demo/reset', json={'initial_soc_pct': 80}).json()['data']
            fixtures['reset_config'] = client.get('/api/config').json()['data']
            fixtures['reset_history'] = client.get('/api/trends').json()['data']
            fixtures['reset_forecast'] = client.get(f'/api/forecast?date={day}').json()['data']
            live = [{'hour': hour, 'temperature_c': 28, 'cloud_cover_pct': 45,
                     'radiation_wm2': 500 if 7 <= hour < 18 else 0} for hour in range(24)]
            fixtures['live_forecast'] = make_forecast(date.fromisoformat(day), 'normal', Settings(), weather_snapshot={
                'weather_hours': live, 'source': {'weather_location': {'name': 'Pune, India'}, 'weather_fetched_at': f'{day}T00:00:00+05:30'}})
        with TestClient(create_app(Path(directory) / 'new-draft.sqlite3', assistant_service=AssistantService(AssistantConfig()))) as client:
            fixtures['fresh'] = client.post('/api/plans/generate', json=initial['input']).json()['data']
    Path(destination).write_text(json.dumps(fixtures))


if __name__ == '__main__':
    export(sys.argv[1])
