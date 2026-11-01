import React, { act } from 'react';
import test, { beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const fixtures = JSON.parse(readFileSync(new URL('./fixtures.json', import.meta.url)));
const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: 'http://gridwell.test/#overview' });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, location: dom.window.location,
  localStorage: dom.window.localStorage, IS_REACT_ACT_ENVIRONMENT: true });
window.scrollTo = () => {};
window.HTMLElement.prototype.scrollIntoView = () => {};
const { createRoot } = await import('react-dom/client');
const { default: App } = await import('../src/App');
let root, calls, state;
const clone = value => structuredClone(value);

beforeEach(() => {
  window.history.replaceState({}, '', '/#overview'); localStorage.clear();
  document.body.innerHTML = '<div id="root"></div>';
  calls = []; state = { plan: clone(fixtures.initial), reset: false, live: false, presets: clone(fixtures.presets) };
  globalThis.fetch = async (path, options = {}) => {
    const url = new URL(path, 'http://gridwell.test');
    const body = options.body ? JSON.parse(options.body) : null;
    calls.push({ path: url.pathname, method: options.method || 'GET', body, search: url.searchParams });
    let data;
    if (url.pathname === '/api/config') data = state.reset ? fixtures.reset_config : fixtures.config;
    else if (url.pathname === '/api/presets' && !body) data = state.presets;
    else if (url.pathname === '/api/trends') data = state.reset ? fixtures.reset_history : fixtures.history;
    else if (url.pathname === '/api/plans') data = state.plan;
    else if (url.pathname === '/api/forecast') data = state.live ? fixtures.live_forecast : state.reset ? fixtures.reset_forecast : fixtures.forecasts[url.searchParams.get('day_type') || 'normal'];
    else if (url.pathname === '/api/forecast/verify') data = fixtures.forecasts[body.day_type];
    else if (url.pathname === '/api/plans/generate') { data = fixtures.fresh; state.plan = clone(data); }
    else if (url.pathname.endsWith('/recalculate')) { data = body.settings.reserve_pct === 30 ? fixtures.changed : fixtures.same; state.plan = clone(data); }
    else if (url.pathname.endsWith('/comparison')) data = state.plan.comparison;
    else if (url.pathname === '/api/demand-context') data = fixtures.demand_context;
    else if (url.pathname === '/api/demo/reset') { state.reset = true; state.plan = null; data = fixtures.reset; }
    else if (url.pathname === '/api/outage/simulate') data = fixtures.outage;
    else throw new Error(`Unmocked UI request: ${options.method || 'GET'} ${url.pathname}`);
    return { ok: true, status: 200, json: async () => ({ data: clone(data), meta: { simulated: true } }) };
  };
});
afterEach(async () => { if (root) { await act(async () => root.unmount()); root = null; } });

async function settle() { await act(async () => { await new Promise(setImmediate); }); }
async function mount() { root = createRoot(document.getElementById('root')); await act(async () => root.render(<App/>)); await settle(); }
const button = (text, scope = document) => [...scope.querySelectorAll('button')].find(element => element.textContent.trim() === text || element.textContent.trim().startsWith(text));
async function click(element) { assert.ok(element, 'Expected action exists'); await act(async () => element.click()); await settle(); }
function input(label) {
  const field = [...document.querySelectorAll('label')].find(element => element.querySelector('span')?.textContent === label);
  assert.ok(field, `Expected input: ${label}`); return field.querySelector('input');
}
async function fill(element, value) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(element, String(value));
    element.dispatchEvent(new window.Event('input', { bubbles: true }));
    element.dispatchEvent(new window.Event('change', { bubbles: true }));
  }); await settle();
}
const navigate = name => click(button(name, document.querySelector('nav')));

test('reset confirmation clears saved plan and reports the actual reset counts', async () => {
  await mount();
  const summary = [...document.querySelectorAll('summary')].find(element => element.textContent.includes('Data sources'));
  await click(summary);
  await fill(input("First history day's opening battery (%)"), 80);
  await click(button('Reset demo'));
  assert.ok(document.querySelector('[role="dialog"]'));
  await click(button('Confirm reset'));
  assert.equal(calls.find(call => call.path === '/api/demo/reset').body.initial_soc_pct, 80);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.match(document.body.textContent, /Demo reset complete/);
  assert.match(document.body.textContent, /1 saved plans cleared/);
  assert.equal(state.plan, null);
});

test('resource edit reaches recalculation and a new result revision becomes visible', async () => {
  await mount(); await navigate('Day Plan');
  await fill(input('Normal battery reserve (%)'), 30);
  assert.match(document.body.textContent, /Draft changes pending/);
  await click(button('Recalculate with these settings'));
  assert.equal(calls.find(call => call.path.endsWith('/recalculate')).body.settings.reserve_pct, 30);
  assert.match(document.body.textContent, /Calculated revision 2/);
  assert.equal(document.querySelector('.pending-banner'), null);
});

