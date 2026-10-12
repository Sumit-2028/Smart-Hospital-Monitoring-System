import { useEffect, useState } from "react";

import { API_BASE_URL, WS_URL, formatISTTime } from "../config";

function MultiRoomOverview() {
  const [rooms, setRooms] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const loadRooms = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/monitoring/rooms`);
        if (!response.ok) throw new Error("Could not load rooms");
        const data = await response.json();
        if (!cancelled) {
          setRooms(data);
          setError("");
        }
      } catch (fetchError) {
        if (!cancelled && fetchError.name !== "AbortError") setError("Room monitoring is unavailable.");
      }
    };
    loadRooms();
    const refreshTimer = window.setInterval(loadRooms, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(refreshTimer);
    };
  }, []);

  useEffect(() => {
    const socket = new WebSocket(WS_URL);
    socket.onmessage = (event) => {
      try {
        const update = JSON.parse(event.data);
        if (!update.room_id) return;
        setRooms((current) => current.map((room) => {
          if (room.room_id !== update.room_id) return room;
          const camera = update.camera_id && room.camera?.id === update.camera_id
            ? { ...room.camera, status: update.camera_status ?? room.camera.status, last_frame_at: update.last_frame_at ?? room.camera.last_frame_at }
            : room.camera;
          return {
            ...room,
            ...(update.event_type === "crowd.reading" ? {
              current_count: update.person_count,
              status: update.status,
              last_update: update.timestamp,
              capacity: update.capacity ?? room.capacity,
            } : {}),
            camera,
          };
        }));
      } catch {
        setError("Received an invalid room update.");
      }
    };
    return () => socket.close();
  }, []);

  if (error) return <div className="system-message">{error}</div>;
  if (!rooms.length) return <section className="room-overview card"><p className="label">ROOM MONITORING</p><p className="empty-text">No active rooms configured yet.</p></section>;

  return (
    <section className="room-overview">
      <div className="section-title">
        <div><p className="label">MULTI-ROOM MONITORING</p><h2>Active Rooms</h2></div>
        <span className="live-indicator">LIVE</span>
      </div>
      <div className="room-grid">
        {rooms.map((room) => {
          const percentage = Math.min((room.current_count / room.capacity) * 100, 100);
          const stale = !room.camera || room.camera.status !== "CONNECTED";
          const feedStatus = room.camera?.status || "UNAVAILABLE";
          return <article className="room-card card" key={room.room_id}>
            <div className="room-card-heading"><div><p className="label">{room.room_type}</p><h3>{room.room_name}</h3></div><span className={`status-badge ${room.status === "NORMAL" ? "normal" : "danger"}`}>{room.status}</span></div>
            <p className="room-department">{room.department_name || "Unassigned department"}</p>
            <div className="room-count">{room.current_count}<small> / {room.capacity}</small></div>
            <div className="progress-bar"><div className={`progress-fill ${room.status === "NORMAL" ? "" : "danger-fill"}`} style={{ width: `${percentage}%` }} /></div>
            <p className={stale ? "feed-stale" : "feed-ok"}>{stale ? `FEED ${feedStatus}` : "FEED CONNECTED"}</p>
            <p className="last-update">Last frame: {room.camera?.last_frame_at ? formatISTTime(room.camera.last_frame_at) : "--"}</p>
            <p className="last-update">Last reading: {room.last_update ? formatISTTime(room.last_update) : "--"}</p>
          </article>;
        })}
      </div>
    </section>
  );
}

export default MultiRoomOverview;
