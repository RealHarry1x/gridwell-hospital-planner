import React, { useEffect, useState } from 'react';
import { api, longDate } from './api';
import { Badge, Icon } from './components';
import { Workspace } from './context';
import { Overview, Comparison, Trends, Breakdown, Suggestions } from './pages/Insights';
import { DayPlan } from './pages/DayPlan';
import { Outage, Presets, Assistant } from './pages/Tools';

const nav = [
  ['overview', 'Overview'], ['plan', 'Day Plan'], ['compare', 'Comparison'],
  ['trends', 'Trends'], ['outage', 'Outage Readiness'], ['breakdown', 'Energy Breakdown'],
  ['suggestions', 'Suggestions'], ['assistant', 'AI Guide'], ['presets', 'Presets'],
];
const validPage = () => nav.some(n => n[0] === location.hash.slice(1)) ? location.hash.slice(1) : 'overview';

export default function App() {
  const [page, setPage] = useState(validPage);
  const [config, setConfig] = useState(null);
  const [settings, setSettings] = useState(null);
  const [date, setDate] = useState('');
  const [dayType, setDayType] = useState('normal');
  const [forecast, setForecast] = useState(null);
  const [plan, setPlan] = useState(null);
  const [presets, setPresets] = useState([]);
  const [history, setHistory] = useState([]);
  const [overrides, setOverrides] = useState([]);
  const [hourlyEdits, setHourlyEdits] = useState([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [reviewOpen, setReviewOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [resetResult, setResetResult] = useState(null);
  const [guideQuestion, setGuideQuestion] = useState('');
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('gridwell-theme') || 'light'; } catch { return 'light'; } });

  useEffect(() => { document.body.dataset.theme = theme; try { localStorage.setItem('gridwell-theme', theme); } catch {} }, [theme]);
  useEffect(() => { if (toast) { const timer = setTimeout(() => setToast(''), 6000); return () => clearTimeout(timer); } }, [toast]);
  useEffect(() => { const listener = () => setPage(validPage()); window.addEventListener('hashchange', listener); return () => window.removeEventListener('hashchange', listener); }, []);

  useEffect(() => {
    let active = true;
    Promise.all([api('/config'), api('/presets'), api('/trends?days=7')]).then(([cfg, modes, trends]) => {
      if (!active) return;
      setConfig(cfg); setSettings(cfg.defaults); setDate(cfg.tomorrow); setPresets(modes); setHistory(trends.days);
    }).catch(e => active && setError(e.message));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!date || !config) return;
    let active = true;
    setLoading(true); setError(''); setPlan(null); setDirty(false); setOverrides([]); setHourlyEdits([]);
    const params = new URLSearchParams({ date, day_type: dayType, solar_capacity_kwp: settings.solar_capacity_kwp, outage_start: settings.outage_start, outage_end: settings.outage_end });
    Promise.all([api(`/plans?date=${date}`), api(`/config?date=${date}`)]).then(async ([saved, cfg]) => {
      if (!active) return;
      setConfig(cfg);
      if (saved && saved.day_type === dayType) {
        setPlan(saved); setForecast(saved.forecast); setSettings(saved.settings);
        setOverrides(saved.input.forecast_overrides); setHourlyEdits(saved.input.hourly_edits);
        setDirty(saved.status === 'stale');
      } else {
        const fc = await api(`/forecast?${params}`);
        if (active) setForecast(fc);
      }
    }).catch(e => active && setError(e.message)).finally(() => active && setLoading(false));
    return () => { active = false; };
    // Reload date/scenario context only. Settings apply via Verify / Recalculate.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, dayType]);

  function navigate(next) {
    setPage(next); location.hash = next; setMobileOpen(false);
    window.scrollTo({ top: 0, behavior: 'instant' });
    document.getElementById('main-content')?.focus({ preventScroll: true });
  }
  async function act(label, work) {
    setBusy(label); setError('');
    try { return await work(); } catch (e) { setError(e.message); setToast(e.message); return null; } finally { setBusy(''); }
  }
  function updateSetting(key, value) { setSettings(s => ({ ...s, [key]: value })); setDirty(true); }
  function requestBody(patch = {}) {
    return { date, day_type: dayType, settings, forecast_overrides: overrides, hourly_edits: hourlyEdits, ...patch };
  }
  async function calculate(patch = {}, newDraft = false) {
    const revise = plan && !newDraft;
    return act(revise ? 'Recalculating plan…' : 'Generating a new day plan…', async () => {
      const body = requestBody(patch);
      const next = await api(revise ? `/plans/${plan.id}/recalculate` : '/plans/generate', { method: 'POST', body });
      setPlan(next); setForecast(next.forecast); setSettings(next.settings); setDirty(false);
      setToast(newDraft ? 'New draft created with current weather inputs (one-hour cache applies). The previous plan record and approval history are kept.'
        : `Revision ${next.revision} calculated. ${next.calculation?.same_inputs ? 'Same inputs: matching figures are expected.' : next.valid ? 'Your results and checks are updated.' : 'Review failed checks; approval is blocked.'}`);
      return next;
    });
  }
  async function approve() {
    return act('Approving simulation…', async () => {
      const next = await api(`/plans/${plan.id}/approve`, { method: 'POST', body: { revision: plan.revision } });
      setPlan(next); setToast('Approved for simulation. Battery history updated; no equipment commands sent.');
      const [trends, cfg] = await Promise.all([api('/trends?days=7'), api(`/config?date=${date}`)]);
      setHistory(trends.days); setConfig(cfg);
    });
  }
  function editForecast(hour, field, value) {
    setOverrides(prev => [...prev.filter(o => !(o.hour === hour && o.field === field)), ...(value === '' ? [] : [{ hour, field, value: Number(value) }])]);
    setDirty(true);
  }
  function editHour(hour, field, value) {
    setHourlyEdits(prev => {
      const current = { ...(prev.find(e => e.hour === hour) || { hour }) };
      if (value === '') delete current[field]; else current[field] = Number(value);
      return [...prev.filter(e => e.hour !== hour), ...(Object.keys(current).length > 1 ? [current] : [])];
    });
    setDirty(true);
  }
  async function verify() {
    return act('Checking forecast adjustments…', async () => {
      const fc = await api('/forecast/verify', { method: 'POST', body: { ...requestBody(), plan_id: plan?.id || null } });
      setForecast(fc); setToast(fc.warnings.length ? `${fc.warnings.length} forecast range warning(s). Original values are preserved.` : 'Forecast verified. Original ranges are preserved.');
    });
  }
  function usePreset(preset) {
    if (preset.built_in) {
      setSettings(current => ({ ...current, ...preset.settings_patch, objective: preset.settings.objective }));
      setToast(`${preset.name} goal selected. Your equipment, comfort limits and hourly edits are kept. Recalculate to see the trade-off.`);
    } else {
      setSettings({ ...preset.settings }); setHourlyEdits([]);
      setToast(`${preset.name} resource settings loaded into the draft. Hourly overrides cleared; recalculate to see the result.`);
    }
    setDirty(true);
  }
  function changeDayType(next) { if (next !== dayType) { setForecast(null); setDayType(next); setReviewOpen(false); } }
  function askGuide(question) { setGuideQuestion(question); navigate('assistant'); }
  async function applyScenarioSettings() {
    return act('Preparing scenario settings…', async () => {
      const fc = await api('/forecast/verify', { method: 'POST', body: { ...requestBody(), plan_id: plan?.id || null } });
      setForecast(fc); setSettings(current => ({ ...current, ...fc.planning_guidance.settings_patch }));
      setHourlyEdits([]); setDirty(true);
      setToast('Suggested reserve and work windows applied to your draft. Hourly overrides cleared. Recalculate to test the result.');
    });
  }
  async function resetWorkspace(initialPct) {
    return act('Resetting saved demo plans…', async () => {
      const outcome = await api('/demo/reset', { method: 'POST', body: { initial_soc_pct: initialPct } });
      const [cfg, trends, modes] = await Promise.all([api('/config'), api('/trends?days=7'), api('/presets')]);
      const fc = await api(`/forecast?date=${cfg.tomorrow}&day_type=normal`);
      setPlan(null); setSettings(cfg.defaults); setConfig(cfg); setForecast(fc); setDate(cfg.tomorrow); setDayType('normal');
      setHistory(trends.days); setPresets(modes); setOverrides([]); setHourlyEdits([]); setDirty(false); setReviewOpen(false);
      setResetResult(outcome); setToast('Demo reset complete. Saved plans and edits were cleared; custom presets were kept.');
      return outcome;
    });
  }
  function reviewForecast() { setReviewOpen(true); navigate('plan'); }

  if (!config || !settings) return <div className="startup"><div className="brand-mark"><Icon name="trends" size={28}/></div><h1>Gridwell</h1>{error ? <><h2>Start your Python backend to connect.</h2><p role="alert">{error}</p><p>Open the project’s README.md for setup instructions.</p><button className="button primary" onClick={() => location.reload()}>Try again</button></> : <><p>Preparing your hospital energy workspace…</p><span className="spinner"/></>}</div>;
  const value = { config, settings, updateSetting, setSettings, date, dayType, forecast, plan, setPlan, presets, setPresets, history, setHistory, overrides, hourlyEdits, setHourlyEdits, dirty, setDirty, busy: busy || (loading ? 'Loading selected day…' : ''), act, navigate, calculate, approve, requestBody, editForecast, editHour, verify, reviewOpen, setReviewOpen, reviewForecast, usePreset, notify: setToast, reportError: setError, setConfig, setForecast, setOverrides, resetWorkspace, resetResult, setResetResult, changeDayType, applyScenarioSettings, askGuide, guideQuestion };
  const Page = { overview: Overview, plan: DayPlan, compare: Comparison, trends: Trends, outage: Outage, breakdown: Breakdown, suggestions: Suggestions, assistant: Assistant, presets: Presets }[page];
  return <Workspace.Provider value={value}><a className="skip-link" href="#main-content" onClick={e => { e.preventDefault(); document.getElementById('main-content')?.focus(); }}>Skip to content</a><div className="app-shell">
    {mobileOpen && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setMobileOpen(false)}/>}
    <aside className={`sidebar ${mobileOpen ? 'is-open' : ''}`} aria-label="Main navigation"><a className="brand" href="#overview" onClick={e => { e.preventDefault(); navigate('overview'); }}><span className="brand-mark"><Icon name="trends" size={24}/></span><span>Gridwell<small>HOSPITAL ENERGY PLANNER</small></span></a><p className="nav-label">WORKSPACE</p><nav>{nav.map(([key, label], index) => <React.Fragment key={key}>{index === 6 && <p className="nav-label nav-divider">INTELLIGENCE</p>}<button className={`nav-item ${page === key ? 'active' : ''}`} aria-current={page === key ? 'page' : undefined} onClick={() => navigate(key)}><Icon name={key}/><span>{label}</span>{page === key && <i/>}</button></React.Fragment>)}</nav><div className="sidebar-bottom"><div className="facility-card"><div className="facility-icon">H<span>+</span></div><div><strong>Cedar General Hospital</strong><span>Fictional · India</span></div><div className="facility-status"><i/>Simulation workspace</div></div><button className="theme-button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}><Icon name={theme === 'dark' ? 'solar' : 'moon'}/>{theme === 'dark' ? 'Light appearance' : 'Dark appearance'}</button><div className="operator"><span className="operator-avatar">OP</span><span><b>Demo operator</b><small>Local workspace · no login</small></span></div></div></aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMobileOpen(!mobileOpen)}><Icon name="menu"/></button><span>Workspace</span><Icon name="chevron" size={13}/><strong>{nav.find(n => n[0] === page)?.[1]}</strong></div><div className="topbar-right"><span className="topbar-date">{longDate(config.today)}</span><Badge tone="green"><i className="status-dot"/>Python connected</Badge><Badge>SIMULATED HOSPITAL</Badge></div></header>
      <main id="main-content" tabIndex={-1}><div className="context-bar"><div className="planning-date"><span className="context-label">PLANNING FOR</span><label className="sr-only" htmlFor="planning-date">Planning date</label><input id="planning-date" type="date" value={date} onChange={e => e.target.value && setDate(e.target.value)} disabled={!!busy}/></div><div className="scenario-picker" role="group" aria-label="Day type">{config.day_types.map(t => <button key={t.id} className={t.id === dayType ? 'selected' : ''} onClick={() => changeDayType(t.id)} disabled={!!busy}>{t.name}</button>)}</div><label className="goal-select"><span className="context-label">GOAL</span><select aria-label="Planning goal" value={settings.objective} onChange={e => updateSetting('objective', e.target.value)} disabled={!!busy}><option value="balanced">Balanced</option><option value="cost">Lowest cost</option><option value="emissions">Lowest emissions</option><option value="custom">Custom weights</option></select></label></div>
      {error && <div className="error-banner" role="alert"><Icon name="info"/><span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><Icon name="close" size={16}/></button></div>}
      {(busy || loading) && <div className="busy-banner" role="status"><span className="spinner small"/>{busy || 'Loading selected day…'}</div>}
      {dirty && plan && <div className="pending-banner"><span><b>Draft changes pending.</b> Figures below still show calculated revision {plan.revision}.</span><button className="text-button" onClick={() => calculate()} disabled={!!busy || loading}>Recalculate <Icon name="arrow" size={15}/></button></div>}
      <div className="page-body" key={page}>{forecast ? <Page/> : <div className="loading-block">{loading ? 'Loading forecast…' : 'Forecast unavailable. Check the message above.'}</div>}</div>
      <footer className="workspace-footer"><span><i className="status-dot"/>Demo environment · no equipment connection</span><span>Forecast. Review. Simulate.</span></footer></main></div></div>{toast && <div className="toast" role="status"><Icon name="info" size={18}/><span>{toast}</span><button aria-label="Dismiss notification" onClick={() => setToast('')}><Icon name="close" size={15}/></button></div>}</Workspace.Provider>;
}
