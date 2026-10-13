import { useCallback, useEffect, useState } from "react";

import { API_BASE_URL, WS_URL } from "../config";

function isNewerTimestamp(nextValue, currentValue) {
  if (!nextValue) return false;
  if (!currentValue) return true;
  return new Date(nextValue).getTime() > new Date(currentValue).getTime();
}

function recalculate(summary, rooms) {
  const freshRooms = rooms.filter((room) => room.has_fresh_reading && typeof room.current_count === "number");
  const normalRoomCount = freshRooms.filter((room) => room.crowd_status === "NORMAL").length;
  const congestedRoomCount = freshRooms.filter((room) => room.crowd_status === "CONGESTED").length;
  const latestReadingAt = rooms
    .map((room) => room.last_reading_at)
    .filter(Boolean)
    .sort((left, right) => new Date(right).getTime() - new Date(left).getTime())[0] || null;
  return {
    ...summary,
    rooms,
    total_count: freshRooms.reduce((total, room) => total + room.current_count, 0),
    complete_room_count: freshRooms.length,
    incomplete_room_count: rooms.length - freshRooms.length,
    normal_room_count: normalRoomCount,
    congested_room_count: congestedRoomCount,
    is_complete: rooms.every((room) => room.has_fresh_reading),
    latest_reading_at: latestReadingAt,
  };
}

export function applyCrowdReading(summary, update) {
  if (!summary || update?.event_type !== "crowd.reading" || !update.room_id || typeof update.person_count !== "number") {
    return summary;
  }
  const currentRoom = summary.rooms.find((room) => room.room_id === update.room_id);
  if (!currentRoom || !isNewerTimestamp(update.timestamp, currentRoom.last_reading_at)) {
    return summary;
  }
  const updatedRoom = {
    ...currentRoom,
    current_count: update.person_count,
    crowd_status: update.status,
    monitoring_status: update.status,
    has_fresh_reading: true,
    last_reading_at: update.timestamp,
    last_successful_reading_at: update.timestamp,
    reading_age_seconds: 0,
    capacity: update.capacity ?? currentRoom.capacity,
    warning_percentage: update.warning_percentage ?? currentRoom.warning_percentage,
    reading_camera_id: update.camera_id ?? currentRoom.reading_camera_id,
    camera_status: update.camera_status ?? currentRoom.camera_status,
    occupancy_percentage: currentRoom.capacity > 0 ? Math.round((update.person_count / currentRoom.capacity) * 1000) / 10 : null,
  };
  return recalculate(summary, summary.rooms.map((room) => room.room_id === update.room_id ? updatedRoom : room));
}

export function useHospitalCrowdSummary(onConnectionState) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [connectionState, setConnectionState] = useState("CONNECTING");

  const loadSummary = useCallback(async (signal) => {
    const response = await fetch(`${API_BASE_URL}/api/monitoring/summary`, { signal });
    if (!response.ok) throw new Error("Hospital crowd summary could not be loaded.");
    const data = await response.json();
    setSummary(data);
    setError("");
    return data;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let refreshTimer;
    const initialLoadTimer = window.setTimeout(() => {
      void loadSummary(controller.signal)
        .catch((loadError) => {
          if (loadError.name !== "AbortError") setError(loadError.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 0);
    refreshTimer = window.setInterval(() => {
      void loadSummary(controller.signal).catch((loadError) => {
        if (loadError.name !== "AbortError") setError(loadError.message);
      });
    }, 10000);
    return () => {
      controller.abort();
      window.clearTimeout(initialLoadTimer);
      window.clearInterval(refreshTimer);
    };
  }, [loadSummary]);

  useEffect(() => {
    let socket;
    let reconnectTimer;
    let disposed = false;
    const connect = () => {
      if (disposed) return;
      setConnectionState("CONNECTING");
      socket = new WebSocket(WS_URL);
      socket.onopen = () => {
        setConnectionState("CONNECTED");
        void loadSummary().catch((loadError) => {
          if (loadError.name !== "AbortError") setError(loadError.message);
        });
      };
      socket.onmessage = (event) => {
        try {
          const update = JSON.parse(event.data);
          if (update.event_type === "crowd.reading") setSummary((current) => applyCrowdReading(current, update));
        } catch {
          setError("Received an invalid hospital crowd update.");
        }
      };
      socket.onerror = () => setConnectionState("RECONNECTING");
      socket.onclose = () => {
        setConnectionState("RECONNECTING");
        if (!disposed) reconnectTimer = window.setTimeout(connect, 3000);
      };
    };
    connect();
    return () => {
      disposed = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [loadSummary]);

  useEffect(() => {
    onConnectionState?.(connectionState);
  }, [connectionState, onConnectionState]);

  return { summary, loading, error, connectionState, retry: () => loadSummary() };
}
