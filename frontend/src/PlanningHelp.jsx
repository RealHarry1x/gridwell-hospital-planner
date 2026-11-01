import React from 'react';
import { hourLabel, number } from './api';
import { Badge, Card, Icon } from './components';
import { useWorkspace } from './context';

export function weatherSource(forecast) {
  return typeof forecast?.source === 'object'
    ? forecast.source.weather_source
    : 'Saved synthetic forecast · created before weather integration';
}

export function WeatherStrip({ forecast, compact = false }) {
  const source = weatherSource(forecast);
  return <Card title="Weather behind the solar estimate" subtitle={`${forecast.source?.weather_location?.name || 'Saved location'} · ${forecast.date} · Asia/Kolkata`}
    action={<Badge tone={forecast.weather_hours ? 'green' : 'amber'}>{source}</Badge>} className="weather-card spaced">
    <p className="muted">Solar potential means the energy your array could generate on this day. With live weather, Python estimates solar energy from forecast sunlight, your array size and a 0.8 performance ratio. Offline, a repeatable synthetic sunlight profile is used. Hospital demand remains simulated.</p>
    {forecast.weather_strip ? <div className="weather-strip" tabIndex={0} aria-label="Hourly weather, scroll horizontally">
      {forecast.weather_strip.map(row => <div className="weather-hour" key={row.hour}>
        <small>{hourLabel(row.hour)}</small><Icon name="solar" size={17}/>
        <b>{number(row.temperature_c, 1)}°C</b><span>{number(row.cloud_cover_pct)}% cloud</span>
        {!compact && <><span>{number(row.radiation_wm2)} W/m²</span><strong>{number(row.solar_expected_kwh, 1)} kWh solar</strong></>}
      </div>)}
    </div> : <div className="soft-note">This older plan has no hourly weather snapshot. Its saved energy values are preserved. Generate a new plan to use the weather integration.</div>}
    <p className="muted small-text">The strip shows base weather before stress-test modifiers. {forecast.day_type === 'heatwave' && 'The heatwave scenario adds 7°C to outdoor temperatures and increases cooling demand. '}
      {forecast.day_type === 'low_solar' && 'The low-solar scenario reduces the solar estimate to 24%. '}
      {forecast.weather_hours ? 'Open-Meteo provides forecasts, not live observations. Weather is cached for one hour and frozen in saved plans.' : 'The offline fallback uses repeatable synthetic weather; it does not claim a live forecast.'}
      {' '}<a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Weather data: Open-Meteo</a>
    </p>
  </Card>;
}

export function GoalChoices({ settings, onChange }) {
  const w = useWorkspace(), selected = settings || w.settings;
  const update = onChange || w.updateSetting;
  return <div className="goal-cards" role="group" aria-label="Choose a planning priority">
    {(w.config.goals || []).map(goal => <button type="button" key={goal.id} className={`choice-card ${selected.objective === goal.id ? 'is-selected' : ''}`}
      aria-pressed={selected.objective === goal.id} disabled={!!w.busy} onClick={() => update('objective', goal.id)}>
      <strong>{goal.name}</strong><b>{goal.weights}</b><span>{goal.description}</span><small>{goal.tradeoff}</small>
    </button>)}
  </div>;
}

export function ScenarioChooser() {
  const w = useWorkspace(), guidance = w.forecast.planning_guidance;
  return <Card title="1. Choose the conditions to plan for" subtitle="Review the weather, then choose a base day or a stress test. You make the choice.">
    {guidance && <div className="guidance-banner"><Icon name="solar"/><div><b>Weather-based suggestion: {w.config.day_types.find(item => item.id === guidance.suggested_day_type)?.name}</b>
      <p>{guidance.reason}</p><small>{guidance.method}</small></div>
      {guidance.suggested_day_type !== w.dayType && <button type="button" className="button small" disabled={!!w.busy} onClick={() => w.changeDayType(guidance.suggested_day_type)}>Choose suggested day</button>}
    </div>}
    <div className="scenario-cards" role="group" aria-label="Choose a day scenario">{w.config.day_types.map(type => <button type="button" key={type.id}
      className={`choice-card ${type.id === w.dayType ? 'is-selected' : ''}`} aria-pressed={type.id === w.dayType} disabled={!!w.busy} onClick={() => w.changeDayType(type.id)}>
      <strong>{type.name}</strong><span>{type.description}</span><small>{type.effect}</small>
    </button>)}</div>
    <div className="scenario-facts"><span>Scenario outdoor temperature <b>{number(w.forecast.daily.outdoor_min_c, 1)}–{number(w.forecast.daily.outdoor_max_c, 1)}°C</b></span>
      <span>Simulated cooling demand <b>{number(w.forecast.daily.hvac_kwh)} kWh</b></span>
      <span>Solar potential <b>{number(w.forecast.daily.solar_kwh.expected)} kWh</b></span>
    </div>
    {guidance && <div className="profile-preview"><div><h3>Optional working settings for this scenario</h3><p>{guidance.comfort_note}</p>
      <ul>{guidance.settings_preview.map(line => <li key={line}>{line}</li>)}</ul><small>{guidance.apply_notice} Applying clears manual hourly overrides.</small></div>
      <button type="button" className="button" disabled={!!w.busy} onClick={w.applyScenarioSettings}>Apply suggested working settings</button>
    </div>}
    <button type="button" className="text-button spaced" disabled={!!w.busy} onClick={() => w.askGuide('Explain the weather forecast and the suggested day type for my energy plan. Why is the indoor comfort limit separate?')}>Ask AI Guide to explain the weather and day type <Icon name="arrow" size={15}/></button>
  </Card>;
}
