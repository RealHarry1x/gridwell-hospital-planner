import React, { useEffect, useId, useRef } from 'react';
import { number } from './api';

const paths = {
  overview: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
  plan: <><rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4m8-4v4M4 11h16m-11 5 2 2 4-4"/></>,
  compare: <><path d="M5 20V10m7 10V4m7 16V8M2 20h20"/></>,
  trends: <><path d="M3 4v16h18M6 15l5-6 4 3 6-7"/></>,
  outage: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/></>,
  breakdown: <><path d="M12 3v9h9A9 9 0 0 0 12 3Z"/><path d="M8 4A9 9 0 1 0 20 16H8V4Z"/></>,
  suggestions: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/></>,
  assistant: <><path d="M5 17 3 21l6-2h10a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2Z"/><path d="M8 8h8m-8 5h5"/></>,
  presets: <><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/></>,
  solar: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></>,
  battery: <><rect x="3" y="6" width="17" height="12" rx="2"/><path d="M22 10v4M6 9v6m4-6v6m4-6v6"/></>,
  bolt: <path d="m13 2-9 12h7l-1 8 10-13h-7l0-7Z"/>,
  people: <><circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3m1-17a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 4v3"/></>,
  leaf: <><path d="M20 3C5 3 1 10 6 17s15 1 14-14Z"/><path d="M4 21 15 10"/></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6"/>,
  chevron: <path d="m9 5 7 7-7 7"/>,
  check: <path d="m5 12 4 4L19 6"/>,
  moon: <path d="M20 14a8 8 0 0 1-10-10 8.5 8.5 0 1 0 10 10Z"/>,
  info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/></>,
  download: <><path d="M12 3v12m-5-5 5 5 5-5M4 15v6h16v-6"/></>,
  close: <path d="m6 6 12 12M6 18 18 6"/>,
  menu: <path d="M4 6h16M4 12h16M4 18h16"/>,
  refresh: <><path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5"/></>,
  plus: <path d="M12 4v16M4 12h16"/>,
};

export function Icon({ name, size = 19, ...props }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.bolt}</svg>;
}
export function Badge({ children, tone = '', className = '' }) {
  return <span className={`badge ${tone} ${className}`}>{children}</span>;
}
export function PageTitle({ eyebrow, title, description, action }) {
  return <div className="page-heading reveal"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{action && <div className="heading-action">{action}</div>}</div>;
}
export function Card({ title, subtitle, action, children, className = '', ...props }) {
  return <section className={`card reveal ${className}`} {...props}>{title && <div className="card-head"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>}{children}</section>;
}
export function Stat({ label, value, unit, detail, icon, accent = false, action }) {
  return <article className={`stat reveal ${accent ? 'stat-accent' : ''}`}><div className="stat-top"><span>{label}</span><span className="stat-icon"><Icon name={icon}/></span></div><div className="stat-value">{value}<span>{unit}</span></div><p>{detail}</p>{action && <div className="stat-action">{action}</div>}</article>;
}
export function Modal({ title, children, onClose }) {
  const box = useRef(null), titleId = useId();
  useEffect(() => {
    const previous = document.activeElement, overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden'; box.current?.focus();
    return () => { document.body.style.overflow = overflow; previous?.focus?.(); };
  }, []);
  function keyboard(event) {
    if (event.key === 'Escape') { event.preventDefault(); onClose(); }
    if (event.key === 'Tab') {
      const controls = [...box.current.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]')];
      const first = controls.at(0), last = controls.at(-1);
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === box.current)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === box.current)) { event.preventDefault(); first.focus(); }
    }
  }
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="modal-panel" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} ref={box} onKeyDown={keyboard}>
      <div className="modal-heading"><h2 id={titleId}>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={onClose}><Icon name="close"/></button></div>
      {children}
    </section>
  </div>;
}
export function Checks({ checks, compact = false }) {
  return <div className={`checks ${compact ? 'compact' : ''}`}>{checks?.map(c => <div key={c.name} className={`check-row ${c.passed ? 'pass' : 'fail'}`}><span className="check-symbol">{c.passed ? '✓' : '!'}</span><div><strong>{c.name}</strong>{!compact && <small>{c.detail}</small>}</div><span>{c.passed ? 'Pass' : 'Failed'}</span></div>)}</div>;
}
export function Warnings({ warnings = [], title = 'Review notes' }) {
  if (!warnings.length) return <div className="note success"><Icon name="check"/>No warnings in this case.</div>;
  return <details className="warnings" open={warnings.some(w => w.severity === 'error')}><summary>{title} <Badge tone={warnings.some(w => w.severity === 'error') ? 'danger' : 'amber'}>{warnings.length}</Badge></summary><ul>{warnings.map((w, i) => <li key={i} className={w.severity === 'error' ? 'warning-error' : ''}>{w.hour != null && <b>{String(w.hour).padStart(2, '0')}:00 · </b>}{w.message}</li>)}</ul></details>;
}
export function Empty({ title = 'Your plan starts here.', description = 'Generate a day plan to see the result of your choices.', action }) {
  return <div className="empty-state"><span className="empty-icon"><Icon name="plan" size={28}/></span><h2>{title}</h2><p>{description}</p>{action}</div>;
}

