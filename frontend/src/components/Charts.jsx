import { fmtTemp, fmtTime } from "../utils/formatting.js";

/**
 * Modern SVG sparkline for mini-trends using genuine data points
 */
export const Sparkline = ({ points, domain = [0, 1], color = "#85532d", height = 50 }) => {
  if (!points || points.length === 0) {
    return <div className="chart-empty-msg">No telemetry points</div>;
  }
  const width = 180;
  const [dmin, dmax] = domain;
  const span = Math.max(dmax - dmin, 1e-6);
  const y = (v) => height - ((Number(v) - dmin) / span) * (height - 8) - 4;
  const x = (i) => (i / Math.max(points.length - 1, 1)) * width;
  const path = points.map((v, i) => `${x(i)},${y(v)}`).join(" ");

  return (
    <svg width={width} height={height} className="modern-sparkline" viewBox={`0 0 ${width} ${height}`}>
      <polyline points={path} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

export const TemperatureChart = ({ telemetry = [], product }) => {
  if (!telemetry || telemetry.length === 0) {
    return (
      <div className="chart-card-box">
        <div className="chart-title-bar">
          <div>
            <h3 className="chart-heading">Temperature Telemetry History</h3>
            <span className="chart-subheading">Live sensor readings from edge IoT tracker</span>
          </div>
        </div>
        <div className="chart-empty-state">
          No live telemetry readings recorded for this shipment in PostgreSQL.
        </div>
      </div>
    );
  }

  const temps = telemetry.map((t) => Number(t.temperature)).filter((v) => !Number.isNaN(v));
  if (temps.length === 0) {
    return (
      <div className="chart-card-box">
        <div className="chart-empty-state">Telemetry records exist but contain no valid temperature values.</div>
      </div>
    );
  }

  const tmax = Math.max(...temps);
  const tmin = Math.min(...temps);
  const hi = product?.maximum_temperature ? Number(product.maximum_temperature) : null;
  const lo = product?.minimum_temperature ? Number(product.minimum_temperature) : null;

  const minBound = lo != null ? Math.min(lo, tmin) : tmin;
  const maxBound = hi != null ? Math.max(hi, tmax) : tmax;
  const domain = [Math.floor(minBound - 1), Math.ceil(maxBound + 1)];

  const width = 720;
  const height = 220;
  const padLeft = 55;
  const padBottom = 35;
  const padTop = 20;
  const padRight = 20;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const x = (i) => padLeft + (i / Math.max(telemetry.length - 1, 1)) * plotW;
  const y = (v) => padTop + (1 - (Number(v) - domain[0]) / Math.max(domain[1] - domain[0], 1e-6)) * plotH;

  const linePath = telemetry.map((t, i) => `L ${x(i).toFixed(1)} ${y(t.temperature).toFixed(1)}`).join(" ");
  const fullPath = `M ${padLeft} ${y(temps[0]).toFixed(1)} ${linePath}`;
  const areaPath = `${fullPath} L ${x(telemetry.length - 1).toFixed(1)} ${padTop + plotH} L ${padLeft} ${padTop + plotH} Z`;

  const excursionPoints = telemetry.filter(
    (t) => (hi != null && t.temperature > hi) || (lo != null && t.temperature < lo)
  );

  const lastReading = telemetry[telemetry.length - 1];

  return (
    <div className="chart-card-box">
      <div className="chart-title-bar">
        <div>
          <h3 className="chart-heading">Temperature Kinetic History</h3>
          <span className="chart-subheading">Continuous live thermal telemetry vs product specifications</span>
        </div>
        <div className="chart-meta-tags">
          <span className="meta-tag meta-tag-latest">
            Latest: <strong>{fmtTemp(lastReading?.temperature)}</strong>
          </span>
          {lastReading && (
            <span className="meta-tag">
              Time: {fmtTime(lastReading.timestamp)}
            </span>
          )}
          <span className="meta-tag">
            Range: {fmtTemp(tmin)} – {fmtTemp(tmax)}
          </span>
        </div>
      </div>

      <div className="chart-svg-container">
        <svg viewBox={`0 0 ${width} ${height}`} className="responsive-chart-svg">
          <defs>
            <linearGradient id="tempWarmGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#85532d" stopOpacity="0.22" />
              <stop offset="100%" stopColor="#85532d" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
            const yy = padTop + frac * plotH;
            const val = domain[1] - frac * (domain[1] - domain[0]);
            return (
              <g key={frac}>
                <line x1={padLeft} y1={yy} x2={width - padRight} y2={yy} stroke="#e8e0d6" strokeWidth="1" strokeDasharray="3 3" />
                <text x={padLeft - 10} y={yy + 4} textAnchor="end" fontSize="11" fill="#8e7d72" fontWeight="500">
                  {val.toFixed(1)}°C
                </text>
              </g>
            );
          })}

          {/* Allowed product range band */}
          {lo != null && hi != null && (
            <g className="safe-range-band">
              <rect
                x={padLeft}
                y={y(hi)}
                width={plotW}
                height={Math.max(y(lo) - y(hi), 0)}
                fill="#ecfdf5"
                fillOpacity="0.75"
              />
              <line
                x1={padLeft}
                y1={y(hi)}
                x2={width - padRight}
                y2={y(hi)}
                stroke="#059669"
                strokeWidth="1.5"
                strokeDasharray="5 3"
              />
              <line
                x1={padLeft}
                y1={y(lo)}
                x2={width - padRight}
                y2={y(lo)}
                stroke="#059669"
                strokeWidth="1.5"
                strokeDasharray="5 3"
              />
              <text x={width - padRight - 5} y={y(hi) - 4} textAnchor="end" fontSize="10" fill="#059669" fontWeight="600">
                Max Safe ({hi}°C)
              </text>
              <text x={width - padRight - 5} y={y(lo) + 12} textAnchor="end" fontSize="10" fill="#059669" fontWeight="600">
                Min Safe ({lo}°C)
              </text>
            </g>
          )}

          {/* Gradient Area fill */}
          <path d={areaPath} fill="url(#tempWarmGradient)" />

          {/* Temperature trend line */}
          <path d={fullPath} fill="none" stroke="#85532d" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

          {/* Excursion breach points */}
          {excursionPoints.map((t, idx) => (
            <g key={idx}>
              <circle cx={x(telemetry.indexOf(t))} cy={y(t.temperature)} r="6" fill="#fecaca" />
              <circle cx={x(telemetry.indexOf(t))} cy={y(t.temperature)} r="3.5" fill="#dc2626" />
            </g>
          ))}

          {/* Time axis label */}
          <text x={padLeft + plotW / 2} y={height - 8} textAnchor="middle" fontSize="11" fill="#8e7d72" fontWeight="500">
            Telemetry Time Sequence ({telemetry.length} Logged Sensor Points)
          </text>
        </svg>
      </div>

      <div className="chart-legend-row">
        <div className="legend-item-chip">
          <span className="legend-pill-sample" style={{ backgroundColor: "#85532d" }}></span>
          <span>Actual Logged Temp (°C)</span>
        </div>
        {lo != null && hi != null && (
          <div className="legend-item-chip">
            <span className="legend-pill-sample" style={{ backgroundColor: "#059669" }}></span>
            <span>Permitted Range ({lo}°C to {hi}°C)</span>
          </div>
        )}
        {excursionPoints.length > 0 && (
          <div className="legend-item-chip danger-chip">
            <span className="legend-pill-sample" style={{ backgroundColor: "#dc2626" }}></span>
            <span>Recorded Excursions ({excursionPoints.length} events)</span>
          </div>
        )}
      </div>
    </div>
  );
};

