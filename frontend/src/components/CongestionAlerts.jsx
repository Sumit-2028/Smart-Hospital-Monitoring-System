import { useEffect, useState } from "react";

import { API_BASE_URL, formatISTDateTime, WS_URL } from "../config";

function CongestionAlerts() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadAlerts = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/crowd/alerts/active`);
      if (!response.ok) throw new Error("Could not load active alerts");
      const data = await response.json();
      setAlerts(data.items || []);
      setError("");
    } catch {
      setError("Active congestion alerts could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const initialLoadTimer = window.setTimeout(loadAlerts, 0);
    const refreshTimer = window.setInterval(loadAlerts, 10000);
    let socket;
    let reconnectTimer;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      socket = new WebSocket(WS_URL);
      socket.onopen = loadAlerts;
      socket.onmessage = (message) => {
        try {
          const update = JSON.parse(message.data);
          if (!update.event_type?.startsWith("congestion.")) return;
          const event = update.event;
          if (!event?.id) return;
          setAlerts((current) => {
            if (update.event_type === "congestion.resolved") {
              return current.filter((item) => item.id !== event.id);
            }
            const existing = current.find((item) => item.id === event.id);
            return existing
              ? current.map((item) => item.id === event.id ? { ...item, ...event } : item)
              : [event, ...current];
          });
        } catch {
          setError("An invalid congestion alert update was received.");
        }
      };
      socket.onclose = () => {
        if (!disposed) reconnectTimer = window.setTimeout(connect, 3000);
      };
    };

    connect();
    return () => {
      disposed = true;
      window.clearTimeout(initialLoadTimer);
      window.clearInterval(refreshTimer);
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  return (
    <section className="congestion-alert-section">
      <div className="section-title">
        <div>
          <p className="label">CONGESTION ALERTS</p>
          <h2>Active room alerts</h2>
        </div>
        <span className="live-indicator">LIVE</span>
      </div>
      {loading ? <div className="card empty-text">Loading active alerts...</div> : error ? (
        <div className="card system-message"><p>{error}</p><button className="back-button" onClick={loadAlerts}>Retry</button></div>
      ) : alerts.length === 0 ? (
        <div className="card empty-text" role="status">No active congestion alerts.</div>
      ) : (
        <div className="alert-grid">
          {alerts.map((alert) => (
            <article className="card congestion-alert-card" key={alert.id}>
              <div className="alert-heading"><h3>{alert.room_name || "Legacy monitoring"}</h3><span className="status-badge danger">{alert.current_reading_is_stale ? "STALE" : "ACTIVE"}</span></div>
              {alert.current_reading_is_stale ? <p>No fresh reading for this event.</p> : <p>{alert.current_count} / {alert.threshold} people</p>}
              <p>Started: {formatISTDateTime(alert.started_at)}</p>
              <p>Duration: {formatDuration(alert.duration_seconds)}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function formatDuration(seconds) {
  const totalMinutes = Math.floor((seconds || 0) / 60);
  return totalMinutes < 1 ? "Less than 1 min" : `${totalMinutes} min`;
}

export default CongestionAlerts;
