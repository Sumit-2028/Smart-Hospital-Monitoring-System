import { useMemo, useState } from "react";

import { API_BASE_URL, getISTDateValue } from "../config";

const reportTypes = [
  { value: "crowd-readings.csv", label: "Crowd readings" },
  { value: "congestion-events.csv", label: "Congestion events" },
  { value: "daily-summary.csv", label: "Daily summary" },
];

function ReportsExport({ token, rooms, cameras, onSessionExpired }) {
  const today = getISTDateValue();
  const [reportType, setReportType] = useState(reportTypes[0].value);
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState(today);
  const [roomId, setRoomId] = useState("");
  const [cameraId, setCameraId] = useState("");
  const [status, setStatus] = useState("ALL");
  const [exporting, setExporting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const availableCameras = useMemo(
    () => cameras.filter((camera) => !roomId || String(camera.room_id) === String(roomId)),
    [cameras, roomId],
  );

  const exportReport = async (event) => {
    event.preventDefault();
    setMessage("");
    setError("");
    if (startDate && endDate && startDate > endDate) {
      setError("Start date must not be after the end date.");
      return;
    }

    setExporting(true);
    try {
      const params = new URLSearchParams();
      if (startDate) params.set("start_date", startDate);
      if (endDate) params.set("end_date", endDate);
      if (roomId) params.set("room_id", roomId);
      if (cameraId) params.set("camera_id", cameraId);
      if (reportType === "congestion-events.csv") params.set("status", status);

      const response = await fetch(`${API_BASE_URL}/api/reports/${reportType}?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.status === 401) {
        onSessionExpired();
        throw new Error("Admin session expired. Please sign in again.");
      }
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.detail || "Could not generate the report.");
      }

      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || reportType;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setMessage(`${filename} downloaded.`);
    } catch (requestError) {
      setError(requestError.message === "Failed to fetch" ? "Backend is unreachable. Check that FastAPI is running." : requestError.message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <section className="card reports-panel">
      <div className="section-heading">
        <div>
          <p className="analytics-label">REPORTS</p>
          <h2>Export monitoring data</h2>
        </div>
        <span className="muted-text">CSV downloads use IST date boundaries.</span>
      </div>
      <form className="report-controls" onSubmit={exportReport}>
        <label>Report<select value={reportType} onChange={(event) => setReportType(event.target.value)}>{reportTypes.map((report) => <option key={report.value} value={report.value}>{report.label}</option>)}</select></label>
        <label>Start date<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
        <label>End date<input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        <label>Room<select value={roomId} onChange={(event) => { setRoomId(event.target.value); setCameraId(""); }}><option value="">All rooms</option>{rooms.filter((room) => room.active !== false).map((room) => <option value={room.id} key={room.id}>{room.name}</option>)}</select></label>
        <label>Camera<select value={cameraId} onChange={(event) => setCameraId(event.target.value)}><option value="">All cameras</option>{availableCameras.filter((camera) => camera.active !== false).map((camera) => <option value={camera.id} key={camera.id}>{camera.name}</option>)}</select></label>
        {reportType === "congestion-events.csv" && <label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}><option>ALL</option><option>ACTIVE</option><option>RESOLVED</option></select></label>}
        <button className="primary-button" disabled={exporting}>{exporting ? "Generating..." : "Download CSV"}</button>
      </form>
      <p className="report-help">Room and camera filters are optional. Daily summaries include reading averages, peaks, event counts and congestion duration.</p>
      {message && <p className="form-message">{message}</p>}
      {error && <p className="form-error">{error}</p>}
    </section>
  );
}

export default ReportsExport;
