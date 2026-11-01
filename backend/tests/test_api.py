from datetime import date, timedelta

import pytest


def data(response, status=200):
    assert response.status_code == status, response.text
    body = response.json()
    assert body["meta"]["simulated"] is True
    return body["data"]


def tomorrow(client):
    return data(client.get('/api/config'))['tomorrow']


def generate(client, **kwargs):
    return data(client.post('/api/plans/generate', json={'date': tomorrow(client), **kwargs}), 201)


def test_forecast_is_stable_and_adjustment_keeps_original(client):
    day = tomorrow(client)
    f = data(client.get(f'/api/forecast?date={day}&day_type=normal'))
    assert f == data(client.get(f'/api/forecast?date={day}&day_type=normal'))
    original = f['hours'][12]['demand_kwh'].copy()
    verified = data(client.post('/api/forecast/verify', json={'date': day, 'forecast_overrides': [{'hour': 12, 'field': 'demand_kwh', 'value': 900}]}))
    assert verified['hours'][12]['demand_kwh'] == original
    assert verified['hours'][12]['adjusted']['demand_kwh'] == 900
    assert verified['adjustments'][0]['outside_range']
    assert verified['warnings']


def test_core_flow_generate_edit_recalculate_approve_compare_and_assistant(client):
    p = generate(client)
    assert len(p['hours']) == 24 and p['valid']
    payload = p['input']
    payload['settings']['objective'] = 'cost'
    payload['hourly_edits'] = [{'hour': 10, 'laundry_kwh': 30}]
    revised = data(client.post(f"/api/plans/{p['id']}/recalculate", json=payload))
    assert revised['revision'] == 2 and revised['valid']
    assert revised['hours'][10]['flexible_loads_kwh']['laundry'] == 30
    assert 'changes' in revised
    assert revised['changes']['cost_inr'] == pytest.approx(revised['summary']['cost_inr'] - p['summary']['cost_inr'])
    approved = data(client.post(f"/api/plans/{p['id']}/approve", json={'revision': 2}))
    assert approved['status'] == 'approved'
    comparison = data(client.get(f"/api/plans/{p['date']}/comparison?plan_id={p['id']}"))
    assert comparison['recommended'] == approved['summary']
    breakdown = data(client.get(f"/api/energy-breakdown?date={p['date']}&plan_id={p['id']}"))
    assert sum(v['energy_kwh'] for v in breakdown['consumption']) == pytest.approx(approved['summary']['demand_kwh'])
    response = data(client.post('/api/assistant', json={'message': 'How much does this cost?', 'plan_id': p['id']}))
    assert response['context']['revision'] == 2
    assert f"{approved['summary']['cost_inr']:,.2f}" in response['answer']
    assert 'sample' in response['mode'].lower()
    csv = client.get(f"/api/plans/{p['id']}/export.csv")
    assert csv.status_code == 200 and 'battery_soc_end_kwh' in csv.text


def test_invalid_draft_and_old_revision_cannot_be_approved(client):
    p = generate(client, hourly_edits=[{'hour': 12, 'grid_charge_kwh': 999}])
    assert not p['valid']
    assert client.post(f"/api/plans/{p['id']}/approve", json={'revision': 1}).status_code == 409
    payload = p['input']
    payload['hourly_edits'] = []
    fixed = data(client.post(f"/api/plans/{p['id']}/recalculate", json=payload))
    assert fixed['valid']
    assert client.post(f"/api/plans/{p['id']}/approve", json={'revision': 1}).status_code == 409
    assert client.post(f"/api/plans/{p['id']}/approve", json={'revision': 2}).status_code == 200


def test_battery_carry_survives_day_selection_and_outage_approval(client):
    day = tomorrow(client)
    first = generate(client, day_type='grid_outage', settings={'outage_end': 24})
    assert first['valid']
    data(client.post(f"/api/plans/{first['id']}/approve", json={'revision': 1}))
    next_day = str(date.fromisoformat(day) + timedelta(days=1))
    carry = data(client.get(f'/api/config?date={next_day}'))['battery_carry']
    assert carry['energy_kwh'] == pytest.approx(first['summary']['battery_soc_end_kwh'])
    assert carry['from_date'] == day
    for scenario in ('heatwave', 'normal', 'low_solar'):
        data(client.get(f'/api/forecast?date={next_day}&day_type={scenario}'))
    assert data(client.get(f'/api/config?date={next_day}'))['battery_carry'] == carry
    next_plan = data(client.post('/api/plans/generate', json={'date': next_day}), 201)
    assert next_plan['summary']['battery_soc_start_kwh'] == carry['energy_kwh']


