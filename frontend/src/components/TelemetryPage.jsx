import { useEffect, useState } from "react";
import { fetchJSON } from "../api.js";
import { fmtTime, fmtTemp } from "../utils/formatting.js";

const formatApiError = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || JSON.stringify(item)).join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return err?.message || fallback;
};

export const TelemetryPage = ({ backendOk, shipmentId }) => {
  const [telemetry, setTelemetry] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const [form, setForm] = useState({
    shipment_id: "",
    temperature: "",
    humidity: "",
    latitude: "",
    longitude: "",
    battery_level: "",
    door_open: false,
  });

  const fetchTelemetry = async (preferredId) => {
    setLoading(true);
    setError(null);
    try {
      let sid = preferredId;
      if (sid == null || sid === "") {
        const fromForm = form.shipment_id ? parseInt(form.shipment_id, 10) : null;
        sid = Number.isFinite(fromForm) ? fromForm : shipmentId;
      }
      if (sid == null) {
        const ships = await fetchJSON("/shipments");
        sid =
  Array.isArray(ships) && ships.length
    ? ships[0].shipment_id
    : null;
      }
      if (sid == null) {
        setTelemetry([]);
        return;
      }
      const res = await fetchJSON(`/shipments/${sid}/telemetry?limit=100`);
      setTelemetry(Array.isArray(res) ? res : []);
    } catch (err) {
      setError(formatApiError(err, "Failed to load telemetry"));
      setTelemetry([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (backendOk) fetchTelemetry(shipmentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendOk, shipmentId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.shipment_id || !form.temperature) return;
    setSuccessMsg(null);
    const payload = {
      shipment_id: parseInt(form.shipment_id, 10),
      temperature: parseFloat(form.temperature),
      humidity: form.humidity ? parseFloat(form.humidity) : null,
      latitude: form.latitude ? parseFloat(form.latitude) : null,
      longitude: form.longitude ? parseFloat(form.longitude) : null,
      battery_level: form.battery_level ? parseFloat(form.battery_level) : null,
      door_open: form.door_open,
    };
    try {
      const API_BASE = import.meta.env.PROD
  ? "https://coldchain-backend-cfes.onrender.com"
  : "/api";

await fetch(`${API_BASE}/telemetry`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify(payload),
});
      setSuccessMsg(`Telemetry recorded successfully for Shipment #${payload.shipment_id}`);
      setForm({
        shipment_id: "",
        temperature: "",
        humidity: "",
        latitude: "",
        longitude: "",
        battery_level: "",
        door_open: false,
      });
      fetchTelemetry(payload.shipment_id);
    } catch (err) {
      setError(formatApiError(err, "Failed to submit telemetry"));
    }
  };

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm({ ...form, [name]: type === "checkbox" ? checked : value });
  };

  return (
    <div className="telemetry-page-container">
      <div className="section-header">
        <div>
          <h2 className="section-title">Telemetry Sensor Ingestion & Log</h2>
          <p className="section-subtitle">Simulate or register edge IoT device payloads into the pipeline</p>
        </div>
      </div>

      <div className="content-card telemetry-card">
        <h3 className="card-title">Manual Telemetry Ingestion Form</h3>
        <p className="card-subtitle">Broadcast sensor telemetry to trigger ML risk assessment and alert pipelines</p>

        <form onSubmit={handleSubmit} className="modern-telemetry-form">
          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="shipment_id">Shipment ID *</label>
              <input
                id="shipment_id"
                name="shipment_id"
                type="number"
                placeholder="e.g. 1"
                value={form.shipment_id}
                onChange={handleInputChange}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="temperature">Temperature (°C) *</label>
              <input
                id="temperature"
                name="temperature"
                type="number"
                step="0.01"
                placeholder="e.g. 4.5"
                value={form.temperature}
                onChange={handleInputChange}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="humidity">Humidity (%)</label>
              <input
                id="humidity"
                name="humidity"
                type="number"
                step="0.1"
                placeholder="e.g. 55"
                value={form.humidity}
                onChange={handleInputChange}
              />
            </div>

            <div className="form-group">
              <label htmlFor="battery_level">Battery Level (%)</label>
              <input
                id="battery_level"
                name="battery_level"
                type="number"
                step="0.1"
                placeholder="e.g. 98.0"
                value={form.battery_level}
                onChange={handleInputChange}
              />
            </div>

            <div className="form-group">
              <label htmlFor="latitude">Latitude</label>
              <input
                id="latitude"
                name="latitude"
                type="number"
                step="0.0001"
                placeholder="e.g. 19.076"
                value={form.latitude}
                onChange={handleInputChange}
              />
            </div>

            <div className="form-group">
              <label htmlFor="longitude">Longitude</label>
              <input
                id="longitude"
                name="longitude"
                type="number"
                step="0.0001"
                placeholder="e.g. 72.877"
                value={form.longitude}
                onChange={handleInputChange}
              />
            </div>
          </div>

          <div className="form-checkbox-row">
            <label className="checkbox-custom-label">
              <input
                name="door_open"
                type="checkbox"
                checked={form.door_open}
                onChange={handleInputChange}
              />
              <span>Container Door Open / Breach Sensor Active</span>
            </label>

            <button type="submit" className="primary-action-btn" disabled={!backendOk}>
              Ingest Telemetry Packet
            </button>
          </div>
        </form>

        {successMsg && <div className="app-banner-success">{successMsg}</div>}
        {error && <div className="app-banner-error">{error}</div>}
      </div>

      <div className="content-card">
        <div className="card-header-row">
          <div>
            <h3 className="card-title">Recent Telemetry Readings</h3>
            <span className="card-subtitle">Sensor history for targeted shipment</span>
          </div>
          <button
            type="button"
            className="secondary-action-btn"
            onClick={() => fetchTelemetry()}
          >
            Refresh Readings
          </button>
        </div>

        {loading ? (
          <div className="data-loading-hint">Loading telemetry sequence...</div>
        ) : !telemetry.length ? (
          <div className="data-empty-hint">No telemetry readings found for this shipment.</div>
        ) : (
          <div className="modern-table-responsive">
            <table className="modern-data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Shipment ID</th>
                  <th>Temperature</th>
                  <th>Humidity</th>
                  <th>Battery</th>
                  <th>GPS Position</th>
                  <th>Door Status</th>
                </tr>
              </thead>
              <tbody>
                {telemetry.map((t, i) => (
                  <tr key={t.id ?? i}>
                    <td>
                      <span className="time-cell">{fmtTime(t.timestamp)}</span>
                    </td>
                    <td>
                      <strong>#{t.shipment_id}</strong>
                    </td>
                    <td>
                      <span className="temp-primary">{fmtTemp(t.temperature)}</span>
                    </td>
                    <td>{t.humidity != null ? `${t.humidity}%` : "—"}</td>
                    <td>{t.battery_level != null ? `${t.battery_level}%` : "—"}</td>
                    <td>
                      {t.latitude != null && t.longitude != null ? (
                        <span className="geo-sub">
                          {Number(t.latitude).toFixed(2)}, {Number(t.longitude).toFixed(2)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <span className={`status-badge ${t.door_open ? "status-danger" : "status-active"}`}>
                        {t.door_open ? "OPEN" : "CLOSED"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
