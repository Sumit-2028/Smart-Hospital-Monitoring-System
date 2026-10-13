import { useCallback, useEffect, useState } from "react";
import { Routes, Route, Link } from "react-router-dom";

import CrowdHistory from "./pages/CrowdHistory";
import AdminPanel from "./pages/AdminPanel";
import RoomMonitoring from "./pages/RoomMonitoring";
import CrowdSummary from "./pages/CrowdSummary";
import HospitalCrowdSummary from "./components/HospitalCrowdSummary";
import MultiRoomOverview from "./components/MultiRoomOverview";
import CongestionAlerts from "./components/CongestionAlerts";
import { IST_TIME_ZONE } from "./config";

function Dashboard() {
  const [hospitalSummary, setHospitalSummary] = useState(null);
  const [connected, setConnected] = useState(false);
  const [connectionState, setConnectionState] = useState("CONNECTING");

  const [currentTime, setCurrentTime] = useState(new Date());
  const handleSummaryChange = useCallback((summary) => setHospitalSummary(summary), []);
  const handleConnectionState = useCallback((state) => {
    setConnectionState(state);
    setConnected(state === "CONNECTED");
  }, []);

  // ----------------------------------------
  // Current time
  // ----------------------------------------

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => {
      clearInterval(timer);
    };
  }, []);

  const currentTimeText = currentTime.toLocaleTimeString("en-IN", {
    timeZone: IST_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });

  const isCongested = (hospitalSummary?.congested_room_count || 0) > 0;
  const personCount = hospitalSummary?.total_count ?? 0;

  return (
    <div className="dashboard">
      <header className="header">
        <div>
          <h1>Smart Hospital Monitoring</h1>

          <p>Real-Time Hospital Safety Dashboard</p>
        </div>

        {/* RIGHT SIDE OF HEADER */}

        <div className="header-right">
          {/* CURRENT TIME */}

          <div className="current-time">
            {currentTimeText}
          </div>

          {/* CONNECTION STATUS */}

          <div
            className={connected ? "connection online" : "connection offline"}
          >
            <span></span>

            {connectionState === "CONNECTED"
              ? "SYSTEM ONLINE"
              : connectionState}
          </div>
        </div>
      </header>

      <main>
        {/* Analytics Navigation */}

        <div className="analytics-navigation">
          <Link to="/analytics" className="analytics-button">
            Crowd Analytics →
          </Link>
          <Link to="/admin" className="back-button">Admin Configuration</Link>
        </div>

        <CongestionAlerts />
        <MultiRoomOverview />

        <section className="overview">
          {/* HOSPITAL-WIDE CROWD SUMMARY */}
          <HospitalCrowdSummary
            onSummaryChange={handleSummaryChange}
            onConnectionState={handleConnectionState}
          />

          {/* AIR QUALITY */}

          <div className="card">
            <p className="label">AIR QUALITY</p>

            <div className="metric-value">--</div>

            <div className="metric-status">SIMULATION</div>

            <p className="coming-soon">
              MQ-135 sensor will be connected later.
            </p>
          </div>

          {/* ACCESS CONTROL */}

          <div className="card">
            <p className="label">ACCESS CONTROL</p>

            <div className="metric-value">--</div>

            <div className="metric-status">SIMULATION</div>

            <p className="coming-soon">
              RFID reader is not connected yet.
            </p>
          </div>

          {/* DUSTBIN */}

          <div className="card">
            <p className="label">DUSTBIN LEVEL</p>

            <div className="metric-value">--</div>

            <div className="metric-status">SIMULATION</div>

            <p className="coming-soon">
              Ultrasonic sensor will be connected later.
            </p>
          </div>
        </section>

        <section className="bottom-grid">
          {/* ALERTS */}

          <div className="card alerts-card">
            <div className="section-title">
              <div>
                <p className="label">SYSTEM ALERTS</p>

                <h2>Recent Events</h2>
              </div>

              <span className="live-indicator">LIVE</span>
            </div>

            {isCongested ? (
              <div className="alert danger-alert">
                <div className="alert-icon">!</div>

                <div>
                  <strong>{hospitalSummary.congested_room_count} room{hospitalSummary.congested_room_count === 1 ? "" : "s"} congested</strong>

                  <p>
                    {personCount} people detected across the hospital. Open Total Crowd for room details.
                  </p>
                </div>
              </div>
            ) : (
              <div className="alert normal-alert">
                <div className="alert-icon">✓</div>

                <div>
                  <strong>Hospital crowd within room limits</strong>

                  <p>{personCount} people currently detected.</p>
                </div>
              </div>
            )}
          </div>

          {/* SYSTEM STATUS */}

          <div className="card system-card">
            <p className="label">SYSTEM STATUS</p>

            <h2>Connected Modules</h2>

            <div className="module">
              <span>Computer Vision</span>

              <span className="module-status">
                {connected ? "CONNECTED" : "WAITING"}
              </span>
            </div>

            <div className="module">
              <span>FastAPI Backend</span>

              <span className="module-status">
                {connected ? "CONNECTED" : "WAITING"}
              </span>
            </div>

            <div className="module">
              <span>PostgreSQL</span>

              <span className="module-status">PERSISTENCE</span>
            </div>

            <div className="module">
              <span>ESP32</span>

              <span className="module-status simulated">NOT CONNECTED</span>
            </div>

            <div className="module">
              <span>MQ-135 air quality</span>

              <span className="module-status simulated">SIMULATION</span>
            </div>

            <div className="module">
              <span>RFID access reader</span>

              <span className="module-status simulated">NOT CONNECTED</span>
            </div>

            <div className="module">
              <span>Ultrasonic level sensor</span>

              <span className="module-status simulated">NOT CONNECTED</span>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />

      <Route path="/monitoring/rooms/:roomId" element={<RoomMonitoring />} />
      <Route path="/crowd-summary" element={<CrowdSummary />} />

      <Route path="/analytics" element={<CrowdHistory />} />
      <Route path="/admin" element={<AdminPanel />} />
    </Routes>
  );
}

export default App;
