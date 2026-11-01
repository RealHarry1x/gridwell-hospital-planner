import React, { useState } from 'react';
import { api, hourLabel, number } from '../api';
import { Badge, Card, Checks, Field, Icon, LineChart, NumberField, PageTitle, SafetySummary, Stat, Toggle, Warnings } from '../components';
import { weatherSource } from '../PlanningHelp';
import { useWorkspace } from '../context';

export function Outage() {
  const w = useWorkspace();
  const [local, setLocal] = useState({ ...w.settings });
  const [failure, setFailure] = useState(w.settings.generator_failure_hour != null);
  const [failureHour, setFailureHour] = useState(w.settings.generator_failure_hour ?? w.settings.outage_start);
  const [refill, setRefill] = useState(false), [refillHour, setRefillHour] = useState(w.settings.outage_start);
  const [refillTo, setRefillTo] = useState(100), [startOverride, setStartOverride] = useState('');
  const [includeEdits, setIncludeEdits] = useState(true);
  const [result, setResult] = useState(null), [changed, setChanged] = useState(false);
  const carry = w.plan?.battery_carry || w.config.battery_carry;
  const update = (key, value) => {
    setLocal(current => ({ ...current, [key]: value })); setChanged(true);
    // Copy the selected hour, without computing a new schedule in the browser.
    // Once an event is enabled, retain the operator's explicit event time.
    if (key === 'outage_start') { if (!failure) setFailureHour(value); if (!refill) setRefillHour(value); }
  };
  const change = setter => value => { setter(value); setChanged(true); };
  const numeric = (key, label, min, max, step = 1, help) => <NumberField label={label} value={local[key]} onChange={value => update(key, value)} min={min} max={max} step={step} help={help}/>;

  async function rehearse(event) {
    event.preventDefault();
    await w.act('Running your outage rehearsal…', async () => {
      const body = w.requestBody({ day_type: 'grid_outage', plan_id: w.plan?.id || null,
        settings: { ...local, generator_failure_hour: failure ? failureHour : null },
        initial_soc_pct_override: startOverride === '' ? null : Number(startOverride),
        hourly_edits: includeEdits ? w.hourlyEdits : [], refill_hour: refill ? refillHour : null, refill_to_pct: refillTo });
      const next = await api('/outage/simulate', { method: 'POST', body });
      setResult(next); setChanged(false);
      w.notify('Outage rehearsal finished. Results are below; your day plan and battery history were kept.');
    });
  }
  function restore() {
    setLocal({ ...w.settings }); setFailure(w.settings.generator_failure_hour != null);
    setFailureHour(w.settings.generator_failure_hour ?? w.settings.outage_start); setRefillHour(w.settings.outage_start); setRefill(false); setStartOverride(''); setChanged(true);
  }
  return <>
    <PageTitle eyebrow="TEST A POWER CUT · NO EQUIPMENT COMMANDS" title="Rehearse the outage."
      description="Choose the power-cut window, available backup and failure events. Run the test, then inspect coverage hour by hour."
      action={<Badge>INDEPENDENT SIMULATION</Badge>}/>
    <div className="outage-rule-banner"><Icon name="outage" size={30}/><div><h2>The backup sequence stays protected.</h2>
      <p>During the cut: solar and battery first, generator at 10% battery, final emergency battery if the generator fails or fuel runs out. Critical demand is served before noncritical work.</p>
    </div></div>
    <form onSubmit={rehearse}>
      <fieldset className="resource-controls" disabled={!!w.busy}>
        <legend className="sr-only">Outage rehearsal controls</legend>
        <div className="grid two-cols">
          <Card title="1. Choose the power-cut window" subtitle="Local hours · start included, end excluded · 24 is midnight">
            <div className="controls-grid two">{numeric('outage_start', 'Power cut starts at hour', 0, 23)}{numeric('outage_end', 'Power returns at hour', 1, 24)}</div>
            <Field label="Beginning-of-day battery override (%)" help={`Blank uses ${number(carry.energy_kwh)} kWh from recorded carry. The override is for this rehearsal only, before any pre-outage charging.`}>
              <input type="number" min="0" max="100" placeholder="Use recorded carry" value={startOverride} onChange={event => change(setStartOverride)(event.target.value)}/>
            </Field>
            <Toggle label="Include my current hourly edits" checked={includeEdits} onChange={change(setIncludeEdits)} help="Leave off to test the resources without manual battery or work overrides."/>
          </Card>
          <Card title="2. Set the backup available" subtitle="These controls affect this test; they do not edit your day plan.">
            <Toggle label="Generator is available" checked={local.generator_available} onChange={value => update('generator_available', value)}/>
            <div className="controls-grid two">{numeric('generator_capacity_kw', 'Generator power (kW)', 0, 2000)}{numeric('generator_fuel_pct', 'Opening tank fuel (%)', 0, 100)}
              {numeric('generator_tank_litres', 'Fuel tank size (litres)', 1, 10000)}{numeric('generator_litres_per_kwh', 'Fuel use (litres/kWh)', .01, 2, .01)}</div>
            <p className="muted">Battery capacity: {number(local.battery_capacity_kwh)} kWh · battery power: {number(local.battery_power_kw)} kW · indoor limits: {local.comfort_min_c}–{local.comfort_max_c}°C. Edit your inventory in Day Plan or Presets before starting a new rehearsal.</p>
          </Card>
        </div>
        <Card title="3. Add events to test (optional)" subtitle="Choose the events, then press Run. Nothing changes in the background." className="spaced">
          <div className="grid two-cols">
            <div><Toggle label="Simulate generator failure" checked={failure} onChange={change(setFailure)}/>
              {failure && <NumberField label="Failure begins at hour" min={0} max={23} value={failureHour} onChange={change(setFailureHour)} help="The generator stays failed after this hour. Refilling does not repair it."/>}</div>
            <div><Toggle label="Record a human refill report" checked={refill} onChange={change(setRefill)}/>
              {refill && <div className="controls-grid two"><NumberField label="Refill report at hour" min={0} max={23} value={refillHour} onChange={change(setRefillHour)}/>
                <NumberField label="Fill tank up to (%)" min={0} max={100} value={refillTo} onChange={change(setRefillTo)}/></div>}</div>
          </div>
          <div className="button-row spaced"><button type="submit" className="button primary"><Icon name="outage" size={17}/>Run outage rehearsal</button>
            <button type="button" className="button" onClick={restore}>Restore day-plan values</button></div>
          <p className="muted small-text">The backend replays the full day, including charging before the cut. Rehearsals never approve a day, save battery carry or send equipment commands. Fuel warns at 40%, urgently below 30%.</p>
        </Card>
      </fieldset>
    </form>
    {result ? <>
      {changed && <div className="pending-banner inline" role="status">You changed the test inputs. Run the rehearsal again; results below still describe the previous run.</div>}
      <div className="section-heading"><div><p className="eyebrow">LAST COMPLETED REHEARSAL · {result.date}</p><h2>{result.valid ? 'Both tested cases pass.' : 'Review the limits that failed.'}</h2></div>
        <Badge tone={result.valid ? 'green' : 'danger'}>{result.valid ? 'EXPECTED + ADVERSE PASS' : 'CHECKS FAILED'}</Badge></div>
      <div className="stats-grid"><Stat label="Starting battery" value={number(result.summary.battery_soc_start_kwh)} unit="kWh" detail={result.battery_carry.source} icon="battery"/>
        <Stat label="Unserved critical energy" value={number(result.summary.critical_unserved_kwh, 2)} unit="kWh" detail="Expected case · zero means no expected shortfall" icon="outage" accent/>
        <Stat label="Fuel remaining at end of day" value={number(result.summary.generator_fuel_end_pct, 1)} unit="%" detail={`${number(result.summary.generator_fuel_used_litres, 1)} litres used`} icon="bolt"/>
        <Stat label="Generator energy delivered" value={number(result.display.generator_total_kwh, 1)} unit="kWh" detail="Critical demand and HVAC combined" icon="trends"/></div>
      <SafetySummary summary={result.summary}/>
      <div className="scenario-facts"><span>Generator first starts <b>{result.rehearsal.generator_started_at_hour == null ? 'Did not run' : hourLabel(result.rehearsal.generator_started_at_hour)}</b></span>
        <span>First critical shortfall <b>{result.rehearsal.first_critical_shortfall_hour == null ? 'None in expected case' : hourLabel(result.rehearsal.first_critical_shortfall_hour)}</b></span>
        <span>Weather used <b>{weatherSource(result.forecast)}</b></span></div>
      <Card title="Power-cut timeline" subtitle={`${hourLabel(result.settings.outage_start)}–${hourLabel(result.settings.outage_end)} · these rows show the last completed expected case`}>
        <div className="table-wrap"><table><thead><tr><th>Hour</th><th>Battery start → end (kWh)</th><th>Solar to hospital (kWh)</th><th>Generator (kWh)</th><th>Fuel left (%)</th><th>Paused energy (kWh)</th><th>Critical shortfall (kWh)</th><th>Indoor (°C)</th><th>Status</th></tr></thead>
          <tbody>{result.hours.filter(row => !row.grid_available).map(row => <tr key={row.hour} className="outage-row"><th scope="row">{hourLabel(row.hour)}</th>
            <td>{number(row.battery_soc_start_kwh, 1)} → {number(row.battery_soc_end_kwh, 1)}</td><td>{number(row.solar_to_load_kwh, 1)}</td>
            <td>{number(row.generator_total_kwh, 1)}</td><td>{number(row.generator_fuel_end_pct, 1)}</td><td>{number(row.paused_noncritical_kwh, 1)}</td>
            <td className={row.critical_status === 'at_risk' ? 'text-danger' : ''}>{number(row.critical_unserved_kwh, 2)}</td><td>{number(row.temperature_c, 1)}</td>
            <td><span className="table-status">{row.generator_running ? 'Generator running' : 'Solar / battery backup'}</span><span className={row.critical_status === 'protected' ? 'text-green table-status' : 'text-danger table-status'}>{row.critical_status.replaceAll('_', ' ')}</span><span className={row.comfort_status === 'within_limits' ? 'table-status' : 'text-danger table-status'}>{row.comfort_status.replaceAll('_', ' ')}</span></td>
          </tr>)}</tbody></table></div>
      </Card>
      <div className="grid two-cols spaced"><Card title="Expected-case checks"><Checks checks={result.checks}/><Warnings warnings={result.warnings}/></Card>
        <Card title="Higher-demand / lower-solar checks" subtitle={result.risk_case.label}><SafetySummary summary={result.risk_case.summary}/><Checks checks={result.risk_case.checks} compact/><Warnings warnings={result.risk_case.warnings}/></Card></div>
      <Card title="Battery through the full rehearsal day" subtitle="Includes pre-outage charging and recovery after grid return." className="spaced">
        <LineChart labels={result.hours.map(row => hourLabel(row.hour))} label="Rehearsal battery energy and fixed generator threshold"
          series={[{ name: 'Battery energy', color: 'var(--accent)', values: result.hours.map(row => row.battery_soc_end_kwh) },
                   { name: 'Generator threshold', color: 'var(--gold)', dashed: true, values: result.hours.map(() => result.display.generator_threshold_kwh) }]}/>
      </Card>
    </> : <div className="pre-rehearsal"><Icon name="outage" size={35}/><div><h2>Your test results will appear here.</h2><p>Start with the default window and backup, then rerun with a generator failure or lower fuel to understand the limits.</p></div></div>}
  </>;
}
