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

      <div className="event-list">
        {events.map((event) => (
          <div className="event-row" key={event.id}>
            <div>
              <strong>{formatISTDateTime(event.started_at)}</strong>

              <p>Peak: {event.peak_crowd} people</p>
            </div>

            <div>
              {event.ended_at ? (
                <span>
                  {calculateDuration(event.started_at, event.ended_at)} min
                </span>
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

function calculateDuration(start, end) {
  const difference = Math.max(0, new Date(end) - new Date(start));

  return Math.round(difference / 60000);
}

export default CongestionEvents;
