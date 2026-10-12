import { useCallback, useEffect, useState } from "react";

import { API_BASE_URL, formatISTDateTime } from "../config";

const emptyForm = { username: "", password: "", role: "ADMIN", active: true };

function AdminUsersPanel({ token, onSessionExpired }) {
  const [admins, setAdmins] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/admins`, { headers: { Authorization: `Bearer ${token}` } });
      if (response.status === 401) { onSessionExpired(); throw new Error("Admin session expired. Please sign in again."); }
      if (response.status === 403) throw new Error("Super administrator privileges are required.");
      if (!response.ok) throw new Error("Could not load administrators.");
      setAdmins(await response.json());
    } catch (requestError) {
      setError(requestError.message === "Failed to fetch" ? "Backend is unreachable." : requestError.message);
    } finally {
      setLoading(false);
    }
  }, [onSessionExpired, token]);

  useEffect(() => { const timer = setTimeout(() => { void load(); }, 0); return () => clearTimeout(timer); }, [load]);

  const save = async (event) => {
    event.preventDefault();
    setSaving(true); setError(""); setMessage("");
    const body = { username: form.username.trim(), role: form.role, active: form.active };
    if (form.password) body.password = form.password;
    if (!editingId && !form.password) { setError("A password is required for a new administrator."); setSaving(false); return; }
    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/admins${editingId ? `/${editingId}` : ""}`, {
        method: editingId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      const result = await response.json().catch(() => ({}));
      if (response.status === 401) { onSessionExpired(); throw new Error("Admin session expired. Please sign in again."); }
      if (!response.ok) throw new Error(result.detail || "Administrator could not be saved.");
      setMessage("Administrator saved."); setEditingId(null); setForm(emptyForm); await load();
    } catch (requestError) {
      setError(requestError.message === "Failed to fetch" ? "Backend is unreachable." : requestError.message);
    } finally { setSaving(false); }
  };

  const edit = (admin) => {
    setEditingId(admin.id);
    setForm({ username: admin.username, password: "", role: admin.role, active: admin.active });
    setMessage(""); setError("");
  };

  const changeActive = async (admin) => {
    setError(""); setMessage("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/admins/${admin.id}/active?active=${!admin.active}`, {
        method: "PATCH", headers: { Authorization: `Bearer ${token}` },
      });
      const result = await response.json().catch(() => ({}));
      if (response.status === 401) { onSessionExpired(); throw new Error("Admin session expired. Please sign in again."); }
      if (!response.ok) throw new Error(result.detail || "Could not change administrator status.");
      await load();
    } catch (requestError) { setError(requestError.message === "Failed to fetch" ? "Backend is unreachable." : requestError.message); }
  };

  return <section className="admin-layout">
    <form className="card admin-form" onSubmit={save}>
      <h2>{editingId ? "Edit administrator" : "Add administrator"}</h2>
      <label>Username<input required minLength="1" maxLength="120" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} /></label>
      <label>{editingId ? "New password (optional)" : "Password"}<input type="password" minLength="8" maxLength="200" required={!editingId} value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
      <label>Role<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}><option>ADMIN</option><option>SUPERADMIN</option></select></label>
      <label className="checkbox-label"><input type="checkbox" checked={form.active} onChange={(event) => setForm({ ...form, active: event.target.checked })} /> Active</label>
      <button className="primary-button" disabled={saving}>{saving ? "Saving..." : editingId ? "Update" : "Create"}</button>
      {editingId && <button type="button" className="back-button" onClick={() => { setEditingId(null); setForm(emptyForm); }}>Cancel</button>}
      {message && <p className="form-message">{message}</p>}
      {error && <p className="form-error">{error}</p>}
    </form>
    <div className="card admin-list">
      <div className="section-heading"><h2>Administrators</h2><button className="row-action" onClick={() => load()} disabled={loading}>Refresh</button></div>
      {loading && !admins ? <p className="empty-text">Loading administrators...</p> : admins?.length === 0 ? <p className="empty-text">No administrators found.</p> : <div className="admin-records">{admins?.map((admin) => <div className="admin-record" key={admin.id}><strong>{admin.username}</strong><span>{admin.role} · {admin.active ? "Active" : "Inactive"} · {formatISTDateTime(admin.created_at)}</span><div><button className="row-action" onClick={() => edit(admin)}>Edit</button><button className="row-action" onClick={() => changeActive(admin)}>{admin.active ? "Deactivate" : "Activate"}</button></div></div>)}</div>}
      {error && admins && <p className="stale-text">Showing the last loaded list. Retry to refresh.</p>}
    </div>
  </section>;
}

export default AdminUsersPanel;
