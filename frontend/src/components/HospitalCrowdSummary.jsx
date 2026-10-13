import { useEffect } from "react";
import { Link } from "react-router-dom";

import { formatISTDateTime } from "../config";
import { useHospitalCrowdSummary } from "../hooks/useHospitalCrowdSummary";

function HospitalCrowdSummary({ onSummaryChange, onConnectionState }) {
  const { summary, loading, error, retry } = useHospitalCrowdSummary(onConnectionState);

  useEffect(() => {
    onSummaryChange?.(summary);
  }, [onSummaryChange, summary]);

  if (loading && !summary) {
    return <section className="card hospital-summary-card" aria-busy="true"><p className="label">HOSPITAL-WIDE CROWD</p><h2>Total Crowd</h2><p className="empty-text">Loading current room readings...</p></section>;
  }
  if (error && !summary) {
    return <section className="card hospital-summary-card system-message"><p>{error}</p><button type="button" className="back-button" onClick={retry}>Retry</button></section>;
  }

  const partial = summary?.incomplete_room_count > 0;
  return <Link to="/crowd-summary" className="card hospital-summary-card hospital-summary-link" aria-label="Open hospital-wide crowd summary">
    <div className="card-header"><div><p className="label">HOSPITAL-WIDE CROWD</p><h2>Total Crowd</h2></div><span className={`status-badge ${partial ? "warning" : "normal"}`}>{partial ? "PARTIAL" : "COMPLETE"}</span></div>
    {error && <p className="summary-inline-error">{error}</p>}
    <div className="crowd-number" aria-live="polite">{summary?.total_count ?? "--"}</div>
    <p className="people-text">PEOPLE DETECTED ACROSS {summary?.configured_room_count || 0} ROOMS</p>
    <div className="summary-stat-grid"><div><strong>{summary?.monitored_room_count ?? 0}</strong><span>Monitored rooms</span></div><div><strong>{summary?.normal_room_count ?? 0}</strong><span>Normal rooms</span></div><div><strong>{summary?.congested_room_count ?? 0}</strong><span>Congested rooms</span></div><div><strong>{summary?.connected_camera_count ?? 0}/{(summary?.connected_camera_count ?? 0) + (summary?.disconnected_camera_count ?? 0)}</strong><span>Cameras connected</span></div></div>
    <div className="summary-freshness">{partial ? `${summary.incomplete_room_count} room${summary.incomplete_room_count === 1 ? "" : "s"} missing a fresh reading` : "All configured rooms have fresh readings"} · Last update {formatISTDateTime(summary?.latest_reading_at)}</div>
    <span className="summary-open-link">Open room-by-room summary →</span>
  </Link>;
}

export default HospitalCrowdSummary;
