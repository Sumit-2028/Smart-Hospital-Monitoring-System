import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

function HourlyChart({ data, selectedDate, setSelectedDate }) {
  const formattedData = data.map((item) => ({
    ...item,
    hourLabel: formatHour(item.hour),
  }));

  return (
    <div className="chart-card">
      <div className="chart-header">
        <div>
          <p className="analytics-label">HOURLY ANALYSIS</p>

          <h2>Crowd by Hour</h2>
        </div>

        <input
          type="date"
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
        />
      </div>

      {formattedData.length === 0 ? (
        <div className="empty-chart">No data available for this date.</div>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={formattedData}>
            <CartesianGrid strokeDasharray="3 3" />

            <XAxis dataKey="hourLabel" />

            <YAxis allowDecimals={false} />

            <Tooltip />

            <Legend />

            <Line
              type="monotone"
              dataKey="average_crowd"
              name="Average"
              strokeWidth={3}
            />

            <Line
              type="monotone"
              dataKey="peak_crowd"
              name="Peak"
              strokeWidth={3}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function formatHour(hour) {
  const suffix = hour >= 12 ? "PM" : "AM";
  const displayHour = hour % 12 || 12;

  return `${displayHour}:00 ${suffix}`;
}

export default HourlyChart;
