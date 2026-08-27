function formatHour(hour) {
  if (hour === null || hour === undefined) {
    return "--";
  }

  const suffix = hour >= 12 ? "PM" : "AM";

  const displayHour = hour % 12 || 12;

  return `${displayHour}:00 ${suffix}`;
}

function formatPeakTime(timestamp) {
  if (!timestamp) {
    return "--";
  }

  return new Date(timestamp).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function TodaySummary({ summary }) {
  if (!summary) {
    return (
      <section className="summary-grid">
        {[1, 2, 3, 4].map((item) => (
          <div className="analytics-card loading-card" key={item}>
            Loading...
          </div>
        ))}
      </section>
    );
  }

  return (
    <section className="summary-grid">
      <div className="analytics-card">
        <p className="analytics-label">TODAY AVERAGE</p>

        <h3>{summary.average_crowd}</h3>

        <span>people</span>
      </div>

      <div className="analytics-card">
        <p className="analytics-label">PEAK CROWD</p>

        <h3>{summary.peak_crowd}</h3>

        <span>{formatPeakTime(summary.peak_time)}</span>
      </div>

      <div className="analytics-card">
        <p className="analytics-label">BUSIEST HOUR</p>

        <h3>{formatHour(summary.busiest_hour)}</h3>

        <span>highest average</span>
      </div>

      <div className="analytics-card">
        <p className="analytics-label">CONGESTION</p>

        <h3>{summary.congestion_minutes}</h3>

        <span>minutes today</span>
      </div>
    </section>
  );
}

export default TodaySummary;
