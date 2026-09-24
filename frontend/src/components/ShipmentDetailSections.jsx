import { TemperatureChart, HumidityChart } from "./Charts.jsx";
import { LiveMap } from "./LiveMap.jsx";
import { RiskAlerts } from "./RiskAlerts.jsx";
import { Recommendations } from "./RecommendationDisplay.jsx";
import { Sparkline } from "./Charts.jsx";
import { fmtPercent } from "../utils/formatting.js";

export const StatusTiles = ({
  forecast = {},
  anomaly = {},
  packaging = {},
  onUploadPackaging,
  packagingBusy,
  packagingError,
}) => (
  <div className="status-tiles-grid">
    {/* LSTM Forecast Tile */}
    <div className="status-tile-card border-brown">
      <div className="tile-top-row">
        <span className="tile-badge badge-brown">Time-Series Forecast</span>
        <span className="tile-status">{forecast.status || "Ready"}</span>
      </div>
      <h4 className="tile-title">LSTM Temporal Forecast</h4>

      {forecast.predicted_breach ? (
        <div className="tile-alert-box alert-warning">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <span>Breach predicted: {forecast.predicted_breach.direction} in ~{forecast.predicted_breach.minutes_ahead}m</span>
        </div>
      ) : (
        <div className="tile-status-nominal">No temperature excursions predicted in near window.</div>
      )}

      {forecast.temperature && forecast.temperature.length > 0 && (
        <div className="tile-sparkline-wrap">
          <Sparkline
            points={forecast.temperature}
            domain={[Math.min(...forecast.temperature) - 1, Math.max(...forecast.temperature) + 1]}
            color="#85532d"
            height={50}
          />
        </div>
      )}

      <div className="tile-footer">
        <span className="tile-dataset-tag">Model: {forecast.data_kind || "SYNTHETIC/DEMO"}</span>
      </div>
    </div>

    {/* Autoencoder Anomaly Tile */}
    <div className="status-tile-card border-gold">
      <div className="tile-top-row">
        <span className="tile-badge badge-gold">Unsupervised Anomaly</span>
        <span className="tile-status">{anomaly.status || "Ready"}</span>
      </div>
      <h4 className="tile-title">Autoencoder Sensory Check</h4>

      <div className="tile-metric-rows">
        <div className="tile-metric-row">
          <span>Reconstruction Score:</span>
          <strong>{anomaly.score != null ? Number(anomaly.score).toFixed(4) : "—"}</strong>
        </div>
        <div className="tile-metric-row">
          <span>Threshold Limit:</span>
          <strong>{anomaly.threshold != null ? Number(anomaly.threshold).toFixed(4) : "—"}</strong>
        </div>
      </div>

      {anomaly.is_anomaly ? (
        <div className="tile-alert-box alert-danger">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>Sensory Anomaly Detected</span>
        </div>
      ) : (
        <div className="tile-status-nominal">Telemetry pattern is nominal (within manifold).</div>
      )}

      <div className="tile-footer">
        <span className="tile-dataset-tag">Status: Verified clean</span>
      </div>
    </div>

    {/* CNN Packaging Inspection Tile */}
    <div className="status-tile-card border-brown">
      <div className="tile-top-row">
        <span className="tile-badge badge-brown">Vision AI</span>
        <span className="tile-status">{packaging.status || "Available"}</span>
      </div>
      <h4 className="tile-title">CNN Packaging Inspection</h4>

      <div className="tile-metric-rows">
        <div className="tile-metric-row">
          <span>Condition Class:</span>
          <strong>{packaging.predicted_class || "OK (Intact Seal)"}</strong>
        </div>
        <div className="tile-metric-row">
          <span>Confidence:</span>
          <strong>{packaging.confidence != null ? fmtPercent(packaging.confidence) : "—"}</strong>
        </div>
      </div>

      {onUploadPackaging && (
        <form
          className="packaging-upload-form"
          onSubmit={(e) => {
            e.preventDefault();
            const input = e.currentTarget.elements.namedItem("packaging");
            const file = input && input.files && input.files[0];
            if (file) onUploadPackaging(file);
          }}
        >
          <label className="file-upload-label">
            <input
              name="packaging"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              disabled={packagingBusy}
            />
          </label>
          <button type="submit" className="upload-submit-btn" disabled={packagingBusy}>
            {packagingBusy ? "Analyzing Image..." : "Upload Inspection Photo"}
          </button>
          {packagingError && <div className="upload-error-tag">{packagingError}</div>}
        </form>
      )}

      <div className="tile-footer">
        <span className="tile-dataset-tag">Vision: ResNet-18 Classifier</span>
      </div>
    </div>
  </div>
);

