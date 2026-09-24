import { riskColor } from "../utils/formatting.js";

const SummaryCard = ({ title, value, subtitle, color, icon, badge, onClick }) => (
  <div
    className={`summary-card ${onClick ? "summary-card-clickable" : ""}`}
    onClick={onClick}
    role={onClick ? "button" : undefined}
    tabIndex={onClick ? 0 : undefined}
  >
    <div className="summary-card-top">
      <div className="summary-title-group">
        <span className="summary-card-title">{title}</span>
        {badge && <span className="summary-card-badge">{badge}</span>}
      </div>
      <div className="summary-card-icon-wrap" style={{ color: color, backgroundColor: `${color}15` }}>
        {icon}
      </div>
    </div>

    <div className="summary-card-body">
      <div className="summary-value">
        {value != null ? value : "—"}
      </div>
      {subtitle && <div className="summary-subtitle">{subtitle}</div>}
    </div>

    <div className="summary-card-indicator" style={{ backgroundColor: color }} />
  </div>
);

export const SummaryCards = ({
  summary,
  avgRiskScore,
  onTotalShipments,
  onActiveShipments,
  onHighRisk,
  onActiveAlerts,
  onMLAvailable,
}) => {
  if (!summary) {
    return (
      <div className="summary-grid">
        <div className="summary-loading-placeholder">Loading fleet summary from database...</div>
      </div>
    );
  }

  const breakdown = summary.risk_breakdown || {};
  const highRiskCount = summary.high_or_critical_risk ?? ((breakdown.HIGH || 0) + (breakdown.CRITICAL || 0));

  // Compute percentage from existing average risk score
  const formattedAvgRisk = avgRiskScore != null 
    ? `${(avgRiskScore * 100).toFixed(1)}%` 
    : "—";

  return (
    <div className="summary-grid">
      <SummaryCard
        title="Total Shipments"
        value={summary.total_shipments}
        subtitle="All registered consignments"
        color="#85532d"
        badge="Database"
        icon={(
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M1 3h15v13H1z" />
            <path d="M16 8h4l3 3v5h-7V8z" />
            <circle cx="5.5" cy="18.5" r="2.5" />
            <circle cx="18.5" cy="18.5" r="2.5" />
          </svg>
        )}
        onClick={onTotalShipments}
      />

      <SummaryCard
        title="Active Shipments"
        value={summary.active_shipments}
        subtitle={`${summary.active_statuses?.join(", ") || "Active transit"}`}
        color="#b8860b"
        badge="In Transit"
        icon={(
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
        )}
        onClick={onActiveShipments}
      />

      <SummaryCard
        title="High / Critical Risk"
        value={highRiskCount}
        subtitle={`${breakdown.HIGH || 0} HIGH • ${breakdown.CRITICAL || 0} CRITICAL`}
        color="#dc2626"
        badge={highRiskCount > 0 ? "Requires Attention" : "Optimal"}
        icon={(
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        )}
        onClick={onHighRisk}
      />

      <SummaryCard
        title="Average Risk Score"
        value={formattedAvgRisk}
        subtitle="Computed from assessed shipments"
        color={avgRiskScore != null && avgRiskScore > 0.4 ? "#d97706" : "#059669"}
        badge="Mean Index"
        icon={(
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
          </svg>
        )}
      />

      <SummaryCard
        title="Active Alerts"
        value={summary.active_alerts}
        subtitle="Unacknowledged triggers"
        color="#d97706"
        badge={summary.active_alerts > 0 ? "Active" : "Clear"}
        icon={(
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
        )}
        onClick={onActiveAlerts}
      />

      <SummaryCard
        title="ML Engine Status"
        value={`${summary.ml_available?.length || 0} Models`}
        subtitle={
          (summary.ml_unavailable?.length || 0) > 0
            ? `${summary.ml_unavailable.length} offline`
            : "All models online"
        }
        color="#85532d"
        badge="Online"
        icon={(
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
            <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
            <line x1="6" y1="6" x2="6.01" y2="6" />
            <line x1="6" y1="18" x2="6.01" y2="18" />
          </svg>
        )}
        onClick={onMLAvailable}
      />
    </div>
  );
};

export const StatusLegend = ({ summary }) => {
  if (!summary || !summary.notes) return null;

  return (
    <div className="status-legend-bar">
      <div className="legend-label">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
        <span>Live System Diagnostics:</span>
      </div>
      <div className="legend-items">
        {summary.notes.map((n, i) => (
          <span key={i} className="legend-pill">
            {n}
          </span>
        ))}
      </div>
    </div>
  );
};