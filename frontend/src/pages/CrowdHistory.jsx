import { useEffect, useState } from "react";

import { Link } from "react-router-dom";

import TodaySummary from "../components/TodaySummary";

import CrowdChart from "../components/CrowdChart";

import HourlyChart from "../components/HourlyChart";

import CongestionEvents from "../components/CongestionEvents";

import DayDetails from "../components/DayDetails";

const API = "http://127.0.0.1:8000";

function CrowdHistory() {
  const [summary, setSummary] = useState(null);

  const [history, setHistory] = useState([]);

  const [hourly, setHourly] = useState([]);

  const [events, setEvents] = useState([]);

  const [days, setDays] = useState(7);

  const [selectedDate, setSelectedDate] = useState(
    new Date().toISOString().split("T")[0],
  );

  const [loadingHistory, setLoadingHistory] = useState(false);

  const [loadingHourly, setLoadingHourly] = useState(false);

  // ----------------------------------------
  // Today's summary
  // ----------------------------------------

  useEffect(() => {
    fetch(`${API}/api/crowd/today`)
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
        console.error("Summary error:", error);
      });
  }, []);

  // ----------------------------------------
  // Daily history
  // ----------------------------------------

  useEffect(() => {
    setLoadingHistory(true);

    fetch(`${API}/api/crowd/history?days=${days}`)
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
        console.error("History error:", error);

        setHistory([]);
      })
      .finally(() => {
        setLoadingHistory(false);
      });
  }, [days]);

  // ----------------------------------------
  // Hourly history
  // ----------------------------------------

  useEffect(() => {
    setLoadingHourly(true);

    fetch(`${API}/api/crowd/history/${selectedDate}`)
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
        console.error("Hourly error:", error);

        setHourly([]);
      })
      .finally(() => {
        setLoadingHourly(false);
      });
  }, [selectedDate]);

  // ----------------------------------------
  // Congestion events
  // ----------------------------------------

  useEffect(() => {
    fetch(`${API}/api/crowd/events`)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load events");
        }

        return response.json();
      })
      .then((data) => {
        setEvents(data);
      })
      .catch((error) => {
        console.error("Events error:", error);

        setEvents([]);
      });
  }, []);

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

      <TodaySummary summary={summary} />

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
              onClick={() => setDays(7)}
            >
              7 DAYS
            </button>

            <button
              className={days === 30 ? "period-active" : ""}
              onClick={() => setDays(30)}
            >
              30 DAYS
            </button>

            <button
              className={days === 90 ? "period-active" : ""}
              onClick={() => setDays(90)}
            >
              90 DAYS
            </button>
          </div>
        </div>

        {loadingHistory ? (
          <div className="chart-card empty-chart">Loading crowd history...</div>
        ) : (
          <CrowdChart data={history} />
        )}
      </section>

      {/* SELECTED DAY */}

      <section>
        <DayDetails
          selectedDate={selectedDate}
          hourlyData={hourly}
          summary={summary}
        />
      </section>

      {/* HOURLY ANALYSIS */}

      <section>
        {loadingHourly ? (
          <div className="chart-card empty-chart">
            Loading hourly analysis...
          </div>
        ) : (
          <HourlyChart
            data={hourly}
            selectedDate={selectedDate}
            setSelectedDate={setSelectedDate}
          />
        )}
      </section>

      {/* CONGESTION */}

      <section>
        <CongestionEvents events={events} />
      </section>
    </div>
  );
}

export default CrowdHistory;
