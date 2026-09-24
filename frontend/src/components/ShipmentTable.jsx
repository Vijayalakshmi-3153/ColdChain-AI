import { useState, useMemo } from "react";
import { fmtTemp, riskColor, riskBgColor, riskBorderColor } from "../utils/formatting.js";

const RISK_LABELS = {
  LOW: "LOW",
  MEDIUM: "MEDIUM",
  HIGH: "HIGH",
  CRITICAL: "CRITICAL",
  UNKNOWN: "UNKNOWN",
};

export const RiskBadge = ({ level, score }) => {
  const normLevel = (level || "UNKNOWN").toUpperCase();
  const label = RISK_LABELS[normLevel] || "UNKNOWN";
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
      title={score != null ? `Calculated risk score: ${Number(score).toFixed(3)}` : undefined}
    >
      <span className="risk-badge-dot" style={{ backgroundColor: color }}></span>
      <span className="risk-badge-text">{label}</span>
      {score != null && (
        <span className="risk-badge-score">
          {(Number(score) * 100).toFixed(0)}%
        </span>
      )}
    </span>
  );
};

export const ShipmentTable = ({
  shipments = [],
  onSelect,
  selectedId,
  loading,
  error,
  initialFilter = "all",
}) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState(initialFilter || "all");
  const [statusFilter, setStatusFilter] = useState("all");

  // Keep internal filter synchronized if parent changes initialFilter
  useMemo(() => {
    if (initialFilter) {
      setActiveFilter(initialFilter);
    }
  }, [initialFilter]);

  const filteredShipments = useMemo(() => {
    if (!shipments || !Array.isArray(shipments)) return [];

    return shipments.filter((s) => {
      // 1. Text Search across ID, Product, Origin, Destination, Vehicle
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesId = String(s.shipment_id || "").toLowerCase().includes(query);
        const matchesProduct = String(s.product_name || "").toLowerCase().includes(query);
        const matchesOrigin = String(s.origin || "").toLowerCase().includes(query);
        const matchesDest = String(s.destination || "").toLowerCase().includes(query);
        const matchesVehicle = String(s.vehicle_id || "").toLowerCase().includes(query);

        if (!matchesId && !matchesProduct && !matchesOrigin && !matchesDest && !matchesVehicle) {
          return false;
        }
      }

      // 2. Risk / Active Filter Tabs
      const status = String(s.status || "").toLowerCase();
      const risk = String(s.risk_level || "").toUpperCase();

      if (activeFilter === "active") {
        const isActive =
          status === "active" ||
          status === "in_transit" ||
          status === "in transit" ||
          status === "pending" ||
          status === "delayed";
        if (!isActive) return false;
      } else if (activeFilter === "low") {
        if (risk !== "LOW") return false;
      } else if (activeFilter === "medium") {
        if (risk !== "MEDIUM") return false;
      } else if (activeFilter === "high-risk") {
        if (risk !== "HIGH" && risk !== "CRITICAL") return false;
      }

      // 3. Status Dropdown Filter
      if (statusFilter !== "all") {
        if (status !== statusFilter.toLowerCase()) return false;
      }

      return true;
    });
  }, [shipments, searchQuery, activeFilter, statusFilter]);

  if (loading) {
    return (
      <div className="table-loading-container">
        <div className="loading-spinner" />
        <span className="loading-text">Loading live shipment registry from database...</span>
      </div>
    );
  }

  if (error && (!shipments || shipments.length === 0)) {
    return (
      <div className="table-error-container">
        <div className="error-title">Unable to fetch live data</div>
        <p className="error-desc">{error}</p>
      </div>
    );
  }

  // Extract distinct statuses for filter dropdown
  const availableStatuses = Array.from(
    new Set((shipments || []).map((s) => s.status).filter(Boolean))
  );

  return (
    <div className="shipment-table-component">
      {/* Control bar: Search + Filter Tabs + Status Select */}
      <div className="table-controls-bar">
        <div className="search-input-wrap">
          <svg className="search-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            className="table-search-input"
            placeholder="Search by ID, product, route, vehicle..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              type="button"
              className="search-clear-btn"
              onClick={() => setSearchQuery("")}
              title="Clear search"
            >
              ×
            </button>
          )}
        </div>

        <div className="filter-tabs-group">
          <button
            type="button"
            className={`filter-tab-pill ${activeFilter === "all" ? "active" : ""}`}
            onClick={() => setActiveFilter("all")}
          >
            All ({shipments.length})
          </button>
          <button
            type="button"
            className={`filter-tab-pill ${activeFilter === "active" ? "active" : ""}`}
            onClick={() => setActiveFilter("active")}
          >
            Active
          </button>
          <button
            type="button"
            className={`filter-tab-pill filter-pill-low ${activeFilter === "low" ? "active" : ""}`}
            onClick={() => setActiveFilter("low")}
          >
            Low Risk
          </button>
          <button
            type="button"
            className={`filter-tab-pill filter-pill-medium ${activeFilter === "medium" ? "active" : ""}`}
            onClick={() => setActiveFilter("medium")}
          >
            Medium Risk
          </button>
          <button
            type="button"
            className={`filter-tab-pill filter-pill-high ${activeFilter === "high-risk" ? "active" : ""}`}
            onClick={() => setActiveFilter("high-risk")}
          >
            High / Critical
          </button>
        </div>

        {availableStatuses.length > 0 && (
          <div className="status-dropdown-wrap">
            <select
              className="status-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">All Statuses</option>
              {availableStatuses.map((st) => (
                <option key={st} value={st}>
                  {st.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Shipments Table */}
      {filteredShipments.length === 0 ? (
        <div className="table-empty-box">
          <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="#8e7d72" strokeWidth="1.5">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <p className="empty-title">
            {shipments.length === 0 ? "No live shipments recorded in database" : "No matching shipments found"}
          </p>
          <p className="empty-subtitle">
            {shipments.length === 0
              ? "Ensure PostgreSQL is seeded and backend is active."
              : "Try adjusting your search criteria or risk filter filters."}
          </p>
          {(searchQuery || activeFilter !== "all" || statusFilter !== "all") && (
            <button
              type="button"
              className="reset-filters-btn"
              onClick={() => {
                setSearchQuery("");
                setActiveFilter("all");
                setStatusFilter("all");
              }}
            >
              Reset Filters
            </button>
          )}
        </div>
      ) : (
        <div className="modern-table-responsive">
          <table className="modern-data-table">
            <thead>
              <tr>
                <th>Shipment ID</th>
                <th>Vehicle</th>
                <th>Product</th>
                <th>Origin</th>
                <th>Destination</th>
                <th>Current Temp</th>
                <th>Humidity</th>
                <th>Risk Score</th>
                <th>Risk Level</th>
                <th>Status</th>
                <th>Last Updated</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredShipments.map((s) => {
                const isSelected = selectedId === s.shipment_id;
                const statusStr = String(s.status || "").toLowerCase();

                return (
                  <tr
                    key={s.shipment_id}
                    className={`shipment-row ${isSelected ? "row-selected" : ""}`}
                    onClick={() => onSelect && onSelect(s)}
                  >
                    <td>
                      <span className="shipment-primary-id">#{s.shipment_id}</span>
                    </td>

                    <td>
                      <span className="vehicle-tag">{s.vehicle_id || "—"}</span>
                    </td>

                    <td>
                      <div className="product-cell">
                        <span className="product-title">{s.product_name || "Consignment"}</span>
                        {s.product_category && (
                          <span className="product-category-sub">{s.product_category}</span>
                        )}
                      </div>
                    </td>

                    <td>
                      <span className="route-endpoint-name">{s.origin || "—"}</span>
                    </td>

                    <td>
                      <span className="route-endpoint-name">{s.destination || "—"}</span>
                    </td>

                    <td>
                      <div className="temp-cell">
                        <span className="temp-primary">{fmtTemp(s.temperature)}</span>
                        {s.cumulative_excursion_minutes > 0 && (
                          <span className="excursion-tag" title="Cumulative excursion minutes">
                            {s.cumulative_excursion_minutes}m breach
                          </span>
                        )}
                      </div>
                    </td>

                    <td>
                      <span className="humidity-primary">
                        {s.humidity != null ? `${Number(s.humidity).toFixed(1)}%` : "—"}
                      </span>
                    </td>

                    <td>
                      <span className="score-code">
                        {s.risk_score != null ? Number(s.risk_score).toFixed(4) : "—"}
                      </span>
                    </td>

                    <td>
                      <RiskBadge level={s.risk_level} score={s.risk_score} />
                    </td>

                    <td>
                      <span className={`status-badge status-${statusStr}`}>
                        <span className="status-badge-dot"></span>
                        {statusStr.replace(/_/g, " ")}
                      </span>
                    </td>

                    <td>
                      <span className="time-cell">
                        {s.last_updated
                          ? new Date(s.last_updated).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                              month: "short",
                              day: "numeric",
                            })
                          : "—"}
                      </span>
                    </td>

                    <td className="text-right">
                      <button
                        type="button"
                        className="inspect-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelect && onSelect(s);
                        }}
                      >
                        Inspect Details →
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};