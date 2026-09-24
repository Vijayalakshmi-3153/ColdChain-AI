import { riskColor, riskBgColor, riskBorderColor } from "../utils/formatting.js";

/** Modern light theme Risk level badge */
export const RiskBadge = ({ level, score }) => {
  const normLevel = (level || "UNKNOWN").toUpperCase();
  const color = riskColor(normLevel);
  const bgColor = riskBgColor(normLevel);
  const borderColor = riskBorderColor(normLevel);

  return (
    <span
      className={`risk-badge-modern risk-${normLevel.toLowerCase()}`}
      style={{
        color: color,
        backgroundColor: bgColor,
        borderColor: borderColor,
      }}
    >
      <span className="risk-badge-dot" style={{ backgroundColor: color }}></span>
      <span className="risk-badge-text">{normLevel}</span>
      {score != null && (
        <span className="risk-badge-score">
          {(Number(score) * 100).toFixed(0)}%
        </span>
      )}
    </span>
  );
};

/** Stat metric card in detail view */
export const Stat = ({ label, value, unit = "", accent = "#85532d" }) => (
  <div className="stat-metric-card" style={{ borderTopColor: accent }}>
    <span className="stat-metric-label">{label}</span>
    <span className="stat-metric-value" style={{ color: accent }}>
      {value != null && !Number.isNaN(Number(value))
        ? `${Number(value).toFixed(unit ? 1 : 0)}${unit}`.trim()
        : "—"}
    </span>
  </div>
);

/** Sparkline graph for trends */
export const Sparkline = ({ points, domain = [0, 1], color = "#85532d", height = 50 }) => {
  if (!points || points.length === 0) return null;
  const width = 160;
  const [dmin, dmax] = domain;
  const span = Math.max(dmax - dmin, 1e-6);
  const y = (v) => height - ((Number(v) - dmin) / span) * (height - 6) - 3;
  const x = (i) => (i / Math.max(points.length - 1, 1)) * width;
  const path = points.map((v, i) => `${x(i)},${y(v)}`).join(" ");

  return (
    <svg width={width} height={height} className="mini-sparkline">
      <polyline points={path} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};
