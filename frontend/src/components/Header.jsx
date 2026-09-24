import { fmtTimeOnly } from "../utils/formatting.js";

export const Header = ({ backendStatus, lastUpdated, isUpdating, route, onRoute, selectedShipmentId }) => {
  const isOnline = backendStatus === "online" || backendStatus === "degraded";

  return (
    <header className="app-header">
      <div className="header-left">
        <div className="brand-badge">
          <svg className="brand-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <div className="brand-text">
          <div className="brand-title-row">
            <h1>ColdChain AI</h1>
            <span className="platform-tag">Enterprise Monitor</span>
          </div>
          <p>Real-Time Cold Chain Logistics & Predictive Spoilage Risk Engine</p>
        </div>
      </div>

      <div className="header-right">
        
        {/* Primary View Navigation */}
        <nav className="header-nav">
          <button
            type="button"
            className={`nav-tab ${route === "dashboard" ? "active" : ""}`}
            onClick={() => onRoute("dashboard")}
          >
            <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="9" rx="1" />
              <rect x="14" y="3" width="7" height="5" rx="1" />
              <rect x="14" y="12" width="7" height="9" rx="1" />
              <rect x="3" y="16" width="7" height="5" rx="1" />
            </svg>
            Dashboard
          </button>

          <button
            type="button"
            className={`nav-tab ${route === "details" ? "active" : ""}`}
            onClick={() => onRoute("details")}
          >
            <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
            Shipment Details
            {selectedShipmentId && (
              <span className="nav-active-pill">#{selectedShipmentId}</span>
            )}
          </button>

          <button
            type="button"
            className={`nav-tab ${route === "reports" ? "active" : ""}`}
            onClick={() => onRoute("reports")}
          >
            <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
            Reports
          </button>

          <button
            type="button"
            className={`nav-tab ${route === "telemetry" ? "active" : ""}`}
            onClick={() => onRoute("telemetry")}
          >
            <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
            </svg>
            Telemetry
          </button>
        </nav>
      </div>
    </header>
  );
};
