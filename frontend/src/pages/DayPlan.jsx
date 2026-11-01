import React, { useState } from 'react';
import { hourLabel, money, number, signed } from '../api';
import { Badge, Card, Checks, Field, Icon, LineChart, NumberField, PageTitle, SafetySummary, Stat, Toggle, Warnings } from '../components';
import { useWorkspace } from '../context';

export { PlanningControls } from '../ResourceControls';
import { PlanningControls } from '../ResourceControls';
import { GoalChoices, ScenarioChooser, weatherSource } from '../PlanningHelp';

export function ForecastReview() {
  const w = useWorkspace();
  const fields = [['demand_kwh', 'Demand', 'kWh'], ['occupancy_pct', 'Occupancy', '%'], ['solar_kwh', 'Solar', 'kWh']];
  return <Card title="A forecast you can question." subtitle="Optional review · original bands remain visible after every adjustment" action={<Badge>NOT REQUIRED</Badge>} className="forecast-review"><p className="muted">Enter an adjusted expected value beside the original. A value outside the original band produces a warning. Generate uses the adjustments even if you skip verification.</p><div className="table-wrap forecast-table"><table><caption className="sr-only">Original low / expected / high values and editable adjustments for 24 hours</caption><thead><tr><th rowSpan="2" scope="col">Hour</th>{fields.map(([key, name, unit]) => <th colSpan="2" scope="colgroup" key={key}>{name} ({unit})</th>)}</tr><tr>{fields.map(([key]) => <React.Fragment key={key}><th scope="col">Low / expected / high</th><th scope="col">Adjusted</th></React.Fragment>)}</tr></thead><tbody>{w.forecast.hours.map(row => <tr key={row.hour}><th scope="row">{hourLabel(row.hour)}</th>{fields.map(([key, label]) => { const adjustment = w.overrides.find(o => o.hour === row.hour && o.field === key); return <React.Fragment key={key}><td className="forecast-band">{number(row[key].low, 1)} / <b>{number(row[key].expected, 1)}</b> / {number(row[key].high, 1)}</td><td><input className="table-input" type="number" step="0.1" min="0" max={key === 'occupancy_pct' ? 100 : undefined} value={adjustment?.value ?? ''} placeholder="Original" aria-label={`Adjusted ${label.toLowerCase()} at ${hourLabel(row.hour)}`} onChange={e => w.editForecast(row.hour, key, e.target.value)}/></td></React.Fragment>; })}</tr>)}</tbody></table></div><div className="button-row"><button className="button" disabled={!!w.busy} onClick={w.verify}>Verify adjustments<Icon name="check" size={16}/></button><button className="text-button" disabled={!!w.busy || !w.overrides.length} onClick={() => { w.setOverrides([]); w.setDirty(true); }}>Clear adjustments</button><span className="muted small-text">{w.overrides.length} adjusted values · original forecast preserved</span></div><Warnings warnings={w.forecast.warnings.map(message => ({ message, severity: 'warning' }))} title="Forecast range warnings"/></Card>;
}

