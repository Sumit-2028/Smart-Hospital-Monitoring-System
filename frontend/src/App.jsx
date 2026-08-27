import { useEffect, useState } from "react";
import { Routes, Route, Link } from "react-router-dom";

import CrowdHistory from "./pages/CrowdHistory";

function Dashboard() {
  const [personCount, setPersonCount] = useState(0);
  const [threshold, setThreshold] = useState(20);
  const [status, setStatus] = useState("NORMAL");
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState("--");

  useEffect(() => {
    const socket = new WebSocket("ws://127.0.0.1:8000/ws");

    socket.onopen = () => {
      console.log("WebSocket connected");

      setConnected(true);
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      console.log("Live crowd data:", data);

      setPersonCount(data.person_count);

      setThreshold(data.threshold);

      setStatus(data.status);

      setLastUpdate(new Date().toLocaleTimeString());
    };

    socket.onclose = () => {
      console.log("WebSocket disconnected");

      setConnected(false);
    };

    socket.onerror = (error) => {
      console.error("WebSocket error:", error);

      setConnected(false);
    };

    return () => {
      socket.close();
    };
  }, []);

  const isCongested = status === "CONGESTED";

  return (
    <div className="dashboard">
      <header className="header">
        <div>
          <h1>Smart Hospital Monitoring</h1>

          <p>Real-Time Hospital Safety Dashboard</p>
        </div>

        <div className={connected ? "connection online" : "connection offline"}>
          <span></span>

          {connected ? "SYSTEM ONLINE" : "SYSTEM OFFLINE"}
        </div>
      </header>

      <main>
        {/* Analytics Navigation */}

        <div className="analytics-navigation">
          <Link to="/analytics" className="analytics-button">
            Crowd Analytics →
          </Link>
        </div>

        <section className="overview">
          {/* LIVE CROWD */}

          <div className="card crowd-card">
            <div className="card-header">
              <div>
                <p className="label">WAITING AREA</p>

                <h2>Live Crowd Monitoring</h2>
              </div>

              <div
                className={
                  isCongested ? "status-badge danger" : "status-badge normal"
                }
              >
                {isCongested ? "CONGESTED" : "NORMAL"}
              </div>
            </div>

            <div className="crowd-number">{personCount}</div>

            <p className="people-text">PEOPLE DETECTED</p>

            <div className="progress-container">
              <div className="progress-info">
                <span>Occupancy</span>

                <span>
                  {personCount} / {threshold}
                </span>
              </div>

              <div className="progress-bar">
                <div
                  className={
                    isCongested ? "progress-fill danger-fill" : "progress-fill"
                  }
                  style={{
                    width: `${Math.min((personCount / threshold) * 100, 100)}%`,
                  }}
                />
              </div>
            </div>

            <div className="last-update">Last update: {lastUpdate}</div>
          </div>

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

            <div className="metric-value">SECURE</div>

            <div className="metric-status">SIMULATION</div>

            <p className="coming-soon">RFID reader will be connected later.</p>
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
                  <strong>Waiting area congested</strong>

                  <p>
                    {personCount} people detected. Threshold is {threshold}.
                  </p>
                </div>
              </div>
            ) : (
              <div className="alert normal-alert">
                <div className="alert-icon">✓</div>

                <div>
                  <strong>Waiting area normal</strong>

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

              <span className="module-status">CONNECTED</span>
            </div>

            <div className="module">
              <span>ESP32</span>

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

      <Route path="/analytics" element={<CrowdHistory />} />
    </Routes>
  );
}

export default App;
