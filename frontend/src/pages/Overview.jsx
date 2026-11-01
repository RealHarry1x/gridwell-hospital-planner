import React, { useState } from 'react';
import { api, hourLabel, money, number } from '../api';
import { Badge, Card, Icon, LineChart, Modal, NumberField, PageTitle, SafetySummary, Stat } from '../components';
import { WeatherStrip, weatherSource } from '../PlanningHelp';
import { useWorkspace } from '../context';

export function Overview() {
  const w = useWorkspace();
  const { forecast: f, plan, config, settings, busy } = w;
  const carry = plan?.battery_carry || config.battery_carry;
  const [initialPct, setInitialPct] = useState(config.initial_soc_pct);
  const [resetOpen, setResetOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyData, setHistoryData] = useState(null);
  const [historyError, setHistoryError] = useState('');

  async function showHistory() {
    setHistoryOpen(true); setHistoryData(null); setHistoryError('');
    const params = new URLSearchParams({ date: w.date, day_type: w.dayType });
    if (plan) params.set('plan_id', plan.id);
    try { setHistoryData(await api(`/demand-context?${params}`)); }
    catch (error) { setHistoryError(error.message); }
  }
  async function confirmReset() {
    const outcome = await w.resetWorkspace(initialPct);
    if (outcome) setResetOpen(false);
  }
  return <>
    <PageTitle eyebrow="START HERE · TOMORROW'S ENERGY" title={<>Plan tomorrow.<br/><em>Protect what matters.</em></>}
      description="Review the demand and weather, choose a day scenario, then generate an hourly plan. Hospital energy figures are simulated."
      action={<button className="button primary" disabled={!!busy} onClick={() => w.navigate('plan')}>Choose conditions & plan <Icon name="arrow" size={17}/></button>}/>

    {w.resetResult && <div className="result-confirmation" role="status">
      <Icon name="check"/><div><h2>Demo reset complete</h2>
        <p>{w.resetResult.deleted_plans} saved plans cleared · {w.resetResult.deleted_history_records} previous records replaced · {w.resetResult.history_records_created} example days rebuilt · {w.resetResult.kept_custom_presets} custom presets kept.</p>
        <p>The first history day ({w.resetResult.first_history_date}) now starts with {number(w.resetResult.first_history_battery_kwh)} kWh. The same date and assumptions produce the same forecast; reset does not randomize it.</p>
      </div><button className="icon-button" aria-label="Dismiss reset result" onClick={() => w.setResetResult(null)}><Icon name="close"/></button>
    </div>}

    <div className="stats-grid">
      <Stat label="Expected hospital demand" value={number(f.daily.demand_kwh.expected)} unit="kWh" detail="Estimated electricity needed across the selected day · simulated" icon="bolt" accent
        action={<button className="text-button" onClick={showHistory}><Icon name="info" size={14}/>Last 7 days & estimate basis</button>}/>
      <Stat label="Solar potential for this day" value={number(f.daily.solar_kwh.expected)} unit="kWh" detail={`Energy a ${number(f.daily.solar_capacity_kwp ?? settings.solar_capacity_kwp)} kWp array could generate · weather basis below`} icon="solar"/>
      <Stat label="Expected occupancy" value={number(f.daily.occupancy_pct.expected)} unit="%" detail="Simulated occupancy forecast · not patient records" icon="people"/>
      <Stat label="Battery carried forward" value={number(carry.energy_kwh)} unit="kWh" detail={carry.from_date ? `Last recorded ending level · ${carry.from_date}` : carry.note} icon="battery"/>
    </div>

    <div className="grid overview-grid">
      <Card title="Demand and solar, hour by hour" subtitle="Expected energy per hour · selected planning day" action={<Badge>24 HOURS</Badge>} className="forecast-card">
        <LineChart labels={f.hours.map(row => hourLabel(row.hour))} label="Expected hourly hospital demand and potential solar generation"
          series={[{ name: 'Hospital demand', color: 'var(--accent)', values: f.hours.map(row => row.demand_kwh.expected) },
                   { name: 'Potential solar generation', color: 'var(--green)', values: f.hours.map(row => row.solar_kwh.expected) }]}/>
        <div className="card-bottom"><span><Icon name="info" size={14}/>{weatherSource(f)}</span>
          <button className="text-button" onClick={w.reviewForecast}>Review forecast assumptions <Icon name="arrow" size={15}/></button></div>
      </Card>
      <Card title="Useful planning signals" subtitle="Prices and grid carbon are demo assumptions" className="signals-card">
        <div className="signal"><span className="signal-icon"><Icon name="solar"/></span><div><span>CHEAPER GRID HOURS</span><strong>{f.daily.cheapest_hours.map(hourLabel).join(' · ')}</strong><small>₹{number(f.daily.price_min_inr_per_kwh, 2)}–{number(f.daily.price_max_inr_per_kwh, 2)} per kWh</small></div></div>
        <div className="signal"><span className="signal-icon green"><Icon name="leaf"/></span><div><span>CLEANER GRID HOURS</span><strong>{f.daily.cleanest_hours.map(hourLabel).join(' · ')}</strong><small>{number(f.daily.carbon_min_kg_per_kwh, 2)}–{number(f.daily.carbon_max_kg_per_kwh, 2)} kg CO2e/kWh</small></div></div>
        <div className="signal"><span className="signal-icon"><Icon name="outage"/></span><div><span>BATTERY BACKUP</span><strong>{settings.reserve_pct}% normal reserve</strong><small>During an outage the generator-start threshold is fixed at 10%.</small></div></div>
      </Card>
    </div>
    <WeatherStrip forecast={f}/>

    {plan && <><div className="section-heading"><h2>Your calculated plan</h2><Badge tone={plan.valid ? 'green' : 'danger'}>Revision {plan.revision} · {plan.status}</Badge></div>
      <div className="stats-grid"><Stat label="Estimated daily cost" value={money(plan.summary.cost_inr)} detail={`${money(plan.comparison.baseline.cost_inr)} usual routine`} icon="compare"/>
        <Stat label="Estimated emissions" value={number(plan.summary.emissions_kg_co2e)} unit="kg CO2e" detail="Simulated grid and generator emissions" icon="leaf"/>
        <Stat label="Peak grid demand" value={number(plan.summary.peak_grid_kw)} unit="kW" detail="Includes battery grid charging" icon="trends"/>
        <Stat label="Battery at midnight" value={number(plan.summary.battery_soc_end_kwh)} unit="kWh" detail={`Minimum ${number(plan.summary.battery_soc_min_kwh)} kWh`} icon="battery"/></div>
      <SafetySummary summary={plan.summary}/></>}

    <details className="assumptions"><summary><Icon name="info" size={16}/>Data sources, assumptions & resetting the demo</summary>
      <div className="assumption-content"><ul>{config.assumptions.map(item => <li key={item}>{item}</li>)}</ul>
        <div className="reset-row"><NumberField label="First history day's opening battery (%)" value={initialPct} onChange={setInitialPct} min={10} max={100}
          help="Reset uses this on the earliest example day; later days carry recorded battery energy."/>
          <button className="button danger-button" disabled={!!busy} onClick={() => setResetOpen(true)}><Icon name="refresh" size={16}/>Reset demo</button></div>
        <p className="muted">Reset clears saved plans, approvals and edits, restores default controls and rebuilds repeatable example history. Your custom presets are kept.</p>
      </div>
    </details>

    {historyOpen && <Modal title="Last 7 recorded days & demand estimate" onClose={() => setHistoryOpen(false)}>
      {historyError ? <p role="alert" className="text-danger">{historyError}</p> : !historyData ? <p role="status">Loading recorded energy…</p> : <>
        <Badge>SIMULATED HISTORY · BEFORE {w.date}</Badge>
        <div className="table-wrap spaced"><table><thead><tr><th>Date</th><th>Recorded energy</th></tr></thead><tbody>
          {historyData.days.map(row => <tr key={row.date}><th scope="row">{row.date}</th><td>{number(row.energy_kwh)} kWh</td></tr>)}
        </tbody></table></div>
        {!historyData.days.length && <p>No earlier recorded days are available.</p>}
        <div className="scenario-facts"><span>Recorded-day average <b>{historyData.average_kwh == null ? 'Unavailable' : `${number(historyData.average_kwh)} kWh`}</b></span>
          <span>Selected forecast <b>{number(historyData.forecast_expected_kwh)} kWh</b></span></div>
        <div className="soft-note"><b>How demand is calculated</b><p>{historyData.method}</p><p>{historyData.source}</p></div>
      </>}
    </Modal>}
    {resetOpen && <Modal title="Reset this demo workspace?" onClose={() => { if (!busy) setResetOpen(false); }}>
      <p>This deletes saved plans and simulation approvals, clears draft edits and restores default planning controls. Eight example days will be rebuilt with a {initialPct}% opening battery assumption on the first history day.</p>
      <p className="soft-note">Your custom presets and local API-key configuration are kept. Resetting does not randomize the same day's demand or overwrite weather in an existing plan—the existing plans are deleted.</p>
      <div className="button-row spaced"><button className="button" disabled={!!busy} onClick={() => setResetOpen(false)}>Keep workspace</button>
        <button className="button danger-button" disabled={!!busy} onClick={confirmReset}>{busy ? 'Resetting…' : 'Confirm reset'}</button></div>
    </Modal>}
  </>;
}