def test_approval_is_idempotent_and_earlier_reapproval_invalidates_future(client):
    p = generate(client)
    data(client.post(f"/api/plans/{p['id']}/approve", json={'revision': 1}))
    following = str(date.fromisoformat(p['date']) + timedelta(days=1))
    q = data(client.post('/api/plans/generate', json={'date': following}), 201)
    data(client.post(f"/api/plans/{q['id']}/approve", json={'revision': 1}))
    data(client.post(f"/api/plans/{p['id']}/approve", json={'revision': 1}))
    assert data(client.get(f"/api/plans/{q['id']}"))['status'] == 'approved'
    payload = p['input']; payload['settings']['reserve_pct'] = 25
    revised = data(client.post(f"/api/plans/{p['id']}/recalculate", json=payload))
    assert revised['valid']
    data(client.post(f"/api/plans/{p['id']}/approve", json={'revision': 2}))
    assert data(client.get(f"/api/plans/{q['id']}"))['status'] == 'stale'
    assert client.post(f"/api/plans/{q['id']}/approve", json={'revision': 1}).status_code == 409


def test_custom_presets_crud_and_protected_rules(client):
    builtins = data(client.get('/api/presets'))
    assert len(builtins) == 3
    p = data(client.post('/api/presets', json={'name': 'Team demo', 'settings': {'objective': 'custom', 'cost_weight': .8, 'carbon_weight': .2}}), 201)
    p2 = data(client.put(f"/api/presets/{p['id']}", json={'name': 'Team demo revised', 'settings': {'reserve_pct': 30}}))
    assert p2['settings']['reserve_pct'] == 30
    assert any(r['id'] == p['id'] for r in data(client.get('/api/presets')))
    assert client.delete('/api/presets/builtin-balanced').status_code == 403
    assert client.post('/api/presets', json={'name': 'Unsafe', 'settings': {'protect_critical': False}}).status_code == 422
    data(client.delete(f"/api/presets/{p['id']}"))
    assert len(data(client.get('/api/presets'))) == 3


def test_outage_rehearsal_failure_refill_and_no_carry_write(client):
    day = tomorrow(client)
    before = data(client.get('/api/config'))['battery_carry']
    base = {'date': day, 'settings': {'outage_start': 0, 'outage_end': 12, 'generator_available': False, 'allow_grid_charging': False}, 'initial_soc_pct_override': 10}
    failed = data(client.post('/api/outage/simulate', json=base))
    assert not failed['valid'] and failed['summary']['critical_unserved_kwh'] > 0
    assert failed['saved_to_history'] is False
    assert data(client.get('/api/config'))['battery_carry'] == before
    refill = data(client.post('/api/outage/simulate', json={'date': day, 'initial_soc_pct_override': 10, 'settings': {'outage_start': 0, 'outage_end': 5, 'generator_fuel_pct': 20}, 'refill_hour': 1}))
    assert refill['hours'][1]['generator_fuel_added_litres'] > 0


def test_validation_and_cross_origin_writes(client):
    day = tomorrow(client)
    assert client.post('/api/plans/generate', json={'date': day, 'settings': {'comfort_min_c': 28, 'comfort_max_c': 24}}).status_code == 422
    assert client.post('/api/forecast/verify', json={'date': day, 'forecast_overrides': [{'hour': 1, 'field': 'occupancy_pct', 'value': 105}]}).status_code == 422
    assert client.post('/api/plans/generate', json={'date': day}, headers={'Origin': 'https://unrelated.example'}).status_code == 403
    assert client.post('/api/plans/generate', json={'date': day}, headers={'Origin': 'http://testserver'}).status_code == 201


def test_forecast_cannot_delete_critical_medical_demand(client):
    day = tomorrow(client)
    original = data(client.get(f'/api/forecast?date={day}'))['hours'][12]['critical_demand_kwh']
    p = generate(client, forecast_overrides=[{'hour': 12, 'field': 'demand_kwh', 'value': 0}])
    assert not p['valid']
    assert p['hours'][12]['critical_demand_kwh'] >= original
    assert any(w['code'] == 'critical_forecast_floor' for w in p['warnings'])
    assert client.post(f"/api/plans/{p['id']}/approve", json={'revision': 1}).status_code == 409


def test_reset_uses_adjustable_first_day_assumption_and_keeps_presets(client):
    data(client.post('/api/presets', json={'name': 'Keep me', 'settings': {}}), 201)
    p = generate(client)
    data(client.post('/api/demo/reset', json={'initial_soc_pct': 80}))
    assert client.get(f"/api/plans/{p['id']}").status_code == 404
    history = data(client.get('/api/trends?days=30'))['days']
    assert history[0]['battery_soc_start_kwh'] == 800
    assert any(p['name'] == 'Keep me' for p in data(client.get('/api/presets')))
