import { useEffect, useState, useCallback } from "react";
import axios from "axios";
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
    axios
      .get("/api/dashboard/shipments")
      .then((res) => {
        if (!cancelled && Array.isArray(res.data)) {
          setShipmentsList(res.data);
          // If no shipment was initially selected, pick the first one
          if (currentId == null && res.data.length > 0) {
            const firstId = res.data[0].shipment_id;
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
          axios.get(`/api/shipments/${currentId}/risk?include_shap=true${refresh}`),
          axios.get(`/api/shipments/${currentId}/telemetry?limit=500`),
          axios.get(`/api/shipments/${currentId}/alerts`),
        ]);

        if (riskRes.status === "fulfilled") {
          setRisk(riskRes.value.data);
          setLastUpdated(new Date().toISOString());
        } else {
          setRisk(null);
          const detail =
            riskRes.reason?.response?.data?.detail ||
            riskRes.reason?.message ||
            "Unable to fetch live data for this shipment";
          setError(detail);
        }

        if (telRes.status === "fulfilled") {
          setTelemetry(Array.isArray(telRes.value.data) ? telRes.value.data : []);
          setTelemetryError(null);
        } else {
          setTelemetry([]);
          setTelemetryError(telRes.reason?.message || "Telemetry unavailable");
        }

        if (alertRes.status === "fulfilled") {
          setAlerts(Array.isArray(alertRes.value.data) ? alertRes.value.data : []);
        } else {
          setAlerts([]);
        }
      } catch (err) {
        setError(err.message || "Unable to fetch live data");
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
      await axios.post(`/api/shipments/${currentId}/packaging`, form);
      await fetchData({ quiet: true, refresh: true });
    } catch (err) {
      const detail =
        err?.response?.data?.detail ||
        err.message ||
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
        fetchData({ quiet: true });
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
      onRefreshLive={() => fetchData({ quiet: false, refresh: true })}
    />
  );
};
