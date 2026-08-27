function DayDetails({ selectedDate, hourlyData, summary }) {
  if (!hourlyData || hourlyData.length === 0) {
    return (
      <div className="chart-card">
        <p className="analytics-label">DAY DETAILS</p>

        <h2>{selectedDate}</h2>

        <p className="empty-text">No crowd readings available for this date.</p>
      </div>
    );
  }

  const totalAverage =
    hourlyData.reduce((sum, item) => sum + item.average_crowd, 0) /
    hourlyData.length;

  const peakItem = hourlyData.reduce((max, item) =>
    item.peak_crowd > max.peak_crowd ? item : max,
  );

  return (
    <div className="day-details">
      <div>
        <p className="analytics-label">SELECTED DATE</p>

        <h2>{selectedDate}</h2>
      </div>

      <div className="day-stat">
        <span>Average</span>

        <strong>{totalAverage.toFixed(2)}</strong>
      </div>

      <div className="day-stat">
        <span>Peak</span>

        <strong>{peakItem.peak_crowd}</strong>
      </div>

      <div className="day-stat">
        <span>Peak Hour</span>

        <strong>{formatHour(peakItem.hour)}</strong>
      </div>
    </div>
  );
}

function formatHour(hour) {
  const suffix = hour >= 12 ? "PM" : "AM";

  const displayHour = hour % 12 || 12;

  return `${displayHour}:00 ${suffix}`;
}

export default DayDetails;
