import React from 'react';
import { Field, Icon, NumberField, Toggle } from './components';
import { useWorkspace } from './context';

export function PlanningControls({ compact = false, settings, onChange }) {
  const w = useWorkspace(), s = settings || w.settings, update = onChange || w.updateSetting;
  const numeric = (key, label, min, max, step = 1, help) => <NumberField key={key} label={label} value={s[key]}
    onChange={value => update(key, value)} min={min} max={max} step={step} help={help}/>;
  return <fieldset className="resource-controls" disabled={!!w.busy}>
    <legend className="sr-only">Equipment, comfort and work settings</legend>
    <div className="resource-panels">
      <section className="resource-panel"><h3><Icon name="battery"/>Battery operating choices</h3>
        {numeric('reserve_pct', 'Normal battery reserve (%)', 10, 90, 1, 'Energy held back during normal grid operation. The outage generator threshold stays fixed at 10%.')}
        <Toggle label="Allow battery charging from the grid" checked={s.allow_grid_charging} onChange={value => update('allow_grid_charging', value)}
          help="The plan may charge in better hours; cost, emissions and battery losses are counted."/>
      </section>
      <section className="resource-panel"><h3><Icon name="people"/>Indoor comfort limits</h3>
        <div className="controls-grid two">{numeric('comfort_min_c', 'Lowest allowed indoor temperature (°C)', 16, 29, .5)}{numeric('comfort_max_c', 'Highest allowed indoor temperature (°C)', 17, 32, .5)}</div>
        <p>These are operator-selected simulation limits, not clinical standards. Heatwave weather increases cooling demand; it does not silently relax these limits.</p>
      </section>
      <section className="resource-panel full"><h3><Icon name="plan"/>When flexible work may run</h3>
        <p>Laundry and water heating can move inside these windows. Critical medical demand cannot move. Hours use 0–24; 24 means midnight at the end of the day.</p>
        <div className="controls-grid">{numeric('laundry_start', 'Laundry may start from hour', 0, 23)}{numeric('laundry_end', 'Laundry must finish by hour', 1, 24)}
          {numeric('water_heating_start', 'Water heating may start from hour', 0, 23)}{numeric('water_heating_end', 'Water heating must finish by hour', 1, 24)}
          {numeric('flexible_power_kw', 'Power available per activity (kW)', 1, 500, 1, 'A narrow window or low power limit can make the daily work impossible.')}</div>
      </section>
    </div>
    {s.objective === 'custom' && <div className="resource-panel spaced"><h3>Custom planning priorities</h3><div className="controls-grid two">
      {numeric('cost_weight', 'Relative cost weight (0–1)', 0, 1, .05)}{numeric('carbon_weight', 'Relative emissions weight (0–1)', 0, 1, .05)}
    </div><p>Python normalizes these weights. At least one must be greater than zero.</p></div>}
    {!compact && <>
      <details className="settings-details inventory"><summary>Solar array & battery inventory <span>Set the equipment you have; choosing a goal does not change it</span></summary>
        <div className="controls-grid">{numeric('solar_capacity_kwp', 'Installed solar capacity (kWp)', 0, 2000)}{numeric('battery_capacity_kwh', 'Battery energy capacity (kWh)', 100, 10000)}
          {numeric('battery_power_kw', 'Maximum charge / discharge power (kW)', 1, 2000)}{numeric('charge_efficiency', 'Charging efficiency (0.5–1)', .5, 1, .01)}{numeric('discharge_efficiency', 'Discharging efficiency (0.5–1)', .5, 1, .01)}</div>
      </details>
      <details className="settings-details inventory"><summary>Power-cut window & generator inventory <span>Used when Grid outage is selected; a separate rehearsal is available on Outage Readiness</span></summary>
        <div className="controls-grid">{numeric('outage_start', 'Power cut starts at hour', 0, 23)}{numeric('outage_end', 'Power returns at hour', 1, 24)}
          {numeric('generator_capacity_kw', 'Generator power capacity (kW)', 0, 2000)}{numeric('generator_tank_litres', 'Fuel tank capacity (litres)', 1, 10000)}
          {numeric('generator_fuel_pct', 'Opening tank fuel (%)', 0, 100)}{numeric('generator_litres_per_kwh', 'Fuel consumption (litres/kWh)', .01, 2, .01)}
          {numeric('generator_fuel_inr_per_litre', 'Fuel cost (₹/litre)', 0, 500)}{numeric('generator_emissions_kg_per_litre', 'Fuel emissions (kg CO2e/litre)', 0, 10, .01)}</div>
        <Toggle label="Generator available" checked={s.generator_available} onChange={value => update('generator_available', value)}/>
        <Field label="Generator failure hour (optional)" help="Blank means no failure. This is a simulation event, not an equipment command.">
          <input type="number" min="0" max="23" placeholder="No failure" value={s.generator_failure_hour ?? ''} onChange={event => update('generator_failure_hour', event.target.value === '' ? null : Number(event.target.value))}/>
        </Field>
      </details>
    </>}
  </fieldset>;
}
