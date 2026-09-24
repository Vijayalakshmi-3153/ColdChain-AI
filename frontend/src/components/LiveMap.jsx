import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { fmtTime, fmtTemp, riskColor } from "../utils/formatting.js";

// Fix Leaflet's default marker icons
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const DefaultIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
});

export const LiveMap = ({ shipments = [], notes, onSelect }) => {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markersRef = useRef([]);
  const polylineRef = useRef(null);

  // Fallback center: India centroid
  let center = [20.5937, 78.9629];
  for (const s of shipments || []) {
    if (s.latitude != null && s.longitude != null) {
      center = [Number(s.latitude), Number(s.longitude)];
      break;
    }
  }

  useEffect(() => {
    if (!mapInstanceRef.current) {
      const el = mapRef.current;
      if (!el) return;

      mapInstanceRef.current = L.map(el, {
        center: center,
        zoom: 4,
        scrollWheelZoom: true,
      });

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://osm.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 18,
      }).addTo(mapInstanceRef.current);
    } else {
      mapInstanceRef.current.setView(center, 4);
    }

    const map = mapInstanceRef.current;

    // Clear previous markers & polylines
    markersRef.current.forEach((m) => map.removeLayer(m));
    markersRef.current = [];
    if (polylineRef.current) {
      map.removeLayer(polylineRef.current);
      polylineRef.current = null;
    }

    const coords = [];
    (shipments || []).forEach((s) => {
      // Strictly use actual backend coordinates - never synthesize fake coordinates
      if (s.latitude == null || s.longitude == null) return;
      const pos = [Number(s.latitude), Number(s.longitude)];
      coords.push(pos);

      const rkColor = riskColor(s.risk_level);
      const popupEl = document.createElement("div");
      popupEl.className = "leaflet-custom-popup";
      popupEl.innerHTML = `
        <div class="popup-header">
          <strong>Shipment #${s.shipment_id}</strong>
          <span class="popup-status">${s.status || "In Transit"}</span>
        </div>
        <div class="popup-body">
          <div><strong>Product:</strong> ${s.product_name || "Consignment"}</div>
          <div><strong>Route:</strong> ${s.origin || "—"} → ${s.destination || "—"}</div>
          <div><strong>Actual Temp:</strong> ${fmtTemp(s.temperature)}</div>
          <div><strong>Actual Humidity:</strong> ${s.humidity != null ? Number(s.humidity).toFixed(1) + "%" : "—"}</div>
          <div class="popup-risk-row">
            <strong>Risk:</strong>
            <span class="popup-risk-badge" style="background:${rkColor}15; color:${rkColor}; border:1px solid ${rkColor}40">
              ${s.risk_level || "UNKNOWN"} ${s.risk_score != null ? `(${(Number(s.risk_score) * 100).toFixed(0)}%)` : ""}
            </span>
          </div>
          <div class="popup-timestamp">Last Telemetry: ${s.last_updated ? fmtTime(s.last_updated) : "Live"}</div>
          <button type="button" class="popup-action-btn">
            View Full Shipment Details →
          </button>
        </div>
      `;

      const btn = popupEl.querySelector(".popup-action-btn");
      if (btn && onSelect) {
        btn.addEventListener("click", () => onSelect(s));
      }

      const marker = L.marker(pos, { icon: DefaultIcon })
        .addTo(map)
        .bindPopup(popupEl, { className: "custom-leaflet-container" });

      if (onSelect) {
        marker.on("dblclick", () => onSelect(s));
      }
      markersRef.current.push(marker);
    });

    if (coords.length > 1) {
      polylineRef.current = L.polyline(coords, {
        color: "#85532d",
        weight: 3.5,
        opacity: 0.85,
        dashArray: "6, 6",
      }).addTo(map);
      map.fitBounds(polylineRef.current.getBounds().pad(0.3));
    } else if (coords.length === 1) {
      map.setView(coords[0], 6);
    }

    return () => {
      if (mapInstanceRef.current) {
        markersRef.current.forEach((m) => mapInstanceRef.current.removeLayer(m));
        markersRef.current = [];
        if (polylineRef.current) {
          mapInstanceRef.current.removeLayer(polylineRef.current);
          polylineRef.current = null;
        }
      }
    };
  }, [shipments, center, onSelect]);

  const activePointsCount = (shipments || []).filter(
    (s) => s.latitude != null && s.longitude != null
  ).length;

  return (
    <div className="live-map-wrapper">
      <div className="map-meta-header">
        <div className="map-badge-group">
          <span className="live-pulse-dot"></span>
          <span className="map-active-count">
            {activePointsCount} Live Consignments with GPS Telemetry
          </span>
        </div>
        {notes && <span className="map-notes-text">{notes}</span>}
      </div>

      <div ref={mapRef} id="coldchain-map" className="map-canvas-container" />
    </div>
  );
};
