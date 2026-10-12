import { useEffect, useState } from "react";

import { Link } from "react-router-dom";

import TodaySummary from "../components/TodaySummary";

import CrowdChart from "../components/CrowdChart";

import HourlyChart from "../components/HourlyChart";

import CongestionEvents from "../components/CongestionEvents";

import DayDetails from "../components/DayDetails";

import { API_BASE_URL, getISTDateValue } from "../config";

function CrowdHistory() {
  const [summary, setSummary] = useState(null);

  const [history, setHistory] = useState([]);

  const [hourly, setHourly] = useState([]);

  const [events, setEvents] = useState([]);
  const [eventRooms, setEventRooms] = useState([]);
  const [eventStatus, setEventStatus] = useState("ALL");
  const [eventRoomId, setEventRoomId] = useState("");
  const [eventStartDate, setEventStartDate] = useState("");
  const [eventEndDate, setEventEndDate] = useState("");
  const [eventsLoading, setEventsLoading] = useState(true);
  const [eventRetry, setEventRetry] = useState(0);

  const [days, setDays] = useState(7);

  const [selectedDate, setSelectedDate] = useState(getISTDateValue());

  const [loadingHistory, setLoadingHistory] = useState(true);

  const [loadingHourly, setLoadingHourly] = useState(true);

  const [summaryError, setSummaryError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [hourlyError, setHourlyError] = useState("");
  const [eventsError, setEventsError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/monitoring/rooms`)
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load rooms");
        return response.json();
      })
      .then(setEventRooms)
      .catch(() => setEventRooms([]));
  }, []);

  // ----------------------------------------
  // Today's summary
  // ----------------------------------------

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${API_BASE_URL}/api/crowd/today`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load today's summary");
        }

        return response.json();
      })
      .then((data) => {
        setSummary(data);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          setSummaryError("Today’s summary could not be loaded.");
        }
      });

    return () => controller.abort();
  }, []);

  // ----------------------------------------
  // Daily history
  // ----------------------------------------

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${API_BASE_URL}/api/crowd/history?days=${days}`, {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load history");
        }

        return response.json();
      })
      .then((data) => {
        setHistory(data);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          setHistoryError("Daily history could not be loaded.");
          setHistory([]);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoadingHistory(false);
        }
      });

    return () => controller.abort();
  }, [days]);

  // ----------------------------------------
  // Hourly history
  // ----------------------------------------

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${API_BASE_URL}/api/crowd/history/${selectedDate}`, {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load hourly data");
        }

        return response.json();
      })
      .then((data) => {
        setHourly(data);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          setHourlyError("Hourly history could not be loaded.");
          setHourly([]);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoadingHourly(false);
        }
      });

    return () => controller.abort();
  }, [selectedDate]);

  // ----------------------------------------
  // Congestion events
  // ----------------------------------------

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      status: eventStatus,
      limit: "100",
    });
    if (eventRoomId) params.set("room_id", eventRoomId);
    if (eventStartDate) params.set("start_date", eventStartDate);
    if (eventEndDate) params.set("end_date", eventEndDate);

    const requestTimer = window.setTimeout(() => {
      setEventsLoading(true);
      setEventsError("");
      fetch(`${API_BASE_URL}/api/crowd/events/history?${params.toString()}`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load events");
        }

        return response.json();
      })
      .then((data) => {
        setEvents(data.items || []);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          setEventsError("Congestion events could not be loaded.");
          setEvents([]);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setEventsLoading(false);
      });
    }, 0);

    return () => {
      window.clearTimeout(requestTimer);
      controller.abort();
    };
  }, [eventEndDate, eventRetry, eventRoomId, eventStartDate, eventStatus]);

  const handlePeriodChange = (value) => {
    setLoadingHistory(true);
    setHistoryError("");
    setDays(value);
  };

  const handleDateChange = (value) => {
    setLoadingHourly(true);
    setHourlyError("");
    setSelectedDate(value);
  };

  return (
    <div className="analytics-page">
      {/* HEADER */}

      <div className="page-header">
        <div>
          <p className="analytics-label">CROWD ANALYTICS</p>

          <h1>Crowd History & Insights</h1>

          <p>Historical waiting-area occupancy and congestion analysis.</p>
        </div>

        <Link to="/" className="back-button">
          ← Live Dashboard
        </Link>
      </div>

      {/* TODAY SUMMARY */}

      {summaryError ? (
        <div className="system-message">{summaryError}</div>
      ) : (
        <TodaySummary summary={summary} />
      )}

      {/* DAILY HISTORY */}

      <section>
        <div className="section-heading">
          <div>
            <p className="analytics-label">HISTORICAL TRENDS</p>

            <h2>Daily Crowd History</h2>
          </div>

          <div className="period-selector">
            <button
              className={days === 7 ? "period-active" : ""}
              onClick={() => handlePeriodChange(7)}
            >
              7 DAYS
            </button>

            <button
              className={days === 30 ? "period-active" : ""}
              onClick={() => handlePeriodChange(30)}
            >
              30 DAYS
            </button>

            <button
              className={days === 90 ? "period-active" : ""}
              onClick={() => handlePeriodChange(90)}
            >
              90 DAYS
            </button>
          </div>
        </div>

        {loadingHistory ? (
          <div className="chart-card empty-chart">Loading crowd history...</div>
        ) : historyError ? (
          <div className="chart-card empty-chart">{historyError}</div>
        ) : (
          <CrowdChart data={history} />
        )}
      </section>

      {/* SELECTED DAY */}

      <section>
        <DayDetails
          selectedDate={selectedDate}
          hourlyData={hourly}
        />
      </section>

      {/* HOURLY ANALYSIS */}

      <section>
        {loadingHourly ? (
          <div className="chart-card empty-chart">
            Loading hourly analysis...
          </div>
        ) : hourlyError ? (
          <div className="chart-card empty-chart">{hourlyError}</div>
        ) : (
          <HourlyChart
            data={hourly}
            selectedDate={selectedDate}
            setSelectedDate={handleDateChange}
          />
        )}
      </section>

      {/* CONGESTION */}

      <section>
        <div className="section-heading">
          <div>
            <p className="analytics-label">EVENT HISTORY</p>
            <h2>Congestion Events</h2>
          </div>
          <button className="back-button" onClick={() => setEventRetry((value) => value + 1)}>Refresh</button>
        </div>
        <div className="event-filters card">
          <label>Room<select value={eventRoomId} onChange={(event) => setEventRoomId(event.target.value)}><option value="">All rooms</option>{eventRooms.map((room) => <option value={room.room_id} key={room.room_id}>{room.room_name}</option>)}</select></label>
          <label>Status<select value={eventStatus} onChange={(event) => setEventStatus(event.target.value)}><option>ALL</option><option>ACTIVE</option><option>RESOLVED</option></select></label>
          <label>From<input type="date" value={eventStartDate} onChange={(event) => setEventStartDate(event.target.value)} /></label>
          <label>To<input type="date" value={eventEndDate} onChange={(event) => setEventEndDate(event.target.value)} /></label>
        </div>
        {eventsLoading ? (
          <div className="chart-card empty-chart">Loading congestion events...</div>
        ) : eventsError ? (
          <div className="chart-card empty-chart">{eventsError}<br /><button className="back-button" onClick={() => setEventRetry((value) => value + 1)}>Retry</button></div>
        ) : (
          <CongestionEvents events={events} />
        )}
      </section>
    </div>
  );
}

export default CrowdHistory;
