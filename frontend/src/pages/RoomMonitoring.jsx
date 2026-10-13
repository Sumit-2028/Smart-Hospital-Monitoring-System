import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import CongestionEvents from "../components/CongestionEvents";
import CameraStream from "../components/CameraStream";
import CrowdChart from "../components/CrowdChart";
import HourlyChart from "../components/HourlyChart";
import { API_BASE_URL, formatISTDateTime, getISTDateValue, WS_URL } from "../config";

function RoomMonitoring() {
  const { roomId } = useParams();
  const [room, setRoom] = useState(null);
  const [today, setToday] = useState(null);
  const [dailyHistory, setDailyHistory] = useState([]);
  const [hourlyHistory, setHourlyHistory] = useState([]);
  const [events, setEvents] = useState([]);
  const [selectedDate, setSelectedDate] = useState(getISTDateValue());
  const [selectedCameraId, setSelectedCameraId] = useState("");
  const [loading, setLoading] = useState(true);
  const [hourlyLoading, setHourlyLoading] = useState(true);
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [socketState, setSocketState] = useState("CONNECTING");

  const loadEvents = useCallback(async (signal) => {
    const response = await fetch(
      `${API_BASE_URL}/api/crowd/events/history?room_id=${encodeURIComponent(roomId)}&status=ALL&limit=100`,
      { signal },
    );
    if (!response.ok) throw new Error("Room alert history could not be loaded.");
    const data = await response.json();
    setEvents(data.items || []);
  }, [roomId]);

  useEffect(() => {
    const controller = new AbortController();
    const loadRoom = async () => {
      try {
        const [roomResponse, summaryResponse, dailyResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/monitoring/rooms/${encodeURIComponent(roomId)}`, { signal: controller.signal }),
          fetch(`${API_BASE_URL}/api/crowd/today?room_id=${encodeURIComponent(roomId)}`, { signal: controller.signal }),
          fetch(`${API_BASE_URL}/api/crowd/history?days=30&room_id=${encodeURIComponent(roomId)}`, { signal: controller.signal }),
        ]);
        if (roomResponse.status === 404) {
          setNotFound(true);
          throw new Error("This monitoring room was not found or is inactive.");
        }
        if (!roomResponse.ok || !summaryResponse.ok || !dailyResponse.ok) {
          throw new Error("Room monitoring data could not be loaded.");
        }
        const [roomData, summaryData, dailyData] = await Promise.all([
          roomResponse.json(),
          summaryResponse.json(),
          dailyResponse.json(),
        ]);
        setRoom(roomData);
        setToday(summaryData);
        setDailyHistory(dailyData || []);
        setSelectedCameraId(String(roomData.cameras?.[0]?.id || ""));
        await loadEvents(controller.signal);
        setError("");
      } catch (loadError) {
        if (loadError.name !== "AbortError") setError(loadError.message || "Room monitoring data could not be loaded.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void loadRoom();
    return () => controller.abort();
  }, [loadEvents, roomId]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/api/crowd/history/${encodeURIComponent(selectedDate)}?room_id=${encodeURIComponent(roomId)}`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Hourly room history could not be loaded.");
        return response.json();
      })
      .then(setHourlyHistory)
      .catch((loadError) => {
        if (loadError.name !== "AbortError") setError(loadError.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setHourlyLoading(false);
      });
    return () => controller.abort();
  }, [roomId, selectedDate]);

  useEffect(() => {
    let socket;
    let reconnectTimer;
    let disposed = false;
    let attempts = 0;

    const connect = () => {
      if (disposed) return;
      setSocketState(attempts ? "RECONNECTING" : "CONNECTING");
      socket = new WebSocket(WS_URL);
      socket.onopen = () => {
        attempts = 0;
        setSocketState("CONNECTED");
      };
      socket.onmessage = (message) => {
        try {
          const update = JSON.parse(message.data);
          if (String(update.room_id) !== String(roomId)) return;
          if (update.event_type === "crowd.reading") {
            setRoom((current) => current ? {
              ...current,
              current_count: update.person_count,
              status: update.status,
              last_update: update.timestamp,
              capacity: update.capacity ?? current.capacity,
            } : current);
          }
          if (update.event_type === "camera.status") {
            setRoom((current) => current ? {
              ...current,
              cameras: current.cameras.map((camera) => camera.id === update.camera_id
                ? { ...camera, status: update.camera_status, last_frame_at: update.last_frame_at }
                : camera),
            } : current);
          }
          if (update.event_type?.startsWith("congestion.")) {
            void loadEvents().catch((loadError) => {
              if (loadError.name !== "AbortError") setError(loadError.message);
            });
          }
        } catch {
          setError("An invalid live room update was received.");
        }
      };
      socket.onerror = () => setSocketState("RECONNECTING");
      socket.onclose = () => {
        if (disposed) return;
        attempts += 1;
        if (attempts > 5) {
          setSocketState("DISCONNECTED");
          return;
        }
        reconnectTimer = window.setTimeout(connect, Math.min(3000 * attempts, 15000));
      };
    };

    connect();
    return () => {
      disposed = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [loadEvents, roomId]);

  const selectedCamera = useMemo(
    () => room?.cameras?.find((camera) => String(camera.id) === String(selectedCameraId)) || room?.cameras?.[0] || null,
    [room, selectedCameraId],
  );

  if (loading) return <main className="dashboard room-monitor-page"><div className="room-page-state card">Loading room monitoring...</div></main>;
  if (notFound || !room) return <main className="dashboard room-monitor-page"><div className="room-page-state card"><h1>Room unavailable</h1><p>{error || "This room is not active or could not be found."}</p><Link className="back-button" to="/">Back to Active Rooms</Link></div></main>;

  const occupancy = room.capacity > 0 ? Math.min((room.current_count / room.capacity) * 100, 100) : 0;
  const connectionLabel = socketState === "CONNECTED" ? "LIVE UPDATES CONNECTED" : `LIVE UPDATES ${socketState}`;
  const handleDateChange = (value) => {
    setHourlyLoading(true);
    setSelectedDate(value);
  };

  return <main className="dashboard room-monitor-page">
    <header className="header room-page-header">
      <div><p className="analytics-label">ROOM MONITORING</p><h1>{room.room_name}</h1><p>{room.room_type?.replaceAll("_", " ")} · {room.department_name || "No department assigned"}</p></div>
      <div className="room-page-actions"><span className={`connection ${socketState === "CONNECTED" ? "online" : "offline"}`}><span />{connectionLabel}</span><Link to="/" className="back-button">← Back to Active Rooms</Link></div>
    </header>

    {error && <div className="system-message" role="alert">{error}</div>}

    <section className="room-detail-header card">
      <div><p className="label">ROOM STATUS</p><div className="room-detail-title"><h2>{room.room_name}</h2><span className={`status-badge ${statusBadgeClass(room.status)}`}>{room.status}</span></div><p className="room-detail-copy">{room.department_name || "No department assigned"}{room.doctor ? ` · ${room.doctor.name} (${room.doctor.specialty})` : " · No doctor assigned"}</p></div>
      <div className="room-detail-times"><span>Last reading <strong>{formatISTDateTime(room.last_update)}</strong></span><span>Last frame <strong>{formatISTDateTime(selectedCamera?.last_frame_at)}</strong></span></div>
    </section>

    <div className="room-monitor-layout">
      <CameraPanel roomId={room.room_id} camera={selectedCamera} cameras={room.cameras || []} selectedCameraId={selectedCameraId} onCameraChange={setSelectedCameraId} />
      <section className="room-stats-panel"><div className="section-title"><div><p className="label">LIVE CROWD STATISTICS</p><h2>Current occupancy</h2></div><span className={`status-badge ${statusBadgeClass(room.status)}`}>{room.status}</span></div><div className="room-detail-metric"><strong>{room.current_count}</strong><span>/ {room.capacity} people</span></div><div className="progress-info"><span>Occupancy</span><span>{Math.round(occupancy)}%</span></div><div className="progress-bar"><div className={`progress-fill ${room.status === "NORMAL" ? "" : "danger-fill"}`} style={{ width: `${occupancy}%` }} /></div><div className="room-stat-grid"><Metric label="Warning threshold" value={`${room.warning_threshold} people`} /><Metric label="Today's peak" value={today?.peak_crowd ?? "--"} /><Metric label="Today's average" value={today ? today.average_crowd : "--"} /><Metric label="Readings" value={today?.reading_count ?? "--"} /></div></section>
    </div>

    <section className="room-history-section"><div className="section-title"><div><p className="label">ROOM ANALYTICS</p><h2>Daily trend · last 30 days</h2></div></div><CrowdChart data={dailyHistory} /></section>
    <section className="room-history-section"><div className="section-title"><div><p className="label">HOURLY ANALYSIS</p><h2>Selected day</h2></div><input className="room-date-control" type="date" value={selectedDate} onChange={(event) => handleDateChange(event.target.value)} /></div>{hourlyLoading ? <div className="card room-page-state">Loading hourly room history...</div> : <HourlyChart data={hourlyHistory} selectedDate={selectedDate} setSelectedDate={handleDateChange} />}</section>
    <section className="room-history-section"><div className="section-title"><div><p className="label">ALERT HISTORY</p><h2>Congestion events for {room.room_name}</h2></div></div><CongestionEvents events={events} /></section>
  </main>;
}

function CameraPanel({ roomId, camera, cameras, selectedCameraId, onCameraChange }) {
  const status = camera?.status || "UNAVAILABLE";
  const [retryNonce, setRetryNonce] = useState(0);
  return <section className="card room-camera-panel"><div className="section-title"><div><p className="label">LIVE CAMERA</p><h2>{camera?.name || "No camera assigned"}</h2></div><span className={`camera-status camera-status-${status.toLowerCase()}`}>{status}</span></div>{cameras.length > 1 && <label className="camera-selector">Camera<select value={selectedCameraId} onChange={(event) => onCameraChange(event.target.value)}>{cameras.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>}<div className="camera-viewport"><CameraStream roomId={roomId} cameraId={camera?.id} cameraStatus={status} retryNonce={retryNonce} /></div><div className="camera-panel-footer"><span>Last successful frame: {formatISTDateTime(camera?.last_frame_at)}</span><button type="button" className="back-button" onClick={() => setRetryNonce((value) => value + 1)} disabled={!camera || status !== "CONNECTED"}>Retry preview</button></div></section>;
}

function Metric({ label, value }) { return <div className="room-stat"><span>{label}</span><strong>{value}</strong></div>; }
function statusBadgeClass(status) { return status === "NORMAL" ? "normal" : status === "WARNING" ? "warning" : "danger"; }

export default RoomMonitoring;
