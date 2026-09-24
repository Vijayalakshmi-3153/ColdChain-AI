import { useEffect, useState } from "react";
import { fetchHealth } from "./api.js";
import { Dashboard } from "./components/Dashboard.jsx";
import { ShipmentDetail } from "./components/ShipmentDetail.jsx";
import { ReportsPage } from "./components/ReportsPage.jsx";
import { TelemetryPage } from "./components/TelemetryPage.jsx";
import { Header } from "./components/Header.jsx";
import { Chatbot } from "./components/Chatbot.jsx";
import "./App.css";

function App() {
  const [backendStatus, setBackendStatus] = useState("checking...");
  const [route, setRoute] = useState("dashboard");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [isUpdating, setIsUpdating] = useState(false);
  const [selectedShipmentId, setSelectedShipmentId] = useState(null);
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    const check = async () => {
      setIsUpdating(true);
      try {
        const data = await fetchHealth();
        setBackendStatus(data.status === "ok" ? "online" : "degraded");
        setLastUpdated(new Date().toISOString());
      } catch {
        setBackendStatus("offline");
      } finally {
        setIsUpdating(false);
      }
    };

    check();
    const id = setInterval(() => {
      check();
    }, 15000);
    return () => clearInterval(id);
  }, []);

  const backendOk = backendStatus === "online" || backendStatus === "degraded";

  const handleSelectShipment = (id) => {
    setSelectedShipmentId(id);
    setRoute("details");
  };

  return (
    <div className={`app-shell ${chatOpen ? "chat-is-open" : ""}`}>
      <Header
        backendStatus={backendStatus}
        lastUpdated={lastUpdated}
        isUpdating={isUpdating}
        route={route}
        onRoute={setRoute}
        selectedShipmentId={selectedShipmentId}
      />

      <main className="app-main-viewport">
        {route === "dashboard" && (
          <Dashboard
            onSelectShipment={handleSelectShipment}
          />
        )}

        {route === "details" && (
          <ShipmentDetail
            shipmentId={selectedShipmentId}
            onBack={() => setRoute("dashboard")}
            onSelectShipment={setSelectedShipmentId}
          />
        )}

        {route === "reports" && (
          <ReportsPage
            shipmentId={selectedShipmentId}
            onSelectShipment={setSelectedShipmentId}
          />
        )}

        {route === "telemetry" && (
          <TelemetryPage
            backendOk={backendOk}
            shipmentId={selectedShipmentId}
          />
        )}
      </main>

      <Chatbot
        shipmentId={selectedShipmentId}
        onOpenChange={setChatOpen}
      />
    </div>
  );
}

export default App;
