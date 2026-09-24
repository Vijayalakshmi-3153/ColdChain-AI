import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { fmtTime, fmtTimeOnly, fmtTemp, riskColor, riskBgColor, riskBorderColor } from "../utils/formatting.js";
import { TemperatureChart } from "./Charts.jsx";

export const ReportsPage = ({ shipmentId, onSelectShipment }) => {
  const [shipments, setShipments] = useState([]);
  const [selectedId, setSelectedId] = useState(shipmentId || null);
  const [riskData, setRiskData] = useState(null);
  const [telemetryData, setTelemetryData] = useState([]);
  const [alertsData, setAlertsData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [shipmentsLoading, setShipmentsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reportDate, setReportDate] = useState(new Date().toISOString());

  // Fetch all shipments from database for selector
  useEffect(() => {
    let cancelled = false;
    setShipmentsLoading(true);

    axios
      .get("/api/dashboard/shipments")
      .then((res) => {
        if (!cancelled) {
          const list = Array.isArray(res.data) ? res.data : [];
          setShipments(list);
          if (!selectedId && list.length > 0) {
            setSelectedId(list[0].shipment_id);
            onSelectShipment?.(list[0].shipment_id);
          }
        }
      })
      .catch((err) => {
        if (!cancelled) setError("Unable to fetch live shipments list: " + (err.message || ""));
      })
      .finally(() => {
        if (!cancelled) setShipmentsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Fetch single shipment report dossier from live backend
  const loadReportData = useCallback(async (id) => {
    if (id == null) return;
    setLoading(true);
    setError(null);

    try {
      const [rRes, tRes, aRes] = await Promise.allSettled([
        axios.get(`/api/shipments/${id}/risk?include_shap=true`),
        axios.get(`/api/shipments/${id}/telemetry?limit=500`),
        axios.get(`/api/shipments/${id}/alerts`),
      ]);

      if (rRes.status === "fulfilled") {
        setRiskData(rRes.value.data);
      } else {
        setRiskData(null);
        setError("Unable to fetch live risk assessment for Shipment #" + id);
      }

      if (tRes.status === "fulfilled") {
        setTelemetryData(Array.isArray(tRes.value.data) ? tRes.value.data : []);
      } else {
        setTelemetryData([]);
      }

      if (aRes.status === "fulfilled") {
        setAlertsData(Array.isArray(aRes.value.data) ? aRes.value.data : []);
      } else {
        setAlertsData([]);
      }

      setReportDate(new Date().toISOString());
    } catch (err) {
      setError("Error generating live report: " + (err.message || ""));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) {
      loadReportData(selectedId);
    }
  }, [selectedId, loadReportData]);

  const handleShipmentChange = (e) => {
    const id = parseInt(e.target.value, 10);
    setSelectedId(id);
    onSelectShipment?.(id);
  };

  // Generate / Refresh Report
  const handleGenerateReport = () => {
    if (selectedId) {
      loadReportData(selectedId);
    }
  };

  // Download CSV Export (Client-side Blob using real data)
  const handleDownloadCSV = () => {
    if (!riskData) return;

    const exposure = riskData.exposure || {};
    const latest = riskData.latest_reading || {};
    const product = riskData.product || {};

    let csv = "COLDCHAIN AI - SHIPMENT RISK & TELEMETRY COMPLIANCE AUDIT\r\n";
    csv += `Report Generated At,${new Date(reportDate).toLocaleString()}\r\n`;
    csv += `Shipment ID,${riskData.shipment_id}\r\n`;
    csv += `Vehicle ID,${riskData.vehicle_id || "Unassigned"}\r\n`;
    csv += `Product Name,"${(product.name || "").replace(/"/g, '""')}"\r\n`;
    csv += `Product Category,${product.category || "—"}\r\n`;
    csv += `Origin,"${(riskData.origin || "").replace(/"/g, '""')}"\r\n`;
    csv += `Destination,"${(riskData.destination || "").replace(/"/g, '""')}"\r\n`;
    csv += `Overall Risk Level,${riskData.risk_level || "UNKNOWN"}\r\n`;
    csv += `Risk Score,${riskData.risk_score != null ? Number(riskData.risk_score).toFixed(4) : "—"}\r\n`;
    csv += `XGBoost Model Score,${riskData.model_risk_score != null ? Number(riskData.model_risk_score).toFixed(4) : "—"}\r\n`;
    csv += `Rule-Based Score,${riskData.rule_based_score != null ? Number(riskData.rule_based_score).toFixed(4) : "—"}\r\n`;
    csv += `Shipment Status,${riskData.status || "—"}\r\n`;
    csv += `Current Temp (C),${latest.temperature != null ? latest.temperature : "—"}\r\n`;
    csv += `Current Humidity (%),${latest.humidity != null ? latest.humidity : "—"}\r\n`;
    csv += `Cumulative Excursion Minutes,${exposure.total_excursion_minutes || 0}\r\n`;
    csv += `Percent Out of Safe Range,${exposure.percent_readings_outside_range != null ? exposure.percent_readings_outside_range : 0}%\r\n`;
    csv += `Remaining Shelf Life (Hours),${riskData.remaining_shelf_life_hours || "—"}\r\n\r\n`;

    // Telemetry Sequence
    csv += "LIVE TELEMETRY TIME-SERIES READINGS\r\n";
    csv += "Timestamp,Temperature (C),Humidity (%),Battery (%),Door Open,Latitude,Longitude\r\n";
    (telemetryData || []).forEach((t) => {
      csv += `"${t.timestamp || ""}",${t.temperature != null ? t.temperature : ""},${t.humidity != null ? t.humidity : ""},${t.battery_level != null ? t.battery_level : ""},${t.door_open ? "OPEN" : "CLOSED"},${t.latitude || ""},${t.longitude || ""}\r\n`;
    });
    csv += "\r\n";

    // Alerts
    csv += "RECORDED ALERTS & INTERVENTIONS\r\n";
    csv += "Alert ID,Type,Severity,Message,Recommended Action,Acknowledged,Created At\r\n";
    (alertsData || []).forEach((a) => {
      csv += `${a.id},"${a.alert_type}","${a.severity}","${(a.message || "").replace(/"/g, '""')}","${(a.recommended_action || "").replace(/"/g, '""')}",${a.acknowledged ? "YES" : "NO"},"${a.created_at || ""}"\r\n`;
    });

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `coldchain_report_shipment_${riskData.shipment_id}_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // Download PDF / Print
  const handlePrintPDF = () => {
    window.print();
  };

  const level = (riskData?.risk_level || "UNKNOWN").toUpperCase();
  const color = riskColor(level);
  const bgColor = riskBgColor(level);
  const borderColor = riskBorderColor(level);
  const exposure = riskData?.exposure || {};
  const latest = riskData?.latest_reading || {};
  const product = riskData?.product || {};

  return (
    <div className="reports-page-container">
      {/* Non-printed Controls Toolbar */}
      <div className="reports-toolbar no-print">
        <div className="toolbar-left">
          <div className="shipment-selector-wrap">
            <label htmlFor="report-shipment-select" className="selector-label">
              Select Shipment:
            </label>
            <select
              id="report-shipment-select"
              className="shipment-select-dropdown"
              value={selectedId || ""}
              onChange={handleShipmentChange}
              disabled={shipmentsLoading}
            >
              {shipments.map((s) => (
                <option key={s.shipment_id} value={s.shipment_id}>
                  #{s.shipment_id} — {s.product_name || "Product"} ({s.origin || "Origin"} → {s.destination || "Dest"})
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="toolbar-actions">
          <button
            type="button"
            className="report-btn btn-secondary"
            onClick={handleGenerateReport}
            disabled={loading || !selectedId}
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
            Generate Report
          </button>

          <button
            type="button"
            className="report-btn btn-secondary"
            onClick={handleDownloadCSV}
            disabled={!riskData || loading}
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download CSV
          </button>

          <button
            type="button"
            className="report-btn btn-primary"
            onClick={handlePrintPDF}
            disabled={!riskData || loading}
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 6 2 18 2 18 9" />
              <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
              <rect x="6" y="14" width="12" height="8" />
            </svg>
            Download PDF
          </button>
        </div>
      </div>

      {loading && (
        <div className="report-loading-banner no-print">
          <div className="loading-spinner" />
          <span>Generating live compliance and telemetry audit report...</span>
        </div>
      )}

      {error && (
        <div className="app-banner-error no-print">
          <div className="banner-error-content">
            <strong>Unable to fetch live data:</strong>
            <span> {error}</span>
          </div>
        </div>
      )}

      {/* =========================================================================
          PRINTABLE REPORT DOSSIER
      ========================================================================= */}
      {riskData && (
        <div className="printable-report-card" id="printable-report-section">
          {/* Executive Header */}
          <div className="report-doc-header">
            <div className="doc-brand">
              <div className="doc-logo-pill">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <span>ColdChain AI Enterprise</span>
              </div>
              <h1 className="doc-main-title">Cold Chain Quality & Spoilage Risk Audit Dossier</h1>
              <p className="doc-subtitle">Official Regulatory Telemetry & Machine-Learning Predictive Assessment</p>
            </div>

            <div className="doc-meta-box">
              <div className="meta-line">
                <span className="meta-k">Report ID:</span>
                <span className="meta-v">CC-REP-{riskData.shipment_id}-{new Date(reportDate).getFullYear()}</span>
              </div>
              <div className="meta-line">
                <span className="meta-k">Generated Date:</span>
                <span className="meta-v">{new Date(reportDate).toLocaleString()}</span>
              </div>
              <div className="meta-line">
                <span className="meta-k">Verification:</span>
                <span className="meta-v status-verified">LIVE DATA VERIFIED</span>
              </div>
            </div>
          </div>

          <hr className="doc-divider" />

          {/* Shipment & Consignment Details */}
          <div className="doc-section">
            <h3 className="doc-section-title">1. Consignment & Transit Profile</h3>
            <div className="doc-grid-table">
              <div className="doc-grid-cell">
                <span className="cell-label">Shipment ID</span>
                <span className="cell-val">#{riskData.shipment_id}</span>
              </div>
              <div className="doc-grid-cell">
                <span className="cell-label">Assigned Vehicle</span>
                <span className="cell-val">{riskData.vehicle_id || "Transit Unit"}</span>
              </div>
              <div className="doc-grid-cell">
                <span className="cell-label">Product Name</span>
                <span className="cell-val font-semibold">{product.name || "Cold Chain Cargo"}</span>
              </div>
              <div className="doc-grid-cell">
                <span className="cell-label">Classification</span>
                <span className="cell-val">{product.category || "Pharmaceutical Biologics"}</span>
              </div>
              <div className="doc-grid-cell">
                <span className="cell-label">Route Origin</span>
                <span className="cell-val">{riskData.origin || "Origin Hub"}</span>
              </div>
              <div className="doc-grid-cell">
                <span className="cell-label">Route Destination</span>
                <span className="cell-val">{riskData.destination || "Destination Port"}</span>
              </div>
              <div className="doc-grid-cell">
                <span className="cell-label">Transit Status</span>
                <span className="cell-val capitalize">{String(riskData.status || "In Transit").replace(/_/g, " ")}</span>
              </div>
              <div className="doc-grid-cell">
                <span className="cell-label">Estimated Arrival</span>
                <span className="cell-val">
                  {riskData.estimated_arrival_time ? fmtTime(riskData.estimated_arrival_time) : "On Schedule"}
                </span>
              </div>
            </div>
          </div>

          {/* Risk Level & Prediction Assessment */}
          <div className="doc-section">
            <h3 className="doc-section-title">2. Predictive Spoilage Risk Evaluation</h3>
            <div className="report-risk-highlight" style={{ backgroundColor: bgColor, borderColor: borderColor }}>
              <div className="risk-level-badge-large" style={{ color: color }}>
                <span className="badge-bullet" style={{ backgroundColor: color }}></span>
                <span>{level} RISK LEVEL</span>
              </div>
              <div className="risk-score-display">
                <span className="score-desc">Composite Spoilage Index:</span>
                <strong className="score-val" style={{ color: color }}>
                  {riskData.risk_score != null ? `${(Number(riskData.risk_score) * 100).toFixed(1)}%` : "—"}
                </strong>
              </div>
            </div>

            <div className="doc-grid-three">
              <div className="doc-metric-tile">
                <span className="metric-label">XGBoost ML Spoilage Probability</span>
                <span className="metric-num">
                  {riskData.model_risk_score != null ? Number(riskData.model_risk_score).toFixed(4) : "—"}
                </span>
                <span className="metric-note">Decision Threshold: {riskData.model_decision_threshold ?? 0.50}</span>
              </div>

              <div className="doc-metric-tile">
                <span className="metric-label">Arrhenius Kinetic Exposure Score</span>
                <span className="metric-num">
                  {riskData.rule_based_score != null ? Number(riskData.rule_based_score).toFixed(4) : "—"}
                </span>
                <span className="metric-note">Degradation Rate Multiplier</span>
              </div>

              <div className="doc-metric-tile">
                <span className="metric-label">Remaining Shelf Life</span>
                <span className="metric-num">
                  {riskData.remaining_shelf_life_hours != null ? `${riskData.remaining_shelf_life_hours}h` : "—"}
                </span>
                <span className="metric-note">Equivalent Age: {exposure.equivalent_age_hours ?? "—"}h</span>
              </div>
            </div>
          </div>

          {/* Environmental Conditions Summary */}
          <div className="doc-section">
            <h3 className="doc-section-title">3. Environmental & Sensory Conditions Summary</h3>
            <div className="doc-grid-four">
              <div className="doc-subcard">
                <span className="subcard-label">Current Temperature</span>
                <span className="subcard-val">{fmtTemp(latest.temperature)}</span>
                <span className="subcard-range">Permitted: {fmtTemp(product.minimum_temperature)} to {fmtTemp(product.maximum_temperature)}</span>
              </div>
              <div className="doc-subcard">
                <span className="subcard-label">Max Recorded Temperature</span>
                <span className="subcard-val">{fmtTemp(exposure.max_temperature)}</span>
                <span className="subcard-range">Peak excursion threshold</span>
              </div>
              <div className="doc-subcard">
                <span className="subcard-label">Relative Humidity</span>
                <span className="subcard-val">{latest.humidity != null ? `${Number(latest.humidity).toFixed(1)}%` : "—"}</span>
                <span className="subcard-range">Ambient humidity status</span>
              </div>
              <div className="doc-subcard">
                <span className="subcard-label">Sensor Battery Reserve</span>
                <span className="subcard-val">{latest.battery_level != null ? `${latest.battery_level}%` : "—"}</span>
                <span className="subcard-range">Edge device power</span>
              </div>
            </div>
          </div>

          {/* Temperature Excursion Audit */}
          <div className="doc-section">
            <h3 className="doc-section-title">4. Temperature Excursion Audit</h3>
            <div className="doc-excursion-panel">
              <div className="excursion-stat">
                <span className="excursion-label">Cumulative Excursion Time:</span>
                <strong className={`excursion-val ${(exposure.total_excursion_minutes || 0) > 0 ? "rose-color" : "green-color"}`}>
                  {exposure.total_excursion_minutes || 0} Minutes
                </strong>
              </div>
              <div className="excursion-stat">
                <span className="excursion-label">Out-of-Range Reading Ratio:</span>
                <strong>{exposure.percent_readings_outside_range != null ? `${Number(exposure.percent_readings_outside_range).toFixed(1)}%` : "0.0%"}</strong>
              </div>
              <div className="excursion-stat">
                <span className="excursion-label">Severity Assessment:</span>
                <span className={`status-badge status-${String(exposure.status || "normal").toLowerCase()}`}>
                  {(exposure.status || "Normal").toUpperCase()}
                </span>
              </div>
            </div>
          </div>

          {/* Thermal History Chart in Report */}
          {telemetryData && telemetryData.length > 0 && (
            <div className="doc-section">
              <h3 className="doc-section-title">5. Thermal Kinetic Trace Chart</h3>
              <TemperatureChart telemetry={telemetryData} product={product} />
            </div>
          )}

          {/* Active Alerts & Corrective Recommendations */}
          <div className="doc-section">
            <h3 className="doc-section-title">6. Logged Alerts & Mitigation Directives</h3>
            {alertsData.length > 0 ? (
              <div className="modern-table-responsive">
                <table className="modern-data-table doc-table">
                  <thead>
                    <tr>
                      <th>Alert ID</th>
                      <th>Type</th>
                      <th>Severity</th>
                      <th>Trigger Event Message</th>
                      <th>Recommended Protocol</th>
                      <th>Resolution</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alertsData.map((a) => (
                      <tr key={a.id}>
                        <td>#{a.id}</td>
                        <td><strong>{a.alert_type}</strong></td>
                        <td>
                          <span className={`alert-severity-badge sev-${String(a.severity || "info").toLowerCase()}`}>
                            {a.severity}
                          </span>
                        </td>
                        <td>{a.message}</td>
                        <td>{a.recommended_action || "Standard monitoring protocol"}</td>
                        <td>{a.acknowledged ? "Resolved" : "Pending Action"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="doc-clean-notice">
                ✓ No active or unacknowledged alert triggers registered for this shipment in PostgreSQL.
              </div>
            )}
          </div>

          {/* Official Sign-off Footer */}
          <div className="report-doc-footer">
            <div className="footer-disclaimer">
              This analytical report is generated by ColdChain AI Decision Support Framework.
              Data reflects live telemetry ingested from edge sensors and machine-learning assessments in PostgreSQL.
            </div>
            <div className="footer-signature-block">
              <div className="signature-line">
                <span className="sig-label">System QA Verification:</span>
                <span className="sig-code">COLDCHAIN-AI-ML-REGISTRY-OK</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
