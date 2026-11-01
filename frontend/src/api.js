// All dispatch, safety and accounting comes from Python. This file only moves JSON.
export async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new Error('Cannot reach the Python backend. Start the backend, then retry. See README.md.');
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.error?.details?.map(e => `${e.field}: ${e.message}`).join(' · ');
    throw new Error([payload?.error?.message || `Request failed (${response.status}).`, detail].filter(Boolean).join(' '));
  }
  if (!payload || !('data' in payload)) throw new Error('Unexpected API response. Check the backend and Vite proxy.');
  return payload.data;
}

export const number = (value, decimals = 0) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: decimals, minimumFractionDigits: decimals }).format(value ?? 0);
export const money = value => `₹${number(value)}`;
export const hourLabel = hour => `${String(hour).padStart(2, '0')}:00`;
export const signed = (value, decimals = 0) => `${value > 0 ? '+' : value < 0 ? '−' : ''}${number(Math.abs(value ?? 0), decimals)}`;
export const longDate = value => new Date(`${value}T12:00:00`).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
