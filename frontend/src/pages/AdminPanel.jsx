import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { API_BASE_URL } from "../config";

const empty = {
  departments: { name: "", description: "", active: true },
  rooms: { name: "", code: "", room_type: "WAITING_AREA", department_id: "", capacity: 10, warning_percentage: 80, active: true },
  cameras: { name: "", source_type: "WEBCAM", source: "0", room_id: "", active: true },
  doctors: { name: "", specialty: "", department_id: "", cabin_id: "", active: true, available: true },
};

function AdminPanel() {
  const [token, setToken] = useState(localStorage.getItem("hospital_admin_token") || "");
  const [credentials, setCredentials] = useState({ username: "", password: "" });
  const [activeTab, setActiveTab] = useState("rooms");
  const [data, setData] = useState({ departments: [], rooms: [], cabins: [], cameras: [], doctors: [] });
  const [form, setForm] = useState(empty.rooms);
  const [editingId, setEditingId] = useState(null);
  const [message, setMessage] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

  const load = useCallback(() => Promise.all(["departments", "rooms", "cabins", "cameras", "doctors"].map((resource) => fetch(`${API_BASE_URL}/api/admin/${resource}`, { headers: { Authorization: `Bearer ${token}` } }).then((response) => { if (response.status === 401) { localStorage.removeItem("hospital_admin_token"); setToken(""); throw new Error("Admin session expired. Please sign in again."); } if (!response.ok) throw new Error("Could not load admin data"); return response.json(); }))).then(([departments, rooms, cabins, cameras, doctors]) => setData({ departments, rooms, cabins, cameras, doctors })).catch((error) => setMessage(error.message)), [token]);

  useEffect(() => { if (token) load(); }, [load, token]);

  const login = (event) => {
    event.preventDefault();
    setLoginLoading(true);
    fetch(`${API_BASE_URL}/api/admin/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(credentials) })
      .then((response) => response.json().then((result) => { if (!response.ok) throw new Error(result.detail || "Admin login failed"); return result; }))
      .then((result) => { localStorage.setItem("hospital_admin_token", result.access_token); setToken(result.access_token); })
      .catch((error) => setMessage(error.message === "Failed to fetch" ? "Backend is unreachable. Check that FastAPI is running." : error.message))
      .finally(() => setLoginLoading(false));
  };

  const editItem = (item) => {
    if (activeTab === "cameras") {
      fetch(`${API_BASE_URL}/api/admin/cameras/${item.id}/edit`, { headers: { Authorization: `Bearer ${token}` } }).then((response) => { if (response.status === 401) { localStorage.removeItem("hospital_admin_token"); setToken(""); throw new Error("Admin session expired. Please sign in again."); } return response.json(); }).then((details) => { setForm(details); setEditingId(item.id); }).catch((error) => setMessage(error.message));
    } else {
      setForm({ ...empty[activeTab], ...item, department_id: item.department_id || "", cabin_id: item.cabin_id || "" });
      setEditingId(item.id);
    }
  };

  const submit = (event) => {
    event.preventDefault();
    const body = { ...form };
    ["department_id", "room_id", "cabin_id"].forEach((key) => { if (key in body) body[key] = body[key] ? Number(body[key]) : null; });
    if (activeTab === "rooms") { body.capacity = Number(body.capacity); body.warning_percentage = Number(body.warning_percentage); }
    const url = `${API_BASE_URL}/api/admin/${activeTab}${editingId ? `/${editingId}` : ""}`;
    fetch(url, { method: editingId ? "PUT" : "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(body) })
      .then((response) => response.json().then((result) => { if (response.status === 401) { localStorage.removeItem("hospital_admin_token"); setToken(""); throw new Error("Admin session expired. Please sign in again."); } if (!response.ok) throw new Error(result.detail || "Save failed"); return result; }))
      .then(() => { setMessage("Saved"); setEditingId(null); setForm(empty[activeTab]); load(); })
      .catch((error) => setMessage(error.message));
  };

  const toggleActive = (item) => fetch(`${API_BASE_URL}/api/admin/${activeTab}/${item.id}/active?active=${!item.active}`, { method: "PATCH", headers: { Authorization: `Bearer ${token}` } }).then((response) => response.json().then((result) => { if (response.status === 401) { localStorage.removeItem("hospital_admin_token"); setToken(""); throw new Error("Admin session expired. Please sign in again."); } if (!response.ok) throw new Error(result.detail || "Could not change active status"); return result; })).then(load).catch((error) => setMessage(error.message));

  const switchTab = (tab) => { setActiveTab(tab); setEditingId(null); setForm(empty[tab]); setMessage(""); };
  const tabs = ["departments", "rooms", "cameras", "doctors"];
  const fields = activeTab === "departments" ? [{ key: "name", label: "Name" }, { key: "description", label: "Description" }] : activeTab === "rooms" ? [{ key: "name", label: "Name" }, { key: "code", label: "Code" }, { key: "capacity", label: "Capacity", type: "number" }, { key: "warning_percentage", label: "Warning %", type: "number" }] : activeTab === "cameras" ? [{ key: "name", label: "Name" }, { key: "source", label: "Device index or stream URL" }] : [{ key: "name", label: "Doctor name" }, { key: "specialty", label: "Specialty" }];

  if (!token) return <main className="admin-page"><div className="page-header"><div><p className="analytics-label">ADMINISTRATION</p><h1>Admin sign in</h1></div><Link to="/" className="back-button">← Dashboard</Link></div><form className="card admin-form" onSubmit={login}><label>Username<input value={credentials.username} onChange={(event) => setCredentials({ ...credentials, username: event.target.value })} /></label><label>Password<input type="password" value={credentials.password} onChange={(event) => setCredentials({ ...credentials, password: event.target.value })} /></label><button className="primary-button" disabled={loginLoading}>{loginLoading ? "Signing in..." : "Sign in"}</button>{message && <p className="form-error">{message}</p>}</form></main>;

  return <main className="admin-page"><div className="page-header"><div><p className="analytics-label">ADMINISTRATION</p><h1>Hospital configuration</h1><p>Manage rooms, cameras, departments, doctors and cabins.</p></div><div className="admin-links"><Link to="/" className="back-button">← Dashboard</Link><button className="back-button" onClick={() => { localStorage.removeItem("hospital_admin_token"); setToken(""); }}>Sign out</button></div></div><div className="admin-tabs">{tabs.map((tab) => <button key={tab} className={activeTab === tab ? "period-active" : ""} onClick={() => switchTab(tab)}>{tab}</button>)}</div><div className="admin-layout"><form className="card admin-form" onSubmit={submit}><h2>{editingId ? "Edit" : "Add"} {activeTab.slice(0, -1)}</h2>{fields.map((field) => <label key={field.key}>{field.label}<input type={field.type || "text"} value={form[field.key] ?? ""} onChange={(event) => setForm({ ...form, [field.key]: event.target.value })} required={field.key !== "code"} /></label>)}{activeTab === "rooms" && <><label>Room type<select value={form.room_type} onChange={(event) => setForm({ ...form, room_type: event.target.value })}>{["OPD", "WAITING_AREA", "WARD", "EMERGENCY", "DOCTOR_CABIN"].map((type) => <option key={type}>{type}</option>)}</select></label><label>Department<select value={form.department_id} onChange={(event) => setForm({ ...form, department_id: event.target.value })}><option value="">None</option>{data.departments.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label></>}{activeTab === "cameras" && <><label>Source type<select value={form.source_type} onChange={(event) => setForm({ ...form, source_type: event.target.value })}><option>WEBCAM</option><option>IP_STREAM</option></select></label><label>Room<select value={form.room_id} onChange={(event) => setForm({ ...form, room_id: event.target.value })} required><option value="">Select room first</option>{data.rooms.filter((item) => item.active).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label></>}{activeTab === "doctors" && <><label>Department<select value={form.department_id} onChange={(event) => setForm({ ...form, department_id: event.target.value })}><option value="">None</option>{data.departments.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>Cabin<select value={form.cabin_id} onChange={(event) => setForm({ ...form, cabin_id: event.target.value })}><option value="">None</option>{data.cabins.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>{data.cabins.length === 0 && <p className="form-error">No active doctor cabins found. Create a room with type DOCTOR_CABIN first.</p>}</> }<button className="primary-button">{editingId ? "Update" : "Save"}</button>{editingId && <button type="button" className="back-button" onClick={() => { setEditingId(null); setForm(empty[activeTab]); }}>Cancel</button>}{message && <p className="form-message">{message}</p>}</form><div className="card admin-list"><h2>Registered {activeTab}</h2>{data[activeTab].length === 0 ? <p className="empty-text">No records yet.</p> : <div className="admin-records">{data[activeTab].map((item) => <div className="admin-record" key={item.id}><strong>{item.name}</strong><span>{item.room_type || item.specialty || item.status || (item.active ? "Active" : "Inactive")}</span><div><button className="row-action" onClick={() => editItem(item)}>Edit</button><button className="row-action" onClick={() => toggleActive(item)}>{item.active === false ? "Activate" : "Deactivate"}</button></div></div>)}</div>}</div></div></main>;
}

export default AdminPanel;