export function Field({ label, help, children, className = '' }) {
  return <label className={`field ${className}`}><span>{label}</span>{children}{help && <small>{help}</small>}</label>;
}
export function NumberField({ label, value, onChange, min, max, step = 1, help, ...props }) {
  return <Field label={label} help={help}><input type="number" value={value} min={min} max={max} step={step} onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))} {...props}/></Field>;
}
export function Toggle({ label, checked, onChange, help }) {
  return <label className="toggle-field"><span><strong>{label}</strong>{help && <small>{help}</small>}</span><input type="checkbox" role="switch" checked={checked} onChange={e => onChange(e.target.checked)}/><span className="switch" aria-hidden="true"/></label>;
}

// SVG coordinates and formatting are presentation only; values are API data.
export function LineChart({ series, labels, unit = 'kWh', height = 248, label, range }) {
  const width = 780, top = 18, bottom = 30, left = 54, right = 16;
  const plotH = height - top - bottom, plotW = width - left - right;
  const max = Math.max(1, ...series.flatMap(s => s.values), ...(range?.high || [])) * 1.12;
  const x = i => left + i * plotW / Math.max(1, labels.length - 1);
  const y = v => top + plotH - (v / max) * plotH;
  const path = values => values.map((v, i) => `${i ? 'L' : 'M'} ${x(i)} ${y(v)}`).join(' ');
  const rangePath = range ? `${path(range.high)} ${range.low.map((v, i) => [x(i), y(v)]).reverse().map(([a, b]) => `L ${a} ${b}`).join(' ')} Z` : '';
  return <div className="chart"><div className="chart-unit">{unit}</div><svg role="img" aria-label={label} viewBox={`0 0 ${width} ${height}`}><title>{label}</title>{Array.from({ length: 5 }, (_, i) => { const value = max / 4 * i; return <g key={i}><line x1={left} x2={width - right} y1={y(value)} y2={y(value)} className="grid-line"/><text x={left - 12} y={y(value) + 4} textAnchor="end">{number(value, max < 2 ? 1 : 0)}</text></g>; })}{range && <path d={rangePath} fill="var(--accent)" opacity=".055"/>}{series.map((s, si) => <g key={s.name}><path d={path(s.values)} fill="none" stroke={s.color} strokeWidth={si === 0 ? 2.8 : 2.2} strokeDasharray={s.dashed ? '5 5' : undefined} strokeLinecap="round" strokeLinejoin="round"/>{s.values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r="3.5" fill={s.color} className="chart-point"><title>{`${labels[i]} · ${s.name}: ${number(v, 2)} ${unit}`}</title></circle>)}</g>)}{labels.map((l, i) => (i % (labels.length > 12 ? 4 : 1) === 0 || i === labels.length - 1) && <text key={i} x={x(i)} y={height - 4} textAnchor="middle">{l}</text>)}</svg><div className="chart-legend">{series.map(s => <span key={s.name}><i style={{ background: s.color }}/>{s.name}</span>)}{range && <span><i className="band-key"/>Original low–high range</span>}</div></div>;
}

export function FlowBars({ items, unit = 'kWh' }) {
  const max = Math.max(...items.map(i => i.value), 1);
  return <div className="flow-bars">{items.map((i, index) => <div className="flow-row" key={i.label}><div className="flow-label"><span><i style={{ background: i.color || ['var(--accent)', 'var(--green)', 'var(--gold)', 'var(--slate)'][index % 4] }}/>{i.label}</span><b>{number(i.value, 1)} <small>{unit}</small></b></div><div className="flow-track"><span style={{ width: `${i.value / max * 100}%`, background: i.color || ['var(--accent)', 'var(--green)', 'var(--gold)', 'var(--slate)'][index % 4] }}/></div></div>)}</div>;
}

export function SafetySummary({ summary }) {
  return <div className="safety-strip"><span className={summary.critical_status === 'protected' ? 'text-green' : 'text-danger'}><Icon name="outage" size={16}/>Critical loads: {summary.critical_status.replaceAll('_', ' ')}</span><span className={summary.comfort_status === 'within_limits' ? 'text-green' : 'text-danger'}><Icon name="check" size={16}/>Comfort: {summary.comfort_status.replaceAll('_', ' ')}</span></div>;
}
