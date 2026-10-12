import { useEffect, useState } from "react";
import { Routes, Route, Link } from "react-router-dom";

import CrowdHistory from "./pages/CrowdHistory";
import AdminPanel from "./pages/AdminPanel";
import MultiRoomOverview from "./components/MultiRoomOverview";
import CongestionAlerts from "./components/CongestionAlerts";
import {
  API_BASE_URL,
  formatISTTime,
  IST_TIME_ZONE,
  WS_URL,
} from "./config";

function Dashboard() {
  const [personCount, setPersonCount] = useState(0);
  const [threshold, setThreshold] = useState(null);
  const [status, setStatus] = useState("NORMAL");
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState("--");
  const [connectionState, setConnectionState] = useState("CONNECTING");
  const [error, setError] = useState("");

  const [currentTime, setCurrentTime] = useState(new Date());

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

  // ----------------------------------------
  // Hydrate the dashboard from persisted state before the next live update.
  useEffect(() => {
    const controller = new AbortController();

    fetch(`${API_BASE_URL}/api/crowd/latest`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Unable to load the latest crowd reading");
        }

        return response.json();
      })
      .then((data) => {
        if (!data) {
          return;
        }

        setPersonCount(data.person_count);
        setThreshold(data.threshold);
        setStatus(data.status);
        setLastUpdate(formatISTTime(data.timestamp));
      })
      .catch((fetchError) => {
        if (fetchError.name !== "AbortError") {
          setError("Live data is not available yet.");
        }
      });

    return () => controller.abort();
  }, []);

  // WebSocket live updates with a small reconnect delay for temporary outages.
  useEffect(() => {
    let socket;
    let reconnectTimer;
    let disposed = false;

    const connect = () => {
      if (disposed) {
        return;
      }

      setConnectionState("CONNECTING");
      socket = new WebSocket(WS_URL);

      socket.onopen = () => {
        setConnected(true);
        setConnectionState("CONNECTED");
        setError("");
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (
            typeof data.person_count !== "number" ||
            typeof data.threshold !== "number"
          ) {
            return;
          }

          setPersonCount(data.person_count);
          setThreshold(data.threshold);
          setStatus(data.status === "CONGESTED" ? "CONGESTED" : "NORMAL");
          setLastUpdate(formatISTTime(data.timestamp));
        } catch {
          setError("Received an invalid live crowd update.");
        }
      };

      socket.onclose = () => {
        setConnected(false);
        setConnectionState("RECONNECTING");

        if (!disposed) {
          reconnectTimer = setTimeout(connect, 3000);
        }
      };

      socket.onerror = () => {
        setConnected(false);
        setConnectionState("RECONNECTING");
      };
    };

    connect();

    return () => {
      disposed = true;
      clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  const currentTimeText = currentTime.toLocaleTimeString("en-IN", {
    timeZone: IST_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });

  const isCongested = status === "CONGESTED";
  const occupancyPercent = threshold
    ? Math.min((personCount / threshold) * 100, 100)
    : 0;

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
        {error && <div className="system-message">{error}</div>}
        {/* Analytics Navigation */}

        <div className="analytics-navigation">
          <Link to="/analytics" className="analytics-button">
            Crowd Analytics →
          </Link>
          <Link to="/admin" className="back-button">Admin Configuration</Link>
        </div>

        <MultiRoomOverview />
        <CongestionAlerts />

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

            <div className="crowd-number" aria-live="polite">
              {personCount}
            </div>

            <p className="people-text">PEOPLE DETECTED</p>

            <div className="progress-container">
              <div className="progress-info">
                <span>Occupancy</span>

                <span>
                  {personCount} / {threshold ?? "--"}
                </span>
              </div>

              <div
                className="progress-bar"
                role="progressbar"
                aria-valuenow={personCount}
                aria-valuemin="0"
                aria-valuemax={threshold || 0}
                aria-label="Waiting area occupancy"
              >
                <div
                  className={
                    isCongested ? "progress-fill danger-fill" : "progress-fill"
                  }
                  style={{
                    width: `${occupancyPercent}%`,
                  }}
                />
              </div>
            </div>

            <div className="last-update">Last crowd update: {lastUpdate}</div>
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

      <Route path="/analytics" element={<CrowdHistory />} />
      <Route path="/admin" element={<AdminPanel />} />
    </Routes>
  );
}

export default App;
