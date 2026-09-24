import { useEffect, useState, useCallback } from "react";
import { fetchJSON } from "../api.js";
import { ShipmentBody } from "./ShipmentDetailBody.jsx";

/**
 * Separate Shipment Details View/Page.
 * Fetches and polls actual risk assessment, live telemetry, and alerts
 * for the selected shipment directly from the backend.
 */
export const ShipmentDetail = ({ shipmentId, onBack, onSelectShipment }) => {
  const [currentId, setCurrentId] = useState(shipmentId);
  const [shipmentsList, setShipmentsList] = useState([]);
  const [risk, setRisk] = useState(null);
  const [telemetry, setTelemetry] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState(null);
  const [telemetryError, setTelemetryError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [packagingBusy, setPackagingBusy] = useState(false);
  const [packagingError, setPackagingError] = useState(null);

  // Sync internal ID if prop changes
  useEffect(() => {
    if (shipmentId != null) {
      setCurrentId(shipmentId);
    }
  }, [shipmentId]);

  // Load available shipments for the selector dropdown
  useEffect(() => {
    let cancelled = false;

    fetchJSON("/dashboard/shipments")
      .then((data) => {
        if (!cancelled && Array.isArray(data)) {
          setShipmentsList(data);

          // If no shipment was initially selected, pick the first one
          if (currentId == null && data.length > 0) {
            const firstId = data[0].shipment_id;
            setCurrentId(firstId);
            onSelectShipment?.(firstId);
          }
        }
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, []);

  const fetchData = useCallback(
    async (opts = {}) => {
      if (currentId == null) return;

      const quiet = Boolean(opts.quiet);

      if (!quiet) setLoading(true);

      setIsUpdating(true);
      setError(null);

      try {
        const refresh = opts.refresh ? "&refresh=true" : "";

        const [riskRes, telRes, alertRes] = await Promise.allSettled([
          fetchJSON(
            `/shipments/${currentId}/risk?include_shap=true${refresh}`
          ),

          fetchJSON(
            `/shipments/${currentId}/telemetry?limit=500`
          ),

          fetchJSON(
            `/shipments/${currentId}/alerts`
          ),
        ]);

        // Risk
        if (riskRes.status === "fulfilled") {
          setRisk(riskRes.value);
          setLastUpdated(new Date().toISOString());
        } else {
          setRisk(null);

          const detail =
            riskRes.reason?.message ||
            "Unable to fetch live data for this shipment";

          setError(detail);
        }

        // Telemetry
        if (telRes.status === "fulfilled") {
          setTelemetry(
            Array.isArray(telRes.value)
              ? telRes.value
              : []
          );

          setTelemetryError(null);
        } else {
          setTelemetry([]);

          setTelemetryError(
            telRes.reason?.message ||
            "Telemetry unavailable"
          );
        }

        // Alerts
        if (alertRes.status === "fulfilled") {
          setAlerts(
            Array.isArray(alertRes.value)
              ? alertRes.value
              : []
          );
        } else {
          setAlerts([]);
        }
      } catch (err) {
        setError(
          err.message ||
          "Unable to fetch live data"
        );
      } finally {
        if (!quiet) setLoading(false);

        setIsUpdating(false);
      }
    },
    [currentId]
  );

  const uploadPackaging = async (file) => {
    if (!file || currentId == null) return;

    setPackagingBusy(true);
    setPackagingError(null);

    const form = new FormData();
    form.append("file", file);

    try {
      const response = await fetch(
        `https://coldchain-backend-cfes.onrender.com/shipments/${currentId}/packaging`,
        {
          method: "POST",
          body: form,
        }
      );

      if (!response.ok) {
        const text = await response.text().catch(() => "");

        let detail = `HTTP ${response.status}`;

        try {
          const json = JSON.parse(text);
          detail =
            json.detail ||
            json.message ||
            detail;
        } catch {
          if (text) detail = text;
        }

        throw new Error(detail);
      }

      await fetchData({
        quiet: true,
        refresh: true,
      });
    } catch (err) {
      const detail =
        err?.message ||
        "Packaging upload failed";

      setPackagingError(detail);
    } finally {
      setPackagingBusy(false);
    }
  };

  useEffect(() => {
    if (currentId != null) {
      fetchData();

      const id = setInterval(() => {
        fetchData({
          quiet: true,
        });
      }, 15000);

      return () => clearInterval(id);
    }
  }, [currentId, fetchData]);

  const handleShipmentSwitch = (newId) => {
    setCurrentId(newId);
    onSelectShipment?.(newId);
  };

  return (
    <ShipmentBody
      shipmentId={currentId}
      shipmentsList={shipmentsList}
      onSwitchShipment={handleShipmentSwitch}
      risk={risk}
      loading={loading}
      isUpdating={isUpdating}
      lastUpdated={lastUpdated}
      error={error}
      telemetry={telemetry}
      telemetryError={telemetryError}
      alerts={alerts}
      onBack={onBack}
      onUploadPackaging={uploadPackaging}
      packagingBusy={packagingBusy}
      packagingError={packagingError}
      onRefreshLive={() =>
        fetchData({
          quiet: false,
          refresh: true,
        })
      }
    />
  );
};