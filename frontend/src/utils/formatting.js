import { format } from "date-fns";

/**
 * Risk-level helpers: colour + label chips.
 * Distinct professional risk colors:
 * LOW = green, MEDIUM = amber, HIGH = orange/red, CRITICAL = red
 */
export const RISK_COLORS = {
  LOW: "#059669",      // Green
  MEDIUM: "#d97706",   // Amber
  HIGH: "#ea580c",     // Orange/Red
  CRITICAL: "#dc2626", // Red
  UNKNOWN: "#786b62",  // Warm Muted Taupe
};

export const RISK_BG_COLORS = {
  LOW: "#ecfdf5",
  MEDIUM: "#fffbeb",
  HIGH: "#fff7ed",
  CRITICAL: "#fef2f2",
  UNKNOWN: "#f7f4ef",
};

export const RISK_BORDER_COLORS = {
  LOW: "#a7f3d0",
  MEDIUM: "#fde68a",
  HIGH: "#fed7aa",
  CRITICAL: "#fecaca",
  UNKNOWN: "#e8dfd5",
};

export const RISK_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"];

export const riskColor = (level) => RISK_COLORS[level] || RISK_COLORS.UNKNOWN;
export const riskBgColor = (level) => RISK_BG_COLORS[level] || RISK_BG_COLORS.UNKNOWN;
export const riskBorderColor = (level) => RISK_BORDER_COLORS[level] || RISK_BORDER_COLORS.UNKNOWN;

export const fmtTemp = (v, unit = "°C") =>
  v == null || Number.isNaN(Number(v)) ? "—" : `${Number(v).toFixed(1)}${unit}`;

export const fmtPercent = (v) => (v == null ? "—" : `${Number(v).toFixed(1)}%`);

export const fmtTime = (ts) => {
  if (!ts) return "—";
  try {
    return format(new Date(ts), "PPpp");
  } catch {
    return String(ts);
  }
};

export const fmtTimeOnly = (ts) => {
  if (!ts) return "—";
  try {
    return format(new Date(ts), "HH:mm:ss");
  } catch {
    return String(ts);
  }
};

export const fmtDistance = (ts) => {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    const diff = Math.round((Date.now() - d.getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    return `${Math.round(diff / 3600)}h ago`;
  } catch {
    return ts;
  }
};

export const exposureStatusColor = (status) => {
  switch (status) {
    case "critical":
      return "#dc2626";
    case "warning":
      return "#d97706";
    case "normal":
      return "#059669";
    case "no_data":
      return "#786b62";
    default:
      return "#786b62";
  }
};

export const capitalize = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "");
