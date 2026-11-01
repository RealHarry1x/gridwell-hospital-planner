"""Operator actions remain observable, deterministic and read-only on rehearsals."""


def test_reset_reports_changes_and_preserves_custom_presets(client):
    day = client.get('/api/config').json()['data']['tomorrow']
    plan = client.post('/api/plans/generate', json={'date': day}).json()['data']
    client.post('/api/presets', json={'name': 'Keep my equipment', 'settings': {'battery_capacity_kwh': 1200}})
    result = client.post('/api/demo/reset', json={'initial_soc_pct': 80}).json()['data']
    assert result['deleted_plans'] == 1 and result['deleted_history_records'] == 8
    assert result['kept_custom_presets'] == 1 and result['history_records_created'] == 8
    assert result['first_history_battery_kwh'] == 800
    assert client.get(f"/api/plans/{plan['id']}").status_code == 404
    assert client.get(f'/api/plans?date={day}').json()['data'] is None
    assert any(preset['name'] == 'Keep my equipment' for preset in client.get('/api/presets').json()['data'])


def test_recalculation_explains_same_inputs_and_records_new_revision(client):
    day = client.get('/api/config').json()['data']['tomorrow']
    original = client.post('/api/plans/generate', json={'date': day}).json()['data']
    same = client.post(f"/api/plans/{original['id']}/recalculate", json={'date': day}).json()['data']
    assert same['revision'] == 2 and same['calculation']['same_inputs'] is True
    assert same['summary'] == original['summary']
    assert all(value == 0 for value in same['changes'].values())
    changed = client.post(f"/api/plans/{original['id']}/recalculate", json={'date': day, 'settings': {'reserve_pct': 30}}).json()['data']
    assert changed['revision'] == 3 and changed['calculation']['same_inputs'] is False
    assert changed['settings']['reserve_pct'] == 30 and changed['display']['normal_reserve_kwh'] == 300


def test_seven_day_demand_context_is_honest_and_excludes_future_history(client):
    day = client.get('/api/config').json()['data']['tomorrow']
    result = client.get(f'/api/demand-context?date={day}').json()['data']
    assert len(result['days']) == 7 and all(row['date'] < day for row in result['days'])
    assert result['average_kwh'] == round(sum(row['energy_kwh'] for row in result['days']) / 7, 2)
    assert result['history_used_for_forecast'] is False
    assert 'not training data' in result['method']
    early = client.get('/api/demand-context?date=2000-01-01').json()['data']
    assert early['days'] == [] and early['average_kwh'] is None


def test_goal_presets_identify_goal_only_changes(client):
    presets = client.get('/api/presets').json()['data']
    assert len(presets) == 3
    for preset in presets:
        assert preset['scope'] == 'goal_only'
        assert preset['settings_patch'] == {'objective': preset['settings']['objective']}
        assert preset['goal']['weights']


def test_rehearsal_details_do_not_edit_day_plan_or_battery_history(client):
    day = client.get('/api/config').json()['data']['tomorrow']
    plan = client.post('/api/plans/generate', json={'date': day}).json()['data']
    history = client.get('/api/trends').json()['data']
    result = client.post('/api/outage/simulate', json={'date': day, 'plan_id': plan['id'],
        'settings': {'outage_start': 0, 'outage_end': 8, 'generator_available': False, 'allow_grid_charging': False},
        'initial_soc_pct_override': 10}).json()['data']
    assert result['saved_to_history'] is False and result['rehearsal']['first_critical_shortfall_hour'] is not None
    assert result['display']['generator_threshold_kwh'] == 100
    assert client.get(f"/api/plans/{plan['id']}").json()['data'] == plan
    assert client.get('/api/trends').json()['data'] == history
