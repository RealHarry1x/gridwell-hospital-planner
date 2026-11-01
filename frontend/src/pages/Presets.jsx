import React, { useState } from 'react';
import { api, hourLabel, number } from '../api';
import { Badge, Card, Field, Icon, Modal, PageTitle } from '../components';
import { GoalChoices } from '../PlanningHelp';
import { PlanningControls } from '../ResourceControls';
import { useWorkspace } from '../context';

export function Presets() {
  const w = useWorkspace();
  const [editing, setEditing] = useState(null), [name, setName] = useState(''), [description, setDescription] = useState('');
  const [draft, setDraft] = useState({ ...w.settings }), [deleting, setDeleting] = useState(null);
  const update = (key, value) => setDraft(current => ({ ...current, [key]: value }));
  async function save(event) {
    event.preventDefault();
    await w.act('Saving your resource preset…', async () => {
      await api(editing ? `/presets/${editing}` : '/presets', { method: editing ? 'PUT' : 'POST', body: { name, description, settings: draft } });
      w.setPresets(await api('/presets')); setEditing(null); setName(''); setDescription('');
      w.notify('Preset saved. Your current day plan was kept; choose Load into draft when you want to use it.');
    });
  }
  async function remove() {
    const next = await w.act('Deleting custom preset…', async () => {
      await api(`/presets/${deleting.id}`, { method: 'DELETE' }); w.setPresets(await api('/presets')); return true;
    });
    if (next) { if (editing === deleting.id) { setEditing(null); setName(''); setDescription(''); } setDeleting(null); w.notify('Custom preset deleted. Saved plans are kept.'); }
  }
  function edit(preset) {
    setEditing(preset.id); setName(preset.name); setDescription(preset.description); setDraft({ ...preset.settings });
    document.getElementById('preset-editor')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  return <>
    <PageTitle eyebrow="PRIORITIES & YOUR AVAILABLE RESOURCES" title="Save settings you understand."
      description="A goal changes how hours are ranked. A custom preset saves a complete equipment and operating setup. Loading either still requires recalculation."/>
    <Card title="Planning goals: what changes?" subtitle="Selecting a goal keeps your equipment, comfort limits, work windows and hourly edits.">
      <GoalChoices/>
      <div className="soft-note">Balanced weighs cost and emissions together. Lowest cost and Lowest emissions each focus on one priority. None is a guaranteed optimum, and each may trade cost, carbon and grid peak differently.</div>
      <button className="text-button spaced" onClick={() => w.navigate('plan')}>Review this goal in Day Plan and calculate <Icon name="arrow" size={15}/></button>
    </Card>
    <div className="section-heading"><div><p className="eyebrow">COMPLETE RESOURCE SETUPS</p><h2>Your custom presets</h2></div>
      <button className="button" disabled={!!w.busy} onClick={() => { setEditing(null); setName(''); setDescription(''); setDraft({ ...w.settings }); document.getElementById('preset-editor')?.scrollIntoView({ behavior: 'smooth' }); }}>Copy current draft settings</button></div>
    <div className="preset-grid">{w.presets.filter(preset => !preset.built_in).map(preset => {
      const matches = Object.entries(preset.settings).every(([key, value]) => w.settings[key] === value);
      return <Card key={preset.id} className={`preset-card ${matches ? 'selected-preset' : ''}`}><div className="preset-top"><span className="preset-symbol"><Icon name="presets" size={25}/></span><Badge>{matches ? 'MATCHES DRAFT' : 'SAVED SETUP'}</Badge></div>
        <h2>{preset.name}</h2><p>{preset.description}</p><dl className="resource-facts">
          <div><dt>Planning priority</dt><dd>{w.config.goals.find(goal => goal.id === preset.settings.objective)?.name}</dd></div>
          <div><dt>Solar / battery</dt><dd>{number(preset.settings.solar_capacity_kwp)} kWp / {number(preset.settings.battery_capacity_kwh)} kWh</dd></div>
          <div><dt>Normal reserve</dt><dd>{preset.settings.reserve_pct}%</dd></div>
          <div><dt>Indoor limits</dt><dd>{preset.settings.comfort_min_c}–{preset.settings.comfort_max_c}°C</dd></div>
          <div><dt>Laundry window</dt><dd>{hourLabel(preset.settings.laundry_start)}–{hourLabel(preset.settings.laundry_end)}</dd></div>
          <div><dt>Generator / fuel</dt><dd>{number(preset.settings.generator_capacity_kw)} kW / {preset.settings.generator_fuel_pct}%</dd></div>
        </dl><div className="button-row"><button className="button small" disabled={!!w.busy} onClick={() => w.usePreset(preset)}>Load into draft <Icon name="arrow" size={15}/></button>
          <button className="text-button" disabled={!!w.busy} onClick={() => edit(preset)}>Edit saved setup</button>
          <button className="text-button danger-text" disabled={!!w.busy} onClick={() => setDeleting(preset)}>Delete</button></div>
      </Card>;
    })}</div>
    {!w.presets.some(preset => !preset.built_in) && <div className="soft-note">No custom setups yet. Use the editor below to save the resources and operating limits you want to reuse.</div>}
    <Card id="preset-editor" title={editing ? 'Edit saved resource setup' : 'Create a resource setup'} subtitle="Editing this form does not change the current plan. Save it, then explicitly load it when needed." className="spaced">
      <form onSubmit={save}><fieldset className="resource-controls" disabled={!!w.busy}>
        <legend className="sr-only">Custom preset editor</legend>
        <div className="controls-grid two"><Field label="Preset name"><input required maxLength={60} value={name} onChange={event => setName(event.target.value)} placeholder="e.g. Larger battery, daytime laundry"/></Field>
          <Field label="When to use it"><input maxLength={300} value={description} onChange={event => setDescription(event.target.value)} placeholder="Describe your equipment or operating needs"/></Field></div>
        <GoalChoices settings={draft} onChange={update}/><PlanningControls settings={draft} onChange={update}/>
        <div className="button-row spaced"><button className="button primary" disabled={!name.trim()} type="submit"><Icon name="plus" size={17}/>{editing ? 'Save setup changes' : 'Save custom setup'}</button>
          {editing && <button type="button" className="text-button" onClick={() => { setEditing(null); setName(''); setDescription(''); setDraft({ ...w.settings }); }}>Cancel editing</button>}</div>
      </fieldset></form>
    </Card>
    <div className="note"><Icon name="outage"/><p>Loading a full setup replaces draft equipment and operating settings and clears manual hourly edits. Critical-demand protection, the 10% outage threshold and all hard checks remain enforced by Python.</p></div>
    {deleting && <Modal title={`Delete “${deleting.name}”?`} onClose={() => { if (!w.busy) setDeleting(null); }}><p>Only this saved custom setup is removed. Existing plans and their recorded settings are kept.</p>
      <div className="button-row spaced"><button className="button" disabled={!!w.busy} onClick={() => setDeleting(null)}>Keep preset</button><button className="button danger-button" disabled={!!w.busy} onClick={remove}>Delete custom preset</button></div>
    </Modal>}
  </>;
}
