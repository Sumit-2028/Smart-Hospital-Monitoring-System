import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { API_BASE_URL, formatISTDateTime } from "../config";
import AdminUsersPanel from "../components/AdminUsersPanel";
import AuditLogPanel from "../components/AuditLogPanel";
import ReportsExport from "../components/ReportsExport";

const empty = {
  departments: { name: "", description: "", active: true },
  rooms: { name: "", code: "", room_type: "WAITING_AREA", department_id: "", capacity: 10, warning_percentage: 80, active: true },
  cameras: { name: "", source_type: "WEBCAM", source: "0", room_id: "", active: true, processing_interval: 1 },
  doctors: { name: "", specialty: "", department_id: "", cabin_id: "", work_identifier: "", active: true, available: true },
};

const navigation = [
  { key: "overview", label: "Overview", icon: "⌂" },
  { key: "departments", label: "Departments", icon: "▦" },
  { key: "rooms", label: "Rooms & cabins", icon: "▥" },
  { key: "cameras", label: "Cameras", icon: "◉" },
  { key: "doctors", label: "Doctors", icon: "＋" },
  { key: "reports", label: "Reports", icon: "▤" },
];

const resourceTitles = {
  departments: "Departments",
  rooms: "Rooms and cabins",
  cameras: "Registered cameras",
  doctors: "Doctors",
};

const roomTypes = ["OPD", "WAITING_AREA", "WARD", "EMERGENCY", "DOCTOR_CABIN"];

function errorMessage(error) {
  return error.message === "Failed to fetch" ? "Backend is unreachable. Check that FastAPI is running." : error.message;
}

