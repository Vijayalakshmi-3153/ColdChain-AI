/**
 * API helper.
 *
 * Local development:
 *   /api -> Vite proxy -> http://localhost:8000
 *
 * GitHub Pages:
 *   /api -> Render backend
 */

const API_BASE = import.meta.env.PROD
  ? "https://coldchain-backend-cfes.onrender.com"
  : "/api";

export const fetchJSON = async (path, { signal } = {}) => {
  const res = await fetch(`${API_BASE}${path}`, { signal });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let detail = `HTTP ${res.status}`;

    try {
      const json = JSON.parse(text);
      detail = json.detail || json.message || detail;
    } catch {
      if (text) detail = text;
    }

    const err = new Error(detail);
    err.status = res.status;
    err.data = null;
    throw err;
  }

  return res.json();
};

export const usePolling = (path, intervalMs = 15000) => {
  return fetchJSON(path);
};

export const fetchHealth = (signal) => fetchJSON("/health", { signal });
export const fetchSummary = (signal) => fetchJSON("/dashboard/summary", { signal });
export const fetchShipments = (signal) => fetchJSON("/dashboard/shipments", { signal });
export const fetchMap = (signal) => fetchJSON("/dashboard/map", { signal });
export const fetchRisk = (id, signal) => fetchJSON(`/shipments/${id}/risk`, { signal });
export const fetchAlerts = (id, signal) => fetchJSON(`/shipments/${id}/alerts`, { signal });
export const fetchExposure = (id, signal) => fetchJSON(`/shipments/${id}/exposure`, { signal });
export const fetchTelemetry = (id, signal) => fetchJSON(`/shipments/${id}/telemetry`, { signal });

export const acknowledgeAlert = (alertId) =>
  fetch(`${API_BASE}/alerts/${alertId}/acknowledge`, { method: "POST" }).then((r) => {
    if (!r.ok) throw new Error(`acknowledge failed: ${r.status}`);
    return r.json();
  });