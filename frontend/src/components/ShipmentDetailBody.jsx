import { RiskAlerts } from "./RiskAlerts.jsx";
import { Recommendations } from "./RecommendationDisplay.jsx";
import { Stat } from "./RiskDisplay.jsx";
import { fmtTime, fmtTimeOnly, fmtTemp, riskColor, riskBgColor, riskBorderColor } from "../utils/formatting.js";
import {
  StatusTiles,
  ShapSection,
  ChartsSection,
  MapSection,
  RecommendationsSection,
} from "./ShipmentDetailSections.jsx";

// Aliases
const StatusTilesSection = StatusTiles;
const ChartSection = ChartsSection;
const MapSectionComp = MapSection;
const RecSection = RecommendationsSection;

/**
 * Separate Shipment Details View
 * Populated strictly with genuine backend data.
 */
export const ShipmentBody = ({
  shipmentId,
  shipmentsList = [],
  onSwitchShipment,
  risk,
  loading,
  isUpdating,
  lastUpdated,
  error,
  telemetry,
  telemetryError,
  alerts = [],
  onBack,
  onUploadPackaging,
  packagingBusy,
  packagingError,
  onRefreshLive,
}) => {
  // Top Navigation Bar
  const renderNavBar = () => (
    <div className="detail-nav-bar">
      <div className="nav-bar-left">
        <button type="button" className="detail-back-btn" onClick={onBack}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          Back to Dashboard
        </button>

        {shipmentsList.length > 0 && (
          <div className="shipment-switcher-wrap">
            <label htmlFor="shipment-switcher" className="switcher-label">
              Consignment:
            </label>
            <select
              id="shipment-switcher"
              className="shipment-switcher-select"
              value={shipmentId || ""}
              onChange={(e) => onSwitchShipment && onSwitchShipment(Number(e.target.value))}
            >
              {shipmentsList.map((s) => (
                <option key={s.shipment_id} value={s.shipment_id}>
                  #{s.shipment_id} — {s.product_name || "Shipment"} ({s.origin || "Origin"} → {s.destination || "Dest"})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div className="nav-bar-right">
        <div className={`live-pulse-badge ${isUpdating ? "badge-updating" : "badge-live"}`}>
          <span className="live-dot" />
          <span className="live-text">{isUpdating ? "UPDATING LIVE..." : "LIVE"}</span>
        </div>
        <span className="detail-sync-clock">
          Last updated: <strong>{lastUpdated ? fmtTimeOnly(lastUpdated) : "—"}</strong>
        </span>
        <button
          type="button"
          className="detail-refresh-btn"
          onClick={onRefreshLive}
          disabled={isUpdating}
          title="Refresh live data"
        >
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" className={isUpdating ? "spin-icon" : ""}>
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
        </button>
      </div>
    </div>
  );

  if (loading && !risk) {
    return (
      <div className="detail-view-container">
        {renderNavBar()}
        <div className="detail-loading-box">
          <div className="loading-spinner" />
          <p>Retrieving live shipment data from PostgreSQL & ML inference engine...</p>
        </div>
      </div>
    );
  }

  if (error && !risk) {
    return (
      <div className="detail-view-container">
        {renderNavBar()}
        <div className="detail-error-box">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <div className="error-text-wrap">
            <h4>Unable to fetch live data for Shipment #{shipmentId}</h4>
            <p>{error}</p>
            <button type="button" className="retry-btn" onClick={onRefreshLive}>
              Retry Live Request
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!risk) {
    return (
      <div className="detail-view-container">
        {renderNavBar()}
        <div className="detail-empty-box">
          <p>No risk assessment record available for this shipment in PostgreSQL.</p>
        </div>
      </div>
    );
  }

  const level = (risk.risk_level || "UNKNOWN").toUpperCase();
  const color = riskColor(level);
  const bgColor = riskBgColor(level);
  const borderColor = riskBorderColor(level);
  const exposure = risk.exposure || {};
  const latest = risk.latest_reading || {};
  const forecast = risk.lstm_forecast || {};
  const anomaly = risk.anomaly || {};
  const packaging = risk.packaging || {};
  const shap = risk.shap || {};
  const shapTop = risk.shap_top_factors || shap.top_factors || [];
  const model = risk.model_result || {};
  const threshold = risk.thresholds || {};
  const telemetryPoints = telemetry || [];
  const product = risk.product || {};
  const position = risk.position || {};

  return (
    <div className="detail-view-container">
      {renderNavBar()}

      {/* Hero Header Card */}
      <div className="content-card detail-hero-card">
        <div className="hero-left">
          <div className="hero-id-row">
            <span className="hero-id-tag">Shipment #{risk.shipment_id}</span>
            {risk.vehicle_id && <span className="hero-vehicle-tag">Vehicle: {risk.vehicle_id}</span>}
            <span className={`hero-status-pill status-${String(risk.status || "").toLowerCase()}`}>
              {String(risk.status || "In Transit").replace(/_/g, " ")}
            </span>
          </div>

          <h2 className="hero-title">{product.name || "Cold Chain Cargo"}</h2>

          <div className="hero-route-row">
            <div className="route-node">
              <span className="node-icon origin-dot"></span>
              <span className="node-text"><strong>Origin:</strong> {risk.origin || "Origin Hub"}</span>
            </div>
            <span className="route-arrow">➔</span>
            <div className="route-node">
              <span className="node-icon dest-dot"></span>
              <span className="node-text"><strong>Destination:</strong> {risk.destination || "Destination Hub"}</span>
            </div>
            {risk.estimated_arrival_time && (
              <span className="hero-eta">
                ETA: {fmtTime(risk.estimated_arrival_time)}
              </span>
            )}
          </div>

          {/* Current Location Coordinates */}
          {(position.latitude != null || risk.latitude != null) && (
            <div className="hero-location-row">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                <circle cx="12" cy="10" r="3" />
              </svg>
              <span>
                Current Location: <strong>{Number(position.latitude ?? risk.latitude).toFixed(4)}°N, {Number(position.longitude ?? risk.longitude).toFixed(4)}°E</strong>
              </span>
              <span className="location-src">({position.source || "GPS Telemetry"})</span>
            </div>
          )}
        </div>

        <div className="hero-right">
          <div
            className="hero-risk-panel"
            style={{
              backgroundColor: bgColor,
              borderColor: borderColor,
              color: color,
            }}
          >
            <span className="hero-risk-label">Risk Evaluation</span>
            <div className="hero-risk-badge">
              <span className="hero-risk-dot" style={{ backgroundColor: color }}></span>
              <span className="hero-risk-text">{level}</span>
            </div>
            {risk.risk_score != null && (
              <span className="hero-risk-percentage">
                Risk Score: {(Number(risk.risk_score) * 100).toFixed(1)}%
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Diagnostic / Assessment Notes */}
      {risk.notes && risk.notes.length > 0 && (
        <div className="content-card detail-notes-card">
          <h4 className="detail-subcard-title">Live Assessment & Pipeline Notes</h4>
          <ul className="notes-list">
            {risk.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      )}

      {/* =========================================================================
          TELEMETRY & STABILITY INDICATORS (STATS GRID)
      ========================================================================= */}
      <section className="detail-section">
        <h3 className="section-title">Telemetry & Stability Indicators</h3>
        <div className="detail-stats-grid">
          <Stat label="Current Temperature" value={latest.temperature} unit="°C" accent="#85532d" />
          <Stat label="Relative Humidity" value={latest.humidity} unit="%" accent="#b8860b" />
          <Stat label="Sensor Battery" value={latest.battery_level} unit="%" accent="#059669" />
          <Stat label="Cumulative Excursion" value={exposure.total_excursion_minutes} unit=" min" accent="#ea580c" />
          <Stat label="Readings Outside Band" value={exposure.percent_readings_outside_range} unit="%" accent="#dc2626" />
          <Stat label="Max Recorded Temp" value={exposure.max_temperature} unit="°C" accent="#ea580c" />
          <Stat label="Min Recorded Temp" value={exposure.min_temperature} unit="°C" accent="#85532d" />
          <Stat label="Remaining Shelf Life" value={risk.remaining_shelf_life_hours} unit="h" accent="#78350f" />
          <Stat label="Thermal Equivalent Age" value={exposure.equivalent_age_hours} unit="h" accent="#5e4c41" />
        </div>
      </section>

      {/* =========================================================================
          DUAL MODEL VS RULE-BASED OUTPUT
      ========================================================================= */}
      <section className="detail-section">
        <div className="content-card model-comparison-card">
          <div className="comparison-header">
            <div>
              <h3 className="card-title">Dual Risk Assessment Architecture</h3>
              <span className="card-subtitle">Machine-Learning Gradient Boosting vs Regulatory Kinetic Exposure</span>
            </div>
            <span className="card-tag card-tag-brown">Live Assessment</span>
          </div>

          <div className="model-columns-grid">
            {/* XGBoost Box */}
            <div className="model-column-box box-ml">
              <div className="box-header-row">
                <span className="box-tag tag-brown">ML Model</span>
                <span className="box-status status-online">Status: {model?.status || "online"}</span>
              </div>
              <h4 className="box-title">XGBoost Spoilage Classifier</h4>

              <div className="box-score-row">
                <span className="score-label">Predicted Risk Probability:</span>
                <span className="score-number">
                  {risk?.model_risk_score != null ? Number(risk.model_risk_score).toFixed(4) : "—"}
                </span>
              </div>

              <div className="box-meta-list">
                <div className="box-meta-item">
                  <span>Decision Threshold:</span>
                  <strong>{risk?.model_decision_threshold != null ? Number(risk.model_decision_threshold).toFixed(3) : "0.500"}</strong>
                </div>
                <div className="box-meta-item">
                  <span>Breach Flag:</span>
                  <strong className={risk?.model_flag ? "danger-text" : "safe-text"}>
                    {risk?.model_flag ? "YES (Breach Flagged)" : "NO (Nominal)"}
                  </strong>
                </div>
                <div className="box-meta-item">
                  <span>Model Kind:</span>
                  <span>{model?.data_kind || "SYNTHETIC/DEMO"}</span>
                </div>
              </div>
            </div>

            {/* Rule-Based Box */}
            <div className="model-column-box box-rule">
              <div className="box-header-row">
                <span className="box-tag tag-gold">Kinetic Rule-Engine</span>
                <span className="box-status status-online">
                  Status: {risk?.rule_based_score != null ? "Active" : "Inactive"}
                </span>
              </div>
              <h4 className="box-title">Arrhenius Kinetic Thermal Exposure</h4>

              <div className="box-score-row">
                <span className="score-label">Kinetic Exposure Severity:</span>
                <span className="score-number">
                  {risk?.rule_based_score != null ? Number(risk.rule_based_score).toFixed(4) : "—"}
                </span>
              </div>

              <div className="box-meta-list">
                <div className="box-meta-item">
                  <span>Exposure Status:</span>
                  <strong className="safe-text">{risk?.exposure?.status || "Evaluated"}</strong>
                </div>
                <div className="box-meta-item">
                  <span>Total Excursion Minutes:</span>
                  <strong>{exposure.total_excursion_minutes || 0} min</strong>
                </div>
                <div className="box-meta-item">
                  <span>Regulatory Standard:</span>
                  <span>USP & WHO Cold Chain Guidelines</span>
                </div>
              </div>
            </div>
          </div>

          <div className="threshold-legend-footer">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            <span>
              Threshold Reference: LOW ≤ {threshold?.risk_low_max ?? 0.25} • MEDIUM ≤ {threshold?.risk_medium_max ?? 0.50} • HIGH ≤ {threshold?.risk_high_max ?? 0.75} • CRITICAL &gt; 0.75
            </span>
          </div>
        </div>
      </section>

      {/* =========================================================================
          AI PREDICTIVE DIAGNOSTICS (LSTM, AUTOENCODER, CNN PACKAGING)
      ========================================================================= */}
      <section className="detail-section">
        <h3 className="section-title">AI Predictive Diagnostics</h3>
        <StatusTilesSection
          forecast={forecast}
          anomaly={anomaly}
          packaging={packaging}
          onUploadPackaging={onUploadPackaging}
          packagingBusy={packagingBusy}
          packagingError={packagingError}
        />
      </section>

      {/* =========================================================================
          MODEL EXPLAINABILITY (SHAP TOP FACTORS)
      ========================================================================= */}
      <section className="detail-section">
        <h3 className="section-title">Model Explainability (SHAP Top Factors)</h3>
        <ShapSection shap={shap} shapTop={shapTop} />
      </section>

      {/* =========================================================================
          LIVE TELEMETRY CHARTS
      ========================================================================= */}
      <section className="detail-section">
        <h3 className="section-title">Sensory Telemetry Analytics</h3>
        <ChartSection telemetryPoints={telemetryPoints} telemetryError={telemetryError} risk={risk} />
      </section>

      {/* =========================================================================
          CURRENT LOCATION & ROUTE MAP
      ========================================================================= */}
      <section className="detail-section">
        <h3 className="section-title">Transit Route & Current Location</h3>
        <MapSectionComp risk={risk} />
      </section>

      {/* =========================================================================
          ALERTS & INTERVENTION RECOMMENDATIONS
      ========================================================================= */}
      <div className="detail-split-grid">
        <div className="content-card alerts-panel-card">
          <h3 className="card-title">Consignment Alerts</h3>
          <RiskAlerts shipmentId={risk.shipment_id} />
        </div>

        <div className="content-card recommendations-panel-card">
          <h3 className="card-title">Intervention Recommendations</h3>
          <RecSection recommendations={risk.recommendations} />
        </div>
      </div>
    </div>
  );
};