test('recalculating unchanged inputs explains why the figures match', async () => {
  await mount(); await navigate('Day Plan'); await click(button('Recalculate with these settings'));
  assert.match(document.querySelector('.calculation-result').textContent, /same inputs and saved weather/);
  assert.match(document.body.textContent, /Calculated revision 2/);
});

test('new weather draft uses generation rather than rewriting the frozen plan', async () => {
  await mount(); await navigate('Day Plan'); await click(button('New draft with current weather'));
  const sent = calls.find(call => call.path === '/api/plans/generate');
  assert.equal(sent.body.settings.solar_capacity_kwp, 150);
  assert.notEqual(state.plan.id, fixtures.initial.id);
  assert.equal(state.plan.revision, 1);
  assert.ok(!calls.some(call => call.path.endsWith('/recalculate') || call.path === '/api/demo/reset'));
});

test('day scenario selection loads different conditions and explicit working settings', async () => {
  await mount(); await navigate('Day Plan');
  const choices = document.querySelector('[aria-label="Choose a day scenario"]');
  await click(button('Heatwave', choices));
  assert.ok(calls.some(call => call.path === '/api/forecast' && call.search.get('day_type') === 'heatwave'));
  assert.match(document.body.textContent, /55% more cooling/);
  await click(button('Apply suggested working settings'));
  assert.equal(input('Normal battery reserve (%)').value, '30');
  assert.equal(input('Laundry may start from hour').value, '7');
  assert.equal(input('Lowest allowed indoor temperature (°C)').value, '22');
});

test('choosing a goal preserves equipment inventory', async () => {
  await mount(); await navigate('Presets'); await click(button('Lowest cost', document.querySelector('[aria-label="Choose a planning priority"]')));
  await navigate('Day Plan');
  assert.equal(input('Installed solar capacity (kWp)').value, '150');
  assert.equal(input('Battery energy capacity (kWh)').value, '1500');
});

test('editing a saved resource setup does not apply it to the current plan', async () => {
  await mount(); await navigate('Presets'); await click(button('Edit saved setup'));
  assert.equal(input('Battery energy capacity (kWh)').value, '1200');
  await navigate('Day Plan');
  assert.equal(input('Battery energy capacity (kWh)').value, '1500');
});

test('outage controls submit independent test inputs and preserve the day plan', async () => {
  await mount(); await navigate('Outage Readiness');
  await fill(input('Power cut starts at hour'), 0); await fill(input('Power returns at hour'), 8);
  await fill(input('Beginning-of-day battery override (%)'), 10);
  const generator = [...document.querySelectorAll('label')].find(element => element.textContent.includes('Generator is available')).querySelector('input');
  await click(generator); await click(button('Run outage rehearsal'));
  const sent = calls.find(call => call.path === '/api/outage/simulate').body;
  assert.equal(sent.settings.outage_start, 0); assert.equal(sent.settings.outage_end, 8); assert.equal(sent.settings.generator_available, false);
  assert.equal(sent.plan_id, fixtures.initial.id);
  assert.match(document.body.textContent, /Power-cut timeline/);
  await navigate('Day Plan');
  assert.equal(input('Power cut starts at hour').value, '18');
  assert.ok(!calls.some(call => call.path.endsWith('/recalculate') || call.path.endsWith('/approve')));
});

test('seven-day demand popup displays context and the true model explanation', async () => {
  await mount(); await click(button('Last 7 days & estimate basis'));
  const dialog = document.querySelector('[role="dialog"]');
  assert.match(dialog.textContent, /not training data/);
  assert.equal(dialog.querySelectorAll('tbody tr').length, 7);
  assert.equal(calls.find(call => call.path === '/api/demand-context').search.get('plan_id'), fixtures.initial.id);
  await act(async () => dialog.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
  assert.equal(document.querySelector('[role="dialog"]'), null);
});

test('failure event starts in the selected cut window instead of a stale default hour', async () => {
  await mount(); await navigate('Outage Readiness');
  await fill(input('Power cut starts at hour'), 0); await fill(input('Power returns at hour'), 8);
  const failure = [...document.querySelectorAll('label')].find(element => element.textContent.includes('Simulate generator failure')).querySelector('input');
  await click(failure);
  assert.equal(input('Failure begins at hour').value, '0');
});

test('comparison removes the duplicate safety cards while retaining the numeric comparison', async () => {
  await mount(); await navigate('Comparison');
  const headings = [...document.querySelectorAll('h2')].map(element => element.textContent);
  assert.ok(!headings.includes('Recommended plan') && !headings.includes('Usual routine'));
  assert.ok(headings.includes('The numbers behind the difference'));
});

test('Overview shows weather provenance and no low-high chart legend', async () => {
  state.plan = null; state.live = true; await mount();
  assert.match(document.body.textContent, /Open-Meteo live forecast/);
  assert.match(document.body.textContent, /Solar potential for this day/);
  assert.equal(document.querySelectorAll('.weather-hour').length, 24);
  assert.ok(!document.body.textContent.includes('Original low–high range'));
});
