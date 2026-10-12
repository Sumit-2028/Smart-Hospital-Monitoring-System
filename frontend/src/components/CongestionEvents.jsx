import { formatISTDateTime } from "../config";

function CongestionEvents({ events }) {
  if (!events || events.length === 0) {
    return (
      <div className="chart-card">
        <p className="analytics-label">CONGESTION EVENTS</p>

        <h2>No congestion events</h2>

        <p className="empty-text">
          The waiting area has remained below the congestion threshold.
        </p>
      </div>
    );
  }

  return (
    <div className="chart-card">
      <div className="chart-header">
        <div>
          <p className="analytics-label">CONGESTION EVENTS</p>

          <h2>Recent Congestion</h2>
        </div>
      </div>

      <div className="event-list" aria-label="Congestion event history">
        {events.map((event) => (
          <div className="event-row" key={event.id}>
            <div>
              <strong>{event.room_name || "Legacy monitoring"}</strong>

              <p>Started: {formatISTDateTime(event.started_at)}</p>
              <p>Peak: {event.peak_crowd} · Threshold: {event.threshold}</p>
            </div>

            <div>
              {event.resolved ? (
                <span>RESOLVED · {formatDuration(event.duration_seconds, event.started_at, event.ended_at)}</span>
              ) : (
                <span className="active-event">ACTIVE</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatDuration(seconds, start, end) {
  if (typeof seconds === "number") return `${Math.round(seconds / 60)} min`;
  const difference = Math.max(0, new Date(end) - new Date(start));
  return `${Math.round(difference / 60000)} min`;
}

export default CongestionEvents;