export function HourlySchedule() {
  const w = useWorkspace(), plan = w.plan;
  const [tab, setTab] = useState('schedule');
  const editFields = [['hvac_kwh', 'HVAC', r => r.flexible_loads_kwh.hvac], ['laundry_kwh', 'Laundry', r => r.flexible_loads_kwh.laundry], ['water_heating_kwh', 'Water heat', r => r.flexible_loads_kwh.water_heating], ['grid_charge_kwh', 'Grid charge', r => r.grid_to_battery_kwh], ['battery_discharge_kwh', 'Battery out', r => r.battery_discharge_to_load_kwh]];
  const flowFields = [['solar_available_kwh', 'PV available'], ['solar_to_load_kwh', 'PV → load'], ['solar_to_battery_kwh', 'PV → battery'], ['grid_to_load_kwh', 'Grid → load'], ['grid_to_battery_kwh', 'Grid → battery'], ['battery_discharge_to_load_kwh', 'Battery → load'], ['solar_curtailed_kwh', 'PV curtailed'], ['generator_to_critical_kwh', 'Gen → critical'], ['generator_to_hvac_kwh', 'Gen → HVAC'], ['unserved_kwh', 'Unserved']];
  return <Card title="The 24-hour schedule" subtitle="One hour per row · flows are kWh; peak and equipment limits are kW" action={<a className="button small" href={`/api/plans/${plan.id}/export.csv`} download><Icon name="download" size={15}/>CSV</a>} className="spaced"><div className="schedule-toolbar"><div className="metric-tabs" role="group" aria-label="Schedule view">{[['schedule', 'Schedule'], ['edit', 'Edit hourly'], ['flows', 'All energy flows']].map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}</div>{w.hourlyEdits.length > 0 && <button className="text-button" onClick={() => { w.setHourlyEdits([]); w.setDirty(true); }}>Clear hourly edits ({w.hourlyEdits.length})</button>}</div>{tab === 'edit' && <div className="soft-note">Edit a single hour or several. Unedited laundry/heating hours rebalance to preserve daily energy; HVAC edits preserve the daily cooling budget. Battery requests that exceed a limit are flagged and block approval. Critical demand cannot be edited here.</div>}<div className="table-wrap schedule-table"><table><caption className="sr-only">Detailed {tab} for the selected simulated day</caption><thead><tr><th scope="col">Hour</th>{tab === 'edit' ? editFields.map(([key, title]) => <th scope="col" key={key}>{title} (kWh)</th>) : tab === 'flows' ? flowFields.map(([key, title]) => <th scope="col" key={key}>{title} (kWh)</th>) : <><th scope="col">Demand (kWh)</th><th scope="col">Critical (kWh)</th><th scope="col">Solar direct (kWh)</th><th scope="col">Grid draw (kWh)</th><th scope="col">Battery end (kWh)</th><th scope="col">Zone (°C)</th><th scope="col">Fuel (%)</th><th scope="col">Cost (₹)</th></>}<th scope="col">Critical / comfort</th></tr></thead><tbody>{plan.hours.map(row => { const edit = w.hourlyEdits.find(e => e.hour === row.hour); return <tr key={row.hour} className={`${!row.grid_available ? 'outage-row' : ''} ${edit ? 'edited-row' : ''}`}><th scope="row">{hourLabel(row.hour)}{!row.grid_available && <small>OUTAGE</small>}{edit && <small>EDITED</small>}</th>{tab === 'edit' ? editFields.map(([key, title, fallback]) => <td key={key}><input type="number" min="0" step="0.1" className={`table-input ${edit?.[key] != null ? 'has-edit' : ''}`} aria-label={`${title} at ${hourLabel(row.hour)}`} value={edit?.[key] ?? Number(fallback(row).toFixed(2))} onChange={e => w.editHour(row.hour, key, e.target.value)} disabled={!!w.busy}/></td>) : tab === 'flows' ? flowFields.map(([key]) => <td key={key}>{number(row[key], 1)}</td>) : <><td>{number(row.demand_kwh, 1)}</td><td>{number(row.critical_demand_kwh, 1)}</td><td>{number(row.solar_to_load_kwh, 1)}</td><td>{number(row.grid_draw_kwh, 1)}</td><td>{number(row.battery_soc_end_kwh, 1)}</td><td>{number(row.temperature_c, 1)}</td><td>{number(row.generator_fuel_end_pct, 1)}</td><td>{number(row.cost_inr)}</td></>}<td><span className={`table-status ${row.critical_status === 'protected' ? 'text-green' : 'text-danger'}`}>{row.critical_status === 'protected' ? 'Protected' : 'At risk'}</span><span className={`table-status ${row.comfort_status === 'within_limits' ? 'text-green' : 'text-danger'}`}>{row.comfort_status === 'within_limits' ? 'In bounds' : 'Violation'}</span></td></tr>; })}</tbody></table></div><p className="muted small-text">The table shows the last calculated schedule. Edits take effect when you choose Recalculate. The backend records unmet demand explicitly and checks every hourly balance.</p></Card>;
}