function AdminPanel() {
  const [token, setToken] = useState(localStorage.getItem("hospital_admin_token") || "");
  const [credentials, setCredentials] = useState({ username: "", password: "" });
  const [activeTab, setActiveTab] = useState("overview");
  const [data, setData] = useState({ departments: [], rooms: [], cabins: [], cameras: [], doctors: [] });
  const [alerts, setAlerts] = useState(null);
  const [form, setForm] = useState(empty.rooms);
  const [editingId, setEditingId] = useState(null);
  const [detailsItem, setDetailsItem] = useState(null);
  const [confirmTarget, setConfirmTarget] = useState(null);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);

  const signOut = useCallback(() => {
    localStorage.removeItem("hospital_admin_token");
    setToken("");
    setCurrentUser(null);
  }, []);

  const request = useCallback(async (resource) => {
    const response = await fetch(`${API_BASE_URL}/api/admin/${resource}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) {
      signOut();
      throw new Error("Admin session expired. Please sign in again.");
    }
    if (!response.ok) throw new Error(body.detail || "Could not load administration data.");
    return body;
  }, [signOut, token]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [departments, rooms, cabins, cameras, doctors, me] = await Promise.all(
        ["departments", "rooms", "cabins", "cameras", "doctors", "me"].map(request),
      );
      setData({ departments, rooms, cabins, cameras, doctors });
      setCurrentUser(me);
      try {
        const alertResponse = await fetch(`${API_BASE_URL}/api/crowd/alerts/active`);
        setAlerts(alertResponse.ok ? (await alertResponse.json()).items || [] : null);
      } catch {
        setAlerts(null);
      }
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, [request]);

  useEffect(() => {
    if (!token) return undefined;
    const timer = setTimeout(() => { void load(); }, 0);
    return () => clearTimeout(timer);
  }, [load, token]);

  const login = async (event) => {
    event.preventDefault();
    setLoginLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credentials),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Admin login failed.");
      localStorage.setItem("hospital_admin_token", body.access_token);
      setToken(body.access_token);
      setCredentials({ username: "", password: "" });
    } catch (loginError) {
      setError(errorMessage(loginError));
    } finally {
      setLoginLoading(false);
    }
  };

  const resetForm = (resource = activeTab) => {
    setEditingId(null);
    setForm(empty[resource] || empty.rooms);
  };

  const editItem = async (item) => {
    setMessage("");
    setError("");
    try {
      const details = activeTab === "cameras" ? await request(`cameras/${item.id}/edit`) : item;
      setForm({ ...empty[activeTab], ...details, department_id: details.department_id || "", cabin_id: details.cabin_id || "", room_id: details.room_id || "" });
      setEditingId(item.id);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (editError) {
      setError(errorMessage(editError));
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    const body = { ...form };
    ["department_id", "room_id", "cabin_id"].forEach((key) => {
      if (key in body) body[key] = body[key] ? Number(body[key]) : null;
    });
    if (activeTab === "rooms") {
      body.capacity = Number(body.capacity);
      body.warning_percentage = Number(body.warning_percentage);
    }
    if (activeTab === "cameras") body.processing_interval = Number(body.processing_interval);
    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/${activeTab}${editingId ? `/${editingId}` : ""}`, {
        method: editingId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      const result = await response.json().catch(() => ({}));
      if (response.status === 401) { signOut(); throw new Error("Admin session expired. Please sign in again."); }
      if (!response.ok) throw new Error(result.detail || "Could not save this record.");
      setMessage(`${resourceTitles[activeTab].replace(/s$/, "")} ${editingId ? "updated" : "created"} successfully.`);
      resetForm();
      await load();
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  };

  const changeActive = async (item, active) => {
    setActionLoading(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/${activeTab}/${item.id}/active?active=${active}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}` },
      });
      const result = await response.json().catch(() => ({}));
      if (response.status === 401) { signOut(); throw new Error("Admin session expired. Please sign in again."); }
      if (!response.ok) throw new Error(result.detail || `Could not ${active ? "restore" : "archive"} this record.`);
      setMessage(`${displayName(item, activeTab)} ${active ? "restored" : "archived"}. Historical readings and events were preserved.`);
      await load();
    } catch (actionError) {
      setError(errorMessage(actionError));
    } finally {
      setActionLoading(false);
      setConfirmTarget(null);
    }
  };

  const switchTab = (tab) => {
    setActiveTab(tab);
    setSearch("");
    setMessage("");
    setError("");
    resetForm(tab);
  };

  const tabs = currentUser?.role === "SUPERADMIN"
    ? [...navigation, { key: "administrators", label: "Admin users", icon: "♙" }, { key: "audit-log", label: "Audit logs", icon: "≡" }]
    : navigation;

  const filteredItems = useMemo(() => {
    if (!data[activeTab]) return [];
    const term = search.trim().toLowerCase();
    if (!term) return data[activeTab];
    return data[activeTab].filter((item) => JSON.stringify(item).toLowerCase().includes(term));
  }, [activeTab, data, search]);

  if (!token) {
    return <main className="admin-login-page"><div className="admin-login-card">
      <div className="admin-brand-mark">SH</div>
      <p className="analytics-label">SECURE ADMINISTRATION</p>
      <h1>Sign in to hospital operations</h1>
      <p className="admin-login-copy">Manage monitoring rooms, cameras, clinicians, reports, and access controls.</p>
      <form className="admin-form" onSubmit={login}>
        <label>Username<input autoComplete="username" required value={credentials.username} onChange={(event) => setCredentials({ ...credentials, username: event.target.value })} /></label>
        <label>Password<input autoComplete="current-password" type="password" required value={credentials.password} onChange={(event) => setCredentials({ ...credentials, password: event.target.value })} /></label>
        <button className="primary-button admin-submit" disabled={loginLoading}>{loginLoading ? "Signing in..." : "Sign in securely"}</button>
      </form>
      {error && <p className="form-error">{error}</p>}
      <Link to="/" className="admin-login-back">← Return to dashboard</Link>
    </div></main>;
  }

  return <main className="admin-shell-page">
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-sidebar-brand"><span className="admin-brand-mark">SH</span><div><strong>Smart Hospital</strong><span>Operations console</span></div></div>
        <div className="admin-sidebar-user"><span className="user-avatar">{(currentUser?.username || "A").slice(0, 1).toUpperCase()}</span><div><strong>{currentUser?.username || "Administrator"}</strong><span>{currentUser?.role || "ADMIN"}</span></div></div>
        <nav className="admin-nav" aria-label="Administration sections">
          <p className="admin-nav-label">WORKSPACE</p>
          {tabs.map((tab) => <button type="button" key={tab.key} className={activeTab === tab.key ? "active" : ""} onClick={() => switchTab(tab.key)}><span className="admin-nav-icon">{tab.icon}</span>{tab.label}</button>)}
        </nav>
        <div className="admin-sidebar-footer"><Link to="/" className="admin-sidebar-link">← Live dashboard</Link><button type="button" className="admin-sidebar-link" onClick={signOut}>↪ Sign out</button></div>
      </aside>

      <section className="admin-main">
        <header className="admin-topbar"><div><p className="analytics-label">ADMINISTRATION</p><h1>{activeTab === "overview" ? "Operations overview" : tabLabel(activeTab)}</h1></div><div className="admin-topbar-actions"><span className="admin-secure-status"><span /> Secure session</span><Link to="/" className="back-button">View dashboard</Link></div></header>
        {error && <div className="admin-notice admin-notice-error" role="alert">{error}<button type="button" onClick={() => setError("")}>×</button></div>}
        {message && <div className="admin-notice admin-notice-success" role="status">{message}<button type="button" onClick={() => setMessage("")}>×</button></div>}
        {loading && !currentUser ? <div className="admin-loading card">Loading administration workspace...</div> : activeTab === "overview" ? <Overview data={data} alerts={alerts} onNavigate={switchTab} /> : activeTab === "reports" ? <ReportsExport token={token} rooms={data.rooms} cameras={data.cameras} onSessionExpired={signOut} /> : activeTab === "administrators" ? <AdminUsersPanel token={token} onSessionExpired={signOut} /> : activeTab === "audit-log" ? <AuditLogPanel token={token} onSessionExpired={signOut} /> : <ManagementView resource={activeTab} items={filteredItems} data={data} form={form} setForm={setForm} editingId={editingId} saving={saving} actionLoading={actionLoading} search={search} setSearch={setSearch} onSubmit={submit} onEdit={editItem} onView={setDetailsItem} onArchive={(item) => setConfirmTarget({ item, resource: activeTab })} onRestore={(item) => void changeActive(item, true)} onCancel={() => resetForm()} onAdd={() => resetForm()} />}
      </section>
    </div>
    {confirmTarget && <ConfirmDialog item={confirmTarget.item} resource={confirmTarget.resource} loading={actionLoading} onCancel={() => setConfirmTarget(null)} onConfirm={() => void changeActive(confirmTarget.item, false)} />}
    {detailsItem && <DetailsDialog item={detailsItem} data={data} onClose={() => setDetailsItem(null)} />}
  </main>;
}

function Overview({ data, alerts, onNavigate }) {
  const activeCameras = data.cameras.filter((camera) => camera.active !== false);
  const activeRooms = data.rooms.filter((room) => room.active !== false);
  const cabins = data.rooms.filter((room) => room.room_type === "DOCTOR_CABIN");
  const connected = activeCameras.filter((camera) => camera.status === "CONNECTED").length;
  const stale = activeCameras.filter((camera) => ["STALE", "RECONNECTING", "DISCONNECTED", "ERROR"].includes(camera.status)).length;
  return <div className="admin-overview">
    <div className="admin-welcome"><div><p className="muted-text">Today’s command center</p><h2>Keep every care space ready.</h2><p>Configure the hospital estate and review monitoring health from one place.</p></div><button type="button" className="primary-button" onClick={() => onNavigate("rooms")}>Configure rooms <span>→</span></button></div>
    <div className="admin-stat-grid"><StatCard label="Departments" value={data.departments.length} icon="▦" tone="blue" /><StatCard label="Rooms & cabins" value={activeRooms.length} detail={`${cabins.length} doctor cabins`} icon="▥" tone="teal" /><StatCard label="Active cameras" value={activeCameras.length} detail={`${connected} connected${stale ? ` · ${stale} need attention` : ""}`} icon="◉" tone={stale ? "amber" : "green"} /><StatCard label="Active alerts" value={alerts === null ? "—" : alerts.length} detail={alerts === null ? "Unable to load live alerts" : "Requires attention"} icon="!" tone={alerts?.length ? "red" : "green"} /></div>
    <div className="admin-overview-columns">
      <section className="card admin-overview-card"><div className="admin-card-heading"><div><p className="analytics-label">MONITORING HEALTH</p><h3>Camera connection status</h3></div><button type="button" className="row-action" onClick={() => onNavigate("cameras")}>Manage cameras</button></div>{activeCameras.length === 0 ? <EmptyState text="No active cameras are registered." /> : <div className="health-list">{activeCameras.slice(0, 5).map((camera) => <div className="health-row" key={camera.id}><span className={`health-dot ${healthTone(camera.status)}`} /><div><strong>{camera.name}</strong><span>{roomName(data.rooms, camera.room_id)}</span></div><StatusBadge value={camera.status || "STOPPED"} /></div>)}</div>}</section>
      <section className="card admin-overview-card"><div className="admin-card-heading"><div><p className="analytics-label">QUICK ACTIONS</p><h3>Common tasks</h3></div></div><div className="quick-actions"><QuickAction label="Add a department" detail="Organize clinical services" onClick={() => onNavigate("departments")} /><QuickAction label="Register a camera" detail="Connect another monitoring feed" onClick={() => onNavigate("cameras")} /><QuickAction label="Manage doctors" detail="Assign cabins and availability" onClick={() => onNavigate("doctors")} /></div></section>
    </div>
  </div>;
}

function StatCard({ label, value, detail, icon, tone }) { return <article className={`admin-stat-card tone-${tone}`}><span className="admin-stat-icon">{icon}</span><div><p>{label}</p><strong>{value}</strong><span>{detail || "Configured records"}</span></div></article>; }
function QuickAction({ label, detail, onClick }) { return <button type="button" className="quick-action" onClick={onClick}><span><strong>{label}</strong><small>{detail}</small></span><b>→</b></button>; }

function ManagementView({ resource, items, data, form, setForm, editingId, saving, actionLoading, search, setSearch, onSubmit, onEdit, onView, onArchive, onRestore, onCancel, onAdd }) {
  return <div className="management-view">
    <div className="management-heading"><div><p className="muted-text">{resource === "rooms" ? "Physical spaces and doctor cabins" : "Configuration records"}</p><h2>{resourceTitles[resource]}</h2></div><button type="button" className="primary-button" onClick={onAdd}>＋ Add {resource === "rooms" ? "room or cabin" : singular(resource)}</button></div>
    <div className="management-toolbar"><div className="search-box"><span>⌕</span><input aria-label={`Search ${resourceTitles[resource]}`} placeholder={`Search ${resourceTitles[resource].toLowerCase()}...`} value={search} onChange={(event) => setSearch(event.target.value)} /></div><span className="record-count">{items.length} record{items.length === 1 ? "" : "s"}</span></div>
    <div className="management-layout">
      <form className="card admin-form admin-editor-card" onSubmit={onSubmit}><div className="editor-heading"><div><p className="analytics-label">{editingId ? "EDIT RECORD" : "NEW RECORD"}</p><h3>{editingId ? `Edit ${singular(resource)}` : `Add ${resource === "rooms" ? "room or cabin" : singular(resource)}`}</h3></div>{editingId && <span className="editing-badge">Editing</span>}</div><FormFields resource={resource} form={form} setForm={setForm} data={data} />{resource === "rooms" && <p className="form-help">Rooms marked as <strong>DOCTOR_CABIN</strong> appear in doctor assignment options.</p>}{resource === "cameras" && <p className="form-help">Stream credentials are never shown in the camera list after saving.</p>}<div className="editor-actions"><button className="primary-button" disabled={saving}>{saving ? "Saving..." : editingId ? "Save changes" : "Create record"}</button>{editingId && <button type="button" className="back-button" onClick={onCancel}>Cancel</button>}</div></form>
      <section className="card admin-table-card"><div className="admin-card-heading"><div><p className="analytics-label">DIRECTORY</p><h3>{resourceTitles[resource]}</h3></div><span className="muted-text">{items.length} shown</span></div>{items.length === 0 ? <EmptyState text={search ? "No records match your search." : `No ${resourceTitles[resource].toLowerCase()} configured yet.`} action={!search ? onAdd : undefined} /> : <ResourceTable resource={resource} items={items} data={data} actionLoading={actionLoading} onEdit={onEdit} onView={onView} onArchive={onArchive} onRestore={onRestore} />}</section>
    </div>
  </div>;
}

function FormFields({ resource, form, setForm, data }) {
  const update = (key, value) => setForm({ ...form, [key]: value });
  if (resource === "departments") return <><Field label="Department name"><input required maxLength="120" value={form.name} onChange={(event) => update("name", event.target.value)} /></Field><Field label="Description"><textarea maxLength="500" rows="4" value={form.description || ""} onChange={(event) => update("description", event.target.value)} /></Field><ActiveField form={form} update={update} /></>;
  if (resource === "rooms") return <><Field label="Room name"><input required maxLength="120" value={form.name} onChange={(event) => update("name", event.target.value)} /></Field><Field label="Room code"><input maxLength="80" placeholder="Optional internal code" value={form.code || ""} onChange={(event) => update("code", event.target.value)} /></Field><Field label="Room type"><select value={form.room_type} onChange={(event) => update("room_type", event.target.value)}>{roomTypes.map((type) => <option key={type}>{type}</option>)}</select></Field><Field label="Department"><select value={form.department_id || ""} onChange={(event) => update("department_id", event.target.value)}><option value="">Unassigned</option>{data.departments.filter((item) => item.active !== false).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></Field><div className="form-row"><Field label="Capacity"><input required min="1" type="number" value={form.capacity} onChange={(event) => update("capacity", event.target.value)} /></Field><Field label="Warning %"><input required min="1" max="100" type="number" value={form.warning_percentage} onChange={(event) => update("warning_percentage", event.target.value)} /></Field></div><ActiveField form={form} update={update} /></>;
  if (resource === "cameras") return <><Field label="Camera name"><input required maxLength="120" value={form.name} onChange={(event) => update("name", event.target.value)} /></Field><Field label="Source type"><select value={form.source_type} onChange={(event) => update("source_type", event.target.value)}><option>WEBCAM</option><option>IP_STREAM</option></select></Field><Field label={form.source_type === "WEBCAM" ? "Device index" : "Stream URL"}><input required value={form.source || ""} onChange={(event) => update("source", event.target.value)} /></Field><Field label="Assigned room"><select required value={form.room_id || ""} onChange={(event) => update("room_id", event.target.value)}><option value="">Select an active room</option>{data.rooms.filter((item) => item.active !== false).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></Field><Field label="Processing interval"><input min="1" max="60" type="number" value={form.processing_interval || 1} onChange={(event) => update("processing_interval", event.target.value)} /></Field><ActiveField form={form} update={update} /></>;
  return <><Field label="Doctor name"><input required maxLength="160" value={form.name} onChange={(event) => update("name", event.target.value)} /></Field><Field label="Specialty"><input required maxLength="160" value={form.specialty} onChange={(event) => update("specialty", event.target.value)} /></Field><Field label="Department"><select value={form.department_id || ""} onChange={(event) => update("department_id", event.target.value)}><option value="">Unassigned</option>{data.departments.filter((item) => item.active !== false).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></Field><Field label="Doctor cabin"><select value={form.cabin_id || ""} onChange={(event) => update("cabin_id", event.target.value)}><option value="">No cabin assigned</option>{data.cabins.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></Field><Field label="Work identifier"><input maxLength="120" placeholder="Optional" value={form.work_identifier || ""} onChange={(event) => update("work_identifier", event.target.value)} /></Field><div className="checkbox-stack"><label className="checkbox-label"><input type="checkbox" checked={form.available !== false} onChange={(event) => update("available", event.target.checked)} /> Available</label><label className="checkbox-label"><input type="checkbox" checked={form.active !== false} onChange={(event) => update("active", event.target.checked)} /> Active profile</label></div></>;
}

function Field({ label, children }) { return <label className="admin-field">{label}{children}</label>; }
function ActiveField({ form, update }) { return <label className="checkbox-label admin-active-field"><input type="checkbox" checked={form.active !== false} onChange={(event) => update("active", event.target.checked)} /> Active record</label>; }

function ResourceTable({ resource, items, data, actionLoading, onEdit, onView, onArchive, onRestore }) {
  return <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Name</th><th>Details</th><th>Status</th><th className="actions-column">Actions</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.name}</strong><small>{resource === "rooms" && item.code ? item.code : resource === "cameras" ? `ID #${item.id}` : resource === "doctors" && item.work_identifier ? item.work_identifier : ""}</small></td><td><span className="table-detail">{detailsFor(resource, item, data)}</span></td><td><StatusBadge value={statusFor(resource, item)} /></td><td className="table-actions"><button type="button" className="row-action" onClick={() => onView(item)}>View</button><button type="button" className="row-action" onClick={() => onEdit(item)}>Edit</button>{item.active === false ? <button type="button" className="row-action" disabled={actionLoading} onClick={() => onRestore(item)}>Restore</button> : <button type="button" className="row-action row-action-danger" disabled={actionLoading} onClick={() => onArchive(item)}>Archive</button>}</td></tr>)}</tbody></table><p className="table-footnote">Archive deactivates the record and preserves monitoring history.</p></div>;
}

function ConfirmDialog({ item, resource, loading, onCancel, onConfirm }) { return <div className="modal-backdrop" role="presentation"><div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="archive-title"><div className="modal-icon warning">!</div><p className="analytics-label">SAFE ARCHIVE</p><h2 id="archive-title">Archive {displayName(item, resource)}?</h2><p>This will deactivate <strong>{item.name}</strong> and remove it from active selections. Historical readings, events, and reports will remain intact.</p><div className="modal-actions"><button type="button" className="back-button" onClick={onCancel} disabled={loading}>Cancel</button><button type="button" className="danger-button" onClick={onConfirm} disabled={loading}>{loading ? "Archiving..." : "Archive record"}</button></div></div></div>; }

function DetailsDialog({ item, data, onClose }) { const entries = Object.entries(item).filter(([key, value]) => value !== null && value !== undefined && key !== "source"); return <div className="modal-backdrop" role="presentation"><div className="modal-card details-modal" role="dialog" aria-modal="true" aria-labelledby="details-title"><div className="modal-card-header"><div><p className="analytics-label">RECORD DETAILS</p><h2 id="details-title">{item.name}</h2></div><button type="button" className="modal-close" onClick={onClose} aria-label="Close details">×</button></div><div className="details-grid">{entries.map(([key, value]) => <div key={key}><span>{humanize(key)}</span><strong>{formatDetail(key, value, data)}</strong></div>)}</div><button type="button" className="back-button modal-close-button" onClick={onClose}>Close</button></div></div>; }

function EmptyState({ text, action }) { return <div className="admin-empty"><span>○</span><p>{text}</p>{action && <button type="button" className="row-action" onClick={action}>Add first record</button>}</div>; }
function StatusBadge({ value }) { const text = String(value || "UNKNOWN").replaceAll("_", " "); return <span className={`admin-status status-${String(value || "unknown").toLowerCase()}`}>{text}</span>; }
function healthTone(status) { return status === "CONNECTED" ? "healthy" : ["STALE", "RECONNECTING"].includes(status) ? "warning" : "offline"; }
function roomName(rooms, id) { return rooms.find((room) => room.id === id)?.name || "Room not assigned"; }
function statusFor(resource, item) { if (resource === "cameras") return item.active === false ? "INACTIVE" : item.status || "STOPPED"; if (resource === "doctors") return item.active === false ? "INACTIVE" : item.available === false ? "UNAVAILABLE" : "AVAILABLE"; return item.active === false ? "INACTIVE" : "ACTIVE"; }
function detailsFor(resource, item, data) { if (resource === "departments") return item.description || "No description"; if (resource === "rooms") return `${item.room_type?.replaceAll("_", " ")} · Capacity ${item.capacity} · ${data.departments.find((dept) => dept.id === item.department_id)?.name || "No department"}`; if (resource === "cameras") return `${item.source_type} · ${roomName(data.rooms, item.room_id)}`; return `${item.specialty} · ${data.cabins.find((cabin) => cabin.id === item.cabin_id)?.name || "No cabin"}`; }
function displayName(item, resource) { return `${singular(resource)} “${item.name}”`; }
function singular(resource) { return resource === "rooms" ? "room" : resource.slice(0, -1); }
function tabLabel(tab) { return navigation.concat([{ key: "administrators", label: "Admin users" }, { key: "audit-log", label: "Audit logs" }]).find((item) => item.key === tab)?.label || "Administration"; }
function humanize(value) { return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function formatDetail(key, value, data) { if (key === "department_id") return data.departments.find((item) => item.id === value)?.name || "Unassigned"; if (key === "cabin_id") return data.rooms.find((item) => item.id === value)?.name || "Unassigned"; if (key === "room_id") return data.rooms.find((item) => item.id === value)?.name || "Unassigned"; if (typeof value === "boolean") return value ? "Yes" : "No"; if (key.endsWith("_at")) return formatISTDateTime(value); return String(value); }

export default AdminPanel;
