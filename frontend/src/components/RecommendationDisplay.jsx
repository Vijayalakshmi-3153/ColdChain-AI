/** Recommendations list from the risk assessment (RULE-BASED output). */
export const Recommendations = ({ recommendations, loading, error }) => {
  if (loading) return <div className="data-empty-hint">Loading recommendations...</div>;
  if (error) return <div className="app-banner-error">{error}</div>;
  if (!recommendations || recommendations.length === 0) {
    return <div className="data-empty-hint">No corrective recommendations flagged for this consignment.</div>;
  }

  return (
    <ul className="recommendations-modern-list">
      {recommendations.map((rec, i) => {
        const sev = String(rec.severity || "info").toLowerCase();
        return (
          <li key={i} className={`rec-card-item rec-${sev}`}>
            <div className="rec-header-row">
              <span className={`rec-severity-chip chip-${sev}`}>
                {rec.severity ? rec.severity.toUpperCase() : "INFO"}
              </span>
              <span className="rec-code-tag">{rec.code || "PROC-REC"}</span>
            </div>
            <div className="rec-action-title">{rec.action}</div>
            {rec.reason && <div className="rec-reason-desc">{rec.reason}</div>}
          </li>
        );
      })}
    </ul>
  );
};