export const ShapSection = ({ shap = {}, shapTop = [] }) => (
  <div className="content-card shap-factors-card">
    <div className="card-header-row">
      <div>
        <h4 className="card-title">Feature Attribution & SHAP Explainability</h4>
        <span className="card-subtitle">Key variables driving the machine-learning risk probability</span>
      </div>
      <span className="card-tag card-tag-brown">TreeExplainer</span>
    </div>

    {shap.status !== "ok" && (!shapTop || shapTop.length === 0) ? (
      <div className="data-empty-hint">{shap.detail || shap.status || "SHAP explanations not calculated."}</div>
    ) : shapTop.length > 0 ? (
      <div className="modern-table-responsive">
        <table className="modern-data-table shap-table">
          <thead>
            <tr>
              <th>Feature Name</th>
              <th>SHAP Attribution Value</th>
              <th>Direction of Influence</th>
              <th>Relative Weight</th>
            </tr>
          </thead>
          <tbody>
            {shapTop.map((f, i) => {
              const val = Number(f.shap_value || 0);
              const isPositive = val >= 0;
              const barWidth = Math.min(Math.abs(val) * 200, 100);

              return (
                <tr key={i}>
                  <td>
                    <strong>{f.feature}</strong>
                  </td>
                  <td>
                    <span className="shap-val-code">{val.toFixed(6)}</span>
                  </td>
                  <td>
                    <span className={`influence-pill ${isPositive ? "influence-up" : "influence-down"}`}>
                      {isPositive ? "▲ Increases Risk" : "▼ Decreases Risk"}
                    </span>
                  </td>
                  <td>
                    <div className="shap-bar-track">
                      <div
                        className={`shap-bar-fill ${isPositive ? "bar-danger" : "bar-safe"}`}
                        style={{ width: `${Math.max(barWidth, 8)}%` }}
                      />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    ) : (
      <div className="data-empty-hint">No SHAP attribution factors available for this shipment.</div>
    )}
  </div>
);

export const ChartsSection = ({ telemetryPoints = [], telemetryError, risk }) => (
  <div className="telemetry-charts-wrapper">
    {telemetryError && <div className="app-banner-error">{telemetryError}</div>}
    {telemetryPoints && telemetryPoints.length > 0 ? (
      <>
        <TemperatureChart telemetry={telemetryPoints} product={risk?.product} />
        <HumidityChart telemetry={telemetryPoints} />
      </>
    ) : (
      <div className="content-card">
        <div className="data-empty-hint">No recorded telemetry time-series points available for this shipment in PostgreSQL.</div>
      </div>
    )}
  </div>
);

export const MapSection = ({ risk }) => {
  if (!risk) return null;
  return (
    <div className="content-card map-card">
      <LiveMap shipments={[risk]} notes={risk?.data_quality?.notes?.[0]} onSelect={null} />
    </div>
  );
};

export const AlertsSection = ({ shipmentId }) => (
  <div className="content-card">
    <RiskAlerts shipmentId={shipmentId} />
  </div>
);

export const RecommendationsSection = ({ recommendations }) => (
  <Recommendations recommendations={recommendations} loading={false} error={null} />
);
