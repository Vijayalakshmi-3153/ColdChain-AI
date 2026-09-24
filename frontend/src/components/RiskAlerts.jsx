import { useEffect, useState } from "react";
import axios from "axios";
import { fmtTime } from "../utils/formatting.js";

/** Alerts list for a shipment, fetched from GET /shipments/{id}/alerts. */
export const RiskAlerts = ({ shipmentId }) => {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (shipmentId == null) return;
    setLoading(true);
    axios
      .get(`/api/shipments/${shipmentId}/alerts`)
      .then((res) => {
        setAlerts(Array.isArray(res.data) ? res.data : []);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message || "Unable to fetch live alerts from server");
        setAlerts([]);
      })
      .finally(() => setLoading(false));
  }, [shipmentId]);

  if (loading) return <div className="data-empty-hint">Loading alerts registry from database...</div>;
  if (error) return <div className="app-banner-error">{error}</div>;
  if (!alerts.length) return <div className="data-empty-hint">No active or historical alerts recorded for this shipment.</div>;

  return (
    <div className="modern-table-responsive">
      <table className="modern-data-table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Severity</th>
            <th>Trigger Message</th>
            <th>Action Required</th>
            <th>Status</th>
            <th>Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((a) => {
            const sev = String(a.severity || "info").toLowerCase();
            return (
              <tr key={a.id}>
                <td>
                  <strong className="alert-type-name">{a.alert_type}</strong>
                </td>
                <td>
                  <span className={`alert-severity-badge sev-${sev}`}>
                    {a.severity || "INFO"}
                  </span>
                </td>
                <td>
                  <span className="alert-msg-text">{a.message}</span>
                </td>
                <td>
                  <span className="alert-action-text">{a.recommended_action || "—"}</span>
                </td>
                <td>
                  <span className={`ack-pill ${a.acknowledged ? "ack-yes" : "ack-no"}`}>
                    {a.acknowledged ? "Resolved" : "Pending"}
                  </span>
                </td>
                <td>
                  <span className="time-cell">{fmtTime(a.created_at)}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
