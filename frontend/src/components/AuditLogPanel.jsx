import { useCallback, useEffect, useState } from "react";

import { API_BASE_URL, formatISTDateTime } from "../config";

function AuditLogPanel({ token, onSessionExpired }) {
  const [filters, setFilters] = useState({ start_date: "", end_date: "", actor_id: "", actor_username: "", action: "", resource_type: "", outcome: "" });
  const [result, setResult] = useState({ items: [], total: 0, offset: 0, limit: 25 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (offset = 0) => {
    setLoading(true); setError("");
    const params = new URLSearchParams({ offset: String(offset), limit: "25" });
    Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value); });
    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/audit-logs?${params.toString()}`, { headers: { Authorization: `Bearer ${token}` } });
      if (response.status === 401) { onSessionExpired(); throw new Error("Admin session expired. Please sign in again."); }
      if (response.status === 403) throw new Error("Super administrator privileges are required.");
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Could not load audit logs.");
      setResult(body);
    } catch (requestError) { setError(requestError.message === "Failed to fetch" ? "Backend is unreachable." : requestError.message); }
    finally { setLoading(false); }
  }, [filters, onSessionExpired, token]);

  useEffect(() => { const timer = setTimeout(() => { void load(0); }, 0); return () => clearTimeout(timer); }, [load]);

  const update = (key, value) => setFilters({ ...filters, [key]: value });
  const nextOffset = result.offset + result.limit;
  const previousOffset = Math.max(0, result.offset - result.limit);

  return <section className="card audit-panel">
    <div className="section-heading"><div><p className="analytics-label">SECURITY</p><h2>Audit log</h2></div><button className="row-action" onClick={() => load(result.offset)} disabled={loading}>Refresh</button></div>
    <div className="audit-filters">
      <label>Start date<input type="date" value={filters.start_date} onChange={(event) => update("start_date", event.target.value)} /></label>
      <label>End date<input type="date" value={filters.end_date} onChange={(event) => update("end_date", event.target.value)} /></label>
      <label>Actor ID<input type="number" min="1" value={filters.actor_id} onChange={(event) => update("actor_id", event.target.value)} /></label>
      <label>Actor username<input placeholder="admin" value={filters.actor_username} onChange={(event) => update("actor_username", event.target.value)} /></label>
      <label>Action<input placeholder="ADMIN_CREATED" value={filters.action} onChange={(event) => update("action", event.target.value)} /></label>
      <label>Resource<input placeholder="ROOM" value={filters.resource_type} onChange={(event) => update("resource_type", event.target.value)} /></label>
      <label>Outcome<select value={filters.outcome} onChange={(event) => update("outcome", event.target.value)}><option value="">All outcomes</option><option>SUCCESS</option><option>FAILURE</option></select></label>
      <button className="primary-button" onClick={() => load(0)} disabled={loading}>Apply filters</button>
    </div>
    {error && <p className="form-error">{error}</p>}
    {error && result.items.length > 0 && <p className="stale-text">Showing the last successfully loaded audit page.</p>}
    {loading && result.items.length === 0 ? <p className="empty-text">Loading audit logs...</p> : result.items.length === 0 ? <p className="empty-text">No audit records match these filters.</p> : <div className="audit-table-wrap"><table className="audit-table"><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Resource</th><th>Outcome</th><th>Metadata</th></tr></thead><tbody>{result.items.map((item) => <tr key={item.id}><td>{formatISTDateTime(item.timestamp)}</td><td>{item.actor_username || "System/unknown"}</td><td>{item.action}</td><td>{item.resource_type || "—"}{item.resource_id ? ` #${item.resource_id}` : ""}</td><td><span className={item.outcome === "SUCCESS" ? "audit-success" : "audit-failure"}>{item.outcome}</span></td><td>{item.metadata ? JSON.stringify(item.metadata) : "—"}</td></tr>)}</tbody></table></div>}
    <div className="audit-pagination"><button className="row-action" onClick={() => load(previousOffset)} disabled={loading || result.offset === 0}>Previous</button><span>{result.total === 0 ? "0" : `${result.offset + 1}-${Math.min(result.offset + result.limit, result.total)} of ${result.total}`}</span><button className="row-action" onClick={() => load(nextOffset)} disabled={loading || nextOffset >= result.total}>Next</button></div>
  </section>;
}

export default AuditLogPanel;