export function DayPlan() {
  const w = useWorkspace(), p = w.plan;
  return <>
    <PageTitle eyebrow="CHOOSE · CALCULATE · REVIEW" title="Build your day plan."
      description="Choose tomorrow's conditions, decide your priority and check your available resources. Calculate before approving a simulation."
      action={p && <Badge tone={p.valid ? 'green' : 'danger'}>REVISION {p.revision} · {p.status}</Badge>}/>
    <ScenarioChooser/>
    <Card title="2. Choose what the schedule should prioritize" subtitle="These goals rank hours differently; all keep the same hard safety rules." className="spaced">
      <GoalChoices/>
    </Card>
    <Card title="3. Review resources and working limits" subtitle="Change only what fits your equipment and operating assumptions." className="spaced">
      <PlanningControls/>
      <div className="plan-action-bar"><div><Badge tone="green">HARD RULES ALWAYS ON</Badge><small>Scenario choice and suggested settings never approve a plan or control equipment.</small></div>
        <div className="button-row"><button className="button primary" disabled={!!w.busy} onClick={() => w.calculate()}>
          <Icon name={p ? 'refresh' : 'suggestions'} size={17}/>{p ? 'Recalculate with these settings' : 'Generate recommendation'}
        </button>{p && <button className="button approve-button" disabled={!!w.busy || w.dirty || !p.valid || p.status === 'approved'} onClick={w.approve}>
          <Icon name="check" size={17}/>{p.status === 'approved' ? 'Simulation approved' : 'Approve simulation'}
        </button>}</div>
      </div>
      {p && <div className="soft-note"><b>Want a new weather basis?</b> Recalculate retains this plan's saved weather. A new draft uses the current weather cache, keeps your settings/edits and preserves the old plan record.
        <button type="button" className="text-button spaced" disabled={!!w.busy} onClick={() => w.calculate({}, true)}>New draft with current weather <Icon name="refresh" size={15}/></button>
      </div>}
      <button className="text-button" onClick={() => w.setReviewOpen(!w.reviewOpen)}>{w.reviewOpen ? 'Close forecast adjustments' : 'Optional: adjust the hourly forecast'}<Icon name="arrow" size={15}/></button>
      {p && !p.valid && <div className="note error-note"><Icon name="info"/><p>Approval is blocked. Review failed checks below. Expected and high-demand / low-solar cases must both pass.</p></div>}
    </Card>
    {w.reviewOpen && <ForecastReview/>}
    {p && <>
      <div className="calculation-result spaced" role="status"><Icon name="check"/><div><h2>Calculated revision {p.revision}</h2>
        <p>{p.calculation?.message || 'Saved calculation loaded. Change a setting and recalculate to create another revision.'}</p>
        <small>{p.calculation?.calculated_at && new Date(p.calculation.calculated_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} · {weatherSource(p.forecast)} · saved weather is retained when recalculating.</small>
      </div></div>
      <div className="section-heading"><h2>Your calculated result</h2><button className="text-button" onClick={() => w.navigate('compare')}>Compare the cost and energy flows <Icon name="arrow" size={15}/></button></div>
      <div className="stats-grid">
        <Stat label="Estimated daily cost" value={money(p.summary.cost_inr)} detail={p.changes ? `${signed(p.changes.cost_inr)} ₹ since previous revision` : 'Includes charging and generator fuel'} icon="compare" accent/>
        <Stat label="Estimated emissions" value={number(p.summary.emissions_kg_co2e)} unit="kg CO2e" detail={p.changes ? `${signed(p.changes.emissions_kg_co2e, 1)} kg since previous revision` : 'Simulated grid + generator emissions'} icon="leaf"/>
        <Stat label="Peak grid demand" value={number(p.summary.peak_grid_kw)} unit="kW" detail={p.changes ? `${signed(p.changes.peak_grid_kw, 1)} kW since previous revision` : 'Includes battery charging'} icon="trends"/>
        <Stat label="Closing battery" value={number(p.summary.battery_soc_end_kwh)} unit="kWh" detail={`Start ${number(p.summary.battery_soc_start_kwh)} · minimum ${number(p.summary.battery_soc_min_kwh)}`} icon="battery"/>
      </div><SafetySummary summary={p.summary}/>
      <Card title="Where each hour's energy comes from" subtitle="Hospital demand and delivered supply; battery charging is shown in the detailed flows.">
        <LineChart labels={p.hours.map(row => hourLabel(row.hour))} label="Hourly demand, direct grid, solar, battery and generator supply"
          series={[{ name: 'Demand', color: 'var(--ink)', dashed: true, values: p.hours.map(row => row.demand_kwh) },
                   { name: 'Grid direct', color: 'var(--accent)', values: p.hours.map(row => row.grid_to_load_kwh) },
                   { name: 'Solar direct', color: 'var(--green)', values: p.hours.map(row => row.solar_to_load_kwh) },
                   { name: 'Battery discharge', color: 'var(--gold)', values: p.hours.map(row => row.battery_discharge_to_load_kwh) },
                   { name: 'Generator', color: 'var(--slate)', values: p.hours.map(row => row.generator_total_kwh) }]}/>
      </Card>
      <div className="grid two-cols spaced"><Card title="Checks for the expected day" subtitle="Any failed hard check blocks approval"><Checks checks={p.checks}/><Warnings warnings={p.warnings}/></Card>
        <Card title="What if demand is higher and solar is lower?" subtitle={p.risk_case.label} action={<Badge tone={p.risk_case.valid ? 'green' : 'danger'}>{p.risk_case.valid ? 'CHECKS PASS' : 'CHECKS FAIL'}</Badge>}>
          <p className="muted">{p.risk_case.method}</p><SafetySummary summary={p.risk_case.summary}/>
          <div className="risk-facts"><span>Estimated cost <b>{money(p.risk_case.summary.cost_inr)}</b></span><span>Critical shortfall <b>{number(p.risk_case.summary.critical_unserved_kwh, 2)} kWh</b></span></div>
          <details className="settings-details"><summary>See adverse-case checks and warnings</summary><Checks checks={p.risk_case.checks} compact/><Warnings warnings={p.risk_case.warnings}/></details>
        </Card>
      </div>
      <HourlySchedule/>
      <Card title="Battery energy through the day" subtitle="Normal reserve and the fixed outage generator threshold are separate." className="spaced">
        <LineChart labels={p.hours.map(row => hourLabel(row.hour))} label="Battery stored energy, normal reserve and generator threshold"
          series={[{ name: 'Stored energy', color: 'var(--accent)', values: p.hours.map(row => row.battery_soc_end_kwh) },
                   { name: 'Normal reserve', color: 'var(--green)', dashed: true, values: p.hours.map(() => p.display.normal_reserve_kwh) },
                   { name: 'Generator threshold', color: 'var(--gold)', dashed: true, values: p.hours.map(() => p.display.generator_threshold_kwh) }]}/>
      </Card>
      <details className="assumptions"><summary><Icon name="info" size={16}/>Why this plan makes these decisions</summary><div className="assumption-content explanation-grid">
        {p.explanations.map(item => <div key={item.question}><h3>{item.question}</h3><p>{item.answer}</p></div>)}
      </div></details>
    </>}
  </>;
}
