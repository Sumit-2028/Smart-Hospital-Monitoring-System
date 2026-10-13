import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { API_BASE_URL, formatISTDateTime } from "../config";
import { useHospitalCrowdSummary } from "../hooks/useHospitalCrowdSummary";

function CrowdSummary() {
  const [alerts, setAlerts] = useState([]);
  const [alertError, setAlertError] = useState("");
  const [filter, setFilter] = useState("");
  const { summary, loading, error, retry, connectionState } = useHospitalCrowdSummary();

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/api/crowd/alerts/active`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Room alerts could not be loaded.");
        return response.json();
      })
      .then((data) => setAlerts(data.items || []))
      .catch((loadError) => {
        if (loadError.name !== "AbortError") setAlertError(loadError.message);
      });
    return () => controller.abort();
  }, [summary?.latest_reading_at]);

  const visibleRooms = useMemo(() => {
    const term = filter.trim().toLowerCase();
    return (summary?.rooms || []).filter((room) => !term || `${room.room_name} ${room.department_name || ""}`.toLowerCase().includes(term));
  }, [filter, summary]);

  if (loading && !summary) return <main className="dashboard crowd-summary-page"><div className="room-page-state card">Loading hospital-wide crowd summary...</div></main>;
  if (error && !summary) return <main className="dashboard crowd-summary-page"><div className="room-page-state card"><h1>Summary unavailable</h1><p>{error}</p><button type="button" className="back-button" onClick={retry}>Retry</button></div></main>;

  return <main className="dashboard crowd-summary-page">
    <header className="header room-page-header"><div><p className="analytics-label">HOSPITAL-WIDE CROWD</p><h1>Total Crowd Summary</h1><p>Latest valid reading from each configured monitoring room</p></div><div className="room-page-actions"><span className={`connection ${connectionState === "CONNECTED" ? "online" : "offline"}`}><span />LIVE UPDATES {connectionState}</span><Link to="/" className="back-button">← Back to Dashboard</Link></div></header>
    {error && <div className="system-message" role="alert">{error}</div>}
    <section className="card summary-hero"><div><p className="label">CURRENT HOSPITAL TOTAL</p><strong>{summary?.total_count ?? 0}</strong><span>people counted from fresh readings</span></div><div className="summary-hero-stats"><Metric label="Rooms complete" value={`${summary?.complete_room_count ?? 0} / ${summary?.configured_room_count ?? 0}`} /><Metric label="Normal rooms" value={summary?.normal_room_count ?? 0} /><Metric label="Congested rooms" value={summary?.congested_room_count ?? 0} /><Metric label="Cameras" value={`${summary?.connected_camera_count ?? 0} connected`} /></div></section>
    <div className={`summary-notice ${summary?.is_complete ? "summary-complete" : "summary-partial"}`} role="status">{summary?.is_complete ? "Complete: every configured room has a fresh valid reading." : `Partial: ${summary?.incomplete_room_count} room${summary?.incomplete_room_count === 1 ? " is" : "s are"} stale or unavailable. Those rooms are excluded from the total.`}</div>
    <section className="summary-room-section"><div className="section-title"><div><p className="label">ROOM BREAKDOWN</p><h2>Where people are detected</h2></div><input className="room-date-control" aria-label="Filter rooms" placeholder="Filter rooms..." value={filter} onChange={(event) => setFilter(event.target.value)} /></div>{visibleRooms.length === 0 ? <div className="card empty-text">{filter ? "No rooms match this filter." : "No active monitoring rooms are configured."}</div> : <div className="summary-room-grid">{visibleRooms.map((room) => <RoomRow key={room.room_id} room={room} alerts={alerts.filter((alert) => alert.room_id === room.room_id)} />)}</div>}</section>
    {alertError && <div className="system-message">{alertError}</div>}
  </main>;
}

function RoomRow({ room, alerts }) {
  const status = room.monitoring_status;
  const count = room.current_count == null ? "--" : room.current_count;
  return <Link to={`/monitoring/rooms/${room.room_id}`} className="card summary-room-card"><div className="summary-room-heading"><div><p className="label">{room.room_type}</p><h3>{room.room_name}</h3><p className="room-department">{room.department_name || "Unassigned department"}</p></div><span className={`status-badge ${status === "NORMAL" ? "normal" : status === "WARNING" ? "warning" : status === "CONGESTED" ? "danger" : "warning"}`}>{status}</span></div><div className="summary-room-count"><strong>{count}</strong><span>{room.capacity ? `/ ${room.capacity} people` : "No capacity"}</span></div><div className="progress-info"><span>Occupancy</span><span>{room.occupancy_percentage == null ? "--" : `${Math.round(room.occupancy_percentage)}%`}</span></div><div className="progress-bar"><div className={`progress-fill ${status === "CONGESTED" ? "danger-fill" : ""}`} style={{ width: `${Math.min(room.occupancy_percentage || 0, 100)}%` }} /></div><div className="summary-room-meta"><span>Camera: {room.camera_status}</span><span>Last reading: {formatISTDateTime(room.last_successful_reading_at)}</span></div>{alerts.length > 0 && <p className="summary-room-alert">{alerts.length} active congestion alert{alerts.length === 1 ? "" : "s"}</p>}{status === "STALE" && <p className="feed-stale">No fresh reading; last value excluded</p>}{status === "UNAVAILABLE" && <p className="feed-stale">No valid reading available</p>}<span className="summary-open-link">Open room monitoring →</span></Link>;
}

function Metric({ label, value }) { return <div className="room-stat"><span>{label}</span><strong>{value}</strong></div>; }

export default CrowdSummary;