export const HumidityChart = ({ telemetry = [] }) => {
  if (!telemetry || telemetry.length === 0) {
    return (
      <div className="chart-card-box">
        <div className="chart-title-bar">
          <div>
            <h3 className="chart-heading">Humidity Telemetry Profile</h3>
            <span className="chart-subheading">Ambient moisture level (%)</span>
          </div>
        </div>
        <div className="chart-empty-state">No live humidity readings recorded in database.</div>
      </div>
    );
  }

  const validHums = telemetry
    .map((t) => (t.humidity != null ? Number(t.humidity) : null))
    .filter((v) => v != null && !Number.isNaN(v));

  if (validHums.length === 0) {
    return (
      <div className="chart-card-box">
        <div className="chart-empty-state">Telemetry records exist but have no humidity values.</div>
      </div>
    );
  }

  const hmax = Math.max(...validHums, 90);
  const hmin = Math.min(...validHums, 20);
  const domain = [Math.max(0, Math.floor(hmin - 5)), Math.min(100, Math.ceil(hmax + 5))];

  const width = 720;
  const height = 180;
  const padLeft = 55;
  const padBottom = 35;
  const padTop = 15;
  const padRight = 20;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const x = (i) => padLeft + (i / Math.max(telemetry.length - 1, 1)) * plotW;
  const y = (v) => padTop + (1 - (Number(v) - domain[0]) / Math.max(domain[1] - domain[0], 1e-6)) * plotH;

  const linePath = telemetry.map((t, i) => `L ${x(i).toFixed(1)} ${y(t.humidity ?? 0).toFixed(1)}`).join(" ");
  const fullPath = `M ${padLeft} ${y(telemetry[0]?.humidity ?? 0).toFixed(1)} ${linePath}`;
  const areaPath = `${fullPath} L ${x(telemetry.length - 1).toFixed(1)} ${padTop + plotH} L ${padLeft} ${padTop + plotH} Z`;

  const lastReading = telemetry[telemetry.length - 1];

  return (
    <div className="chart-card-box">
      <div className="chart-title-bar">
        <div>
          <h3 className="chart-heading">Relative Humidity Monitor</h3>
          <span className="chart-subheading">Ambient moisture telemetry profile (%)</span>
        </div>
        <div className="chart-meta-tags">
          <span className="meta-tag meta-tag-latest">
            Latest: <strong>{lastReading?.humidity != null ? `${Number(lastReading.humidity).toFixed(1)}%` : "—"}</strong>
          </span>
          {lastReading && (
            <span className="meta-tag">
              Time: {fmtTime(lastReading.timestamp)}
            </span>
          )}
        </div>
      </div>

      <div className="chart-svg-container">
        <svg viewBox={`0 0 ${width} ${height}`} className="responsive-chart-svg">
          <defs>
            <linearGradient id="humGoldGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#b8860b" stopOpacity="0.2" />
              <stop offset="100%" stopColor="#b8860b" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {[0, 0.5, 1].map((frac) => {
            const yy = padTop + frac * plotH;
            const val = domain[1] - frac * (domain[1] - domain[0]);
            return (
              <g key={frac}>
                <line x1={padLeft} y1={yy} x2={width - padRight} y2={yy} stroke="#e8e0d6" strokeWidth="1" strokeDasharray="3 3" />
                <text x={padLeft - 10} y={yy + 4} textAnchor="end" fontSize="11" fill="#8e7d72" fontWeight="500">
                  {val.toFixed(0)}%
                </text>
              </g>
            );
          })}

          <path d={areaPath} fill="url(#humGoldGradient)" />
          <path d={fullPath} fill="none" stroke="#b8860b" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

          <text x={padLeft + plotW / 2} y={height - 8} textAnchor="middle" fontSize="11" fill="#8e7d72" fontWeight="500">
            Telemetry Time Sequence
          </text>
        </svg>
      </div>
    </div>
  );
};
