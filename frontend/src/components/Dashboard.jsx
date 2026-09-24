import { useEffect, useState, useMemo, useCallback } from "react";
import axios from "axios";
import { SummaryCards, StatusLegend } from "./SummaryCards.jsx";
import { ShipmentTable } from "./ShipmentTable.jsx";
import { LiveMap } from "./LiveMap.jsx";
import { fmtTemp, fmtTimeOnly, riskColor } from "../utils/formatting.js";

const POLL_MS = 15000;

/**
 * Main Dashboard Page:
 * Focused purely on high-level operational overview:
 * - KPIs (Total, Active, High Risk, Average Risk Score, Active Alerts, ML Models)
 * - Fleet Temperature & Humidity Monitoring Summary
 * - Risk Level Distribution
 * - Live Shipment Map (actual coordinates)
 * - Recent Alerts
 * - Filterable Shipment Overview Table
 * Selecting a shipment navigates to the separate Shipment Details page.
 */
export const Dashboard = ({ onSelectShipment }) => {
  const [summary, setSummary] = useState(null);
  const [shipments, setShipments] = useState(null);
  const [mapData, setMapData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [shipmentFilter, setShipmentFilter] = useState("all");

  const fetchDashboardData = useCallback(async (isInitial = false) => {
    if (isInitial) setLoading(true);
    setIsUpdating(true);

    try {
      const [sRes, shRes, mRes] = await Promise.allSettled([
        axios.get("/api/dashboard/summary"),
        axios.get("/api/dashboard/shipments"),
        axios.get("/api/dashboard/map"),
      ]);

      let hasSuccess = false;

      if (sRes.status === "fulfilled") {
        setSummary(sRes.value.data);
        hasSuccess = true;
      }

      if (shRes.status === "fulfilled") {
        setShipments(shRes.value.data);
        hasSuccess = true;
      }

      if (mRes.status === "fulfilled") {
        setMapData(mRes.value.data);
        hasSuccess = true;
      }

      if (hasSuccess) {
        setError(null);
        setLastUpdated(new Date().toISOString());
      } else {
        const firstErr = [sRes, shRes, mRes].find((r) => r.status === "rejected");
        setError(firstErr?.reason?.message || "Unable to fetch live data from server");
      }
    } catch (err) {
      setError(err?.message || "Unable to fetch live data");
    } finally {
      setLoading(false);
      setIsUpdating(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData(true);
    const id = setInterval(() => {
      fetchDashboardData(false);
    }, POLL_MS);
    return () => clearInterval(id);
  }, [fetchDashboardData]);

  // Compute fleet telemetry & condition stats purely from existing shipment data
  const fleetMetrics = useMemo(() => {
    if (!shipments || shipments.length === 0) {
      return {
        avgRiskScore: null,
        avgTemp: null,
        minTemp: null,
        maxTemp: null,
        avgHumidity: null,
        excursionShipmentsCount: 0,
        statusCounts: {},
        riskCounts: { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 },
        recentAlertsList: [],
      };
    }

    const validRiskScores = shipments
      .map((s) => s.risk_score)
      .filter((v) => v != null && !Number.isNaN(Number(v)));

    const avgRiskScore = validRiskScores.length > 0
      ? validRiskScores.reduce((acc, cur) => acc + Number(cur), 0) / validRiskScores.length
      : null;

    const validTemps = shipments
      .map((s) => s.temperature)
      .filter((v) => v != null && !Number.isNaN(Number(v)));

    const avgTemp = validTemps.length > 0
      ? validTemps.reduce((acc, cur) => acc + Number(cur), 0) / validTemps.length
      : null;

    const minTemp = validTemps.length > 0 ? Math.min(...validTemps) : null;
    const maxTemp = validTemps.length > 0 ? Math.max(...validTemps) : null;

    const validHum = shipments
      .map((s) => s.humidity)
      .filter((v) => v != null && !Number.isNaN(Number(v)));

    const avgHumidity = validHum.length > 0
      ? validHum.reduce((acc, cur) => acc + Number(cur), 0) / validHum.length
      : null;

    const excursionShipmentsCount = shipments.filter(
      (s) =>
        (s.cumulative_excursion_minutes && s.cumulative_excursion_minutes > 0) ||
        s.exposure_status === "critical" ||
        s.exposure_status === "warning" ||
        (s.active_alerts && s.active_alerts > 0)
    ).length;

    const statusCounts = {};
    const riskCounts = { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 };

    shipments.forEach((s) => {
      const st = s.status || "Unknown";
      statusCounts[st] = (statusCounts[st] || 0) + 1;

      const rk = String(s.risk_level || "UNKNOWN").toUpperCase();
      if (rk in riskCounts) {
        riskCounts[rk] += 1;
      }
    });

    // Extract actual alerted shipments for the recent alerts feed
    const recentAlertsList = shipments
      .filter((s) => (s.active_alerts && s.active_alerts > 0) || s.risk_level === "CRITICAL" || s.risk_level === "HIGH")
      .map((s) => ({
        shipment_id: s.shipment_id,
        product_name: s.product_name || "Consignment",
        risk_level: s.risk_level,
        temperature: s.temperature,
        active_alerts: s.active_alerts || 1,
        status: s.status,
        last_updated: s.last_updated,
        message: s.cumulative_excursion_minutes > 0
          ? `Thermal excursion: ${s.cumulative_excursion_minutes} min out-of-band`
          : `${s.risk_level} risk evaluated for shipment #${s.shipment_id}`,
      }));

    return {
      avgRiskScore,
      avgTemp,
      minTemp,
      maxTemp,
      avgHumidity,
      excursionShipmentsCount,
      statusCounts,
      riskCounts,
      recentAlertsList,
    };
  }, [shipments]);

  const goToShipments = (filter = "all") => {
    setShipmentFilter(filter);
    setTimeout(() => {
      const section = document.getElementById("shipments-section");
      if (section) {
        section.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 100);
  };

  const goToSystemStatus = () => {
    const section = document.getElementById("system-status-section");
    if (section) {
      section.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  // Initial loading state
  if (loading && !summary && !shipments) {
    return (
      <div className="loading-state-container">
        <div className="loading-spinner" />
        <p className="loading-state-text">Connecting to ColdChain AI Live Backend & PostgreSQL...</p>
      </div>
    );
  }

  const totalEvaluated = shipments ? shipments.length : 0;
  const riskCounts = summary?.risk_breakdown || fleetMetrics.riskCounts;

  return (
    <div className="dashboard-container">
      {/* Live Operational Status Banner */}
      <div className="dashboard-live-bar">
        <div className="live-bar-left">
          <div className={`live-pulse-badge ${error ? "badge-offline" : isUpdating ? "badge-updating" : "badge-live"}`}>
            <span className="live-dot" />
            <span className="live-text">
              {error ? "OFFLINE" : isUpdating ? "UPDATING LIVE DATA..." : "LIVE MONITORING"}
            </span>
          </div>
          <span className="live-timestamp-text">
            Last updated: <strong>{lastUpdated ? fmtTimeOnly(lastUpdated) : "—"}</strong>
          </span>
        </div>

        <div className="live-bar-right">
          <button
            type="button"
            className="refresh-live-btn"
            onClick={() => fetchDashboardData(false)}
            disabled={isUpdating}
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" className={isUpdating ? "spin-icon" : ""}>
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
            {isUpdating ? "Refreshing..." : "Refresh Live Data"}
          </button>
        </div>
      </div>

      {/* Error state: Only shown if API is actually unavailable */}
      {error && (
        <div className="app-banner-error">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <div className="banner-error-content">
            <strong>Unable to fetch live data</strong>
            <span> — {error}. Please ensure the backend API (port 8000) and PostgreSQL database are running.</span>
          </div>
        </div>
      )}

      {/* =========================================================
          SECTION 1: OVERVIEW KPI CARDS
      ========================================================= */}
      <section id="system-status-section" className="dashboard-section">
        <div className="section-header">
          <div>
            <h2 className="section-title">Operations Overview</h2>
            <p className="section-subtitle">Real-time status metrics and machine-learning diagnostic health</p>
          </div>
        </div>

        <SummaryCards
          summary={summary}
          avgRiskScore={fleetMetrics.avgRiskScore}
          onTotalShipments={() => goToShipments("all")}
          onActiveShipments={() => goToShipments("active")}
          onHighRisk={() => goToShipments("high-risk")}
          onActiveAlerts={() => goToSystemStatus()}
          onMLAvailable={() => goToSystemStatus()}
        />

        {summary && <StatusLegend summary={summary} />}
      </section>

      {/* =========================================================
          SECTION 2: FLEET MONITORING & RISK DISTRIBUTION HUB
      ========================================================= */}
      <section className="dashboard-section">
        <div className="section-grid-two-col">
          {/* Temperature & Humidity Monitoring Card */}
          <div className="content-card monitoring-card">
            <div className="card-header-row">
              <div>
                <h3 className="card-title">Temperature & Humidity Monitoring</h3>
                <span className="card-subtitle">Active sensor telemetry across transit fleet</span>
              </div>
              <span className="card-tag card-tag-brown">Live Sensors</span>
            </div>

            <div className="monitoring-stats-grid">
              <div className="metric-pill">
                <span className="metric-pill-label">Mean Fleet Temp</span>
                <span className="metric-pill-val accent-color">
                  {fmtTemp(fleetMetrics.avgTemp)}
                </span>
                <span className="metric-pill-sub">
                  Range: {fmtTemp(fleetMetrics.minTemp)} to {fmtTemp(fleetMetrics.maxTemp)}
                </span>
              </div>

              <div className="metric-pill">
                <span className="metric-pill-label">Mean Humidity</span>
                <span className="metric-pill-val gold-color">
                  {fleetMetrics.avgHumidity != null ? `${fleetMetrics.avgHumidity.toFixed(1)}%` : "—"}
                </span>
                <span className="metric-pill-sub">Ambient moisture control</span>
              </div>

              <div className="metric-pill">
                <span className="metric-pill-label">Excursions / Warning</span>
                <span className={`metric-pill-val ${fleetMetrics.excursionShipmentsCount > 0 ? "rose-color" : "green-color"}`}>
                  {fleetMetrics.excursionShipmentsCount}
                </span>
                <span className="metric-pill-sub">
                  {fleetMetrics.excursionShipmentsCount > 0 ? "Shipments breached limits" : "All within safe limits"}
                </span>
              </div>
            </div>

            {/* Shipment Status Breakdown Badges */}
            <div className="status-breakdown-row">
              <span className="breakdown-label">Shipment Status:</span>
              <div className="breakdown-pills">
                {Object.keys(fleetMetrics.statusCounts).length === 0 ? (
                  <span className="status-empty-text">No active shipments</span>
                ) : (
                  Object.entries(fleetMetrics.statusCounts).map(([statusName, count]) => (
                    <span key={statusName} className="status-count-chip">
                      <span className="chip-dot"></span>
                      <span className="chip-name">{statusName.replace(/_/g, " ")}</span>
                      <strong className="chip-count">{count}</strong>
                    </span>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Risk Distribution Card */}
          <div className="content-card risk-dist-card">
            <div className="card-header-row">
              <div>
                <h3 className="card-title">Risk Level Distribution</h3>
                <span className="card-subtitle">Predictive ML & rule-based risk classification</span>
              </div>
              <span className="card-tag card-tag-sand">All Shipments</span>
            </div>

            {/* Visual Segmented Bar */}
            <div className="risk-progress-bar-container">
              <div
                className="risk-bar-segment segment-low"
                style={{
                  width: totalEvaluated ? `${((riskCounts.LOW || 0) / totalEvaluated) * 100}%` : "25%",
                }}
                title={`LOW: ${riskCounts.LOW || 0}`}
              />
              <div
                className="risk-bar-segment segment-medium"
                style={{
                  width: totalEvaluated ? `${((riskCounts.MEDIUM || 0) / totalEvaluated) * 100}%` : "25%",
                }}
                title={`MEDIUM: ${riskCounts.MEDIUM || 0}`}
              />
              <div
                className="risk-bar-segment segment-high"
                style={{
                  width: totalEvaluated ? `${((riskCounts.HIGH || 0) / totalEvaluated) * 100}%` : "25%",
                }}
                title={`HIGH: ${riskCounts.HIGH || 0}`}
              />
              <div
                className="risk-bar-segment segment-critical"
                style={{
                  width: totalEvaluated ? `${((riskCounts.CRITICAL || 0) / totalEvaluated) * 100}%` : "25%",
                }}
                title={`CRITICAL: ${riskCounts.CRITICAL || 0}`}
              />
            </div>

            {/* Risk Legend Grid */}
            <div className="risk-legend-grid">
              <div className="risk-legend-item">
                <span className="legend-indicator dot-low"></span>
                <span className="legend-name">LOW</span>
                <strong className="legend-val">{riskCounts.LOW || 0}</strong>
              </div>
              <div className="risk-legend-item">
                <span className="legend-indicator dot-medium"></span>
                <span className="legend-name">MEDIUM</span>
                <strong className="legend-val">{riskCounts.MEDIUM || 0}</strong>
              </div>
              <div className="risk-legend-item">
                <span className="legend-indicator dot-high"></span>
                <span className="legend-name">HIGH</span>
                <strong className="legend-val">{riskCounts.HIGH || 0}</strong>
              </div>
              <div className="risk-legend-item">
                <span className="legend-indicator dot-critical"></span>
                <span className="legend-name">CRITICAL</span>
                <strong className="legend-val">{riskCounts.CRITICAL || 0}</strong>
              </div>
            </div>

            <div className="risk-card-footer">
              <span className="footer-info-text">
                Evaluated using XGBoost spoilage probability + continuous kinetic exposure
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================
          SECTION 3: LIVE SHIPMENT MAP
      ========================================================= */}
      <section className="dashboard-section">
        <div className="section-header">
          <div>
            <h2 className="section-title">Live Shipment Route & Geolocation Map</h2>
            <p className="section-subtitle">Real-time GPS vehicle positions and transit trajectory</p>
          </div>
        </div>

        <div className="content-card map-card">
          {mapData ? (
            <LiveMap
              shipments={mapData.shipments}
              notes={mapData.notes?.join("; ")}
              onSelect={(shipment) => onSelectShipment(shipment.shipment_id)}
            />
          ) : (
            <div className="data-empty-hint">Map data currently unavailable.</div>
          )}
        </div>
      </section>

      {/* =========================================================
          SECTION 4: RECENT ALERTS FEED
      ========================================================= */}
      {fleetMetrics.recentAlertsList.length > 0 && (
        <section className="dashboard-section">
          <div className="section-header">
            <div>
              <h2 className="section-title">Recent Critical Triggers & Alerts</h2>
              <p className="section-subtitle">Active alerts detected in the cold chain transit network</p>
            </div>
          </div>

          <div className="content-card recent-alerts-card">
            <div className="alerts-feed-grid">
              {fleetMetrics.recentAlertsList.slice(0, 4).map((alertItem) => (
                <div key={alertItem.shipment_id} className={`alert-feed-item alert-feed-${String(alertItem.risk_level).toLowerCase()}`}>
                  <div className="alert-feed-top">
                    <span className="alert-feed-id">Shipment #{alertItem.shipment_id}</span>
                    <span className="alert-feed-tag" style={{ color: riskColor(alertItem.risk_level) }}>
                      {alertItem.risk_level}
                    </span>
                  </div>
                  <div className="alert-feed-msg">{alertItem.message}</div>
                  <div className="alert-feed-footer">
                    <span>Temp: {fmtTemp(alertItem.temperature)}</span>
                    <button
                      type="button"
                      className="alert-inspect-link"
                      onClick={() => onSelectShipment(alertItem.shipment_id)}
                    >
                      Inspect →
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* =========================================================
          SECTION 5: SHIPMENT OVERVIEW DIRECTORY TABLE
      ========================================================= */}
      <section id="shipments-section" className="dashboard-section">
        <div className="section-header">
          <div>
            <h2 className="section-title">Shipment Overview Directory</h2>
            <p className="section-subtitle">Click any consignment to open its dedicated Shipment Details page</p>
          </div>
        </div>

        <div className="content-card table-card">
          <ShipmentTable
            shipments={shipments || []}
            onSelect={(shipment) => onSelectShipment(shipment.shipment_id)}
            loading={loading && !shipments}
            error={error}
            initialFilter={shipmentFilter}
          />
        </div>
      </section>
    </div>
  );
};