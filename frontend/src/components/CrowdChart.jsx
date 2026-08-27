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

function formatDate(date) {
  const value = new Date(`${date}T00:00:00`);

  return value.toLocaleDateString([], {
    day: "numeric",
    month: "short",
  });
}

function CrowdChart({ data }) {
  const formattedData = data.map((item) => ({
    ...item,
    displayDate: formatDate(item.date),
  }));

  return (
    <div className="chart-card">
      {formattedData.length === 0 ? (
        <div className="empty-chart">
          No historical crowd data available yet.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={360}>
          <LineChart
            data={formattedData}
            margin={{
              top: 10,
              right: 20,
              left: 0,
              bottom: 10,
            }}
          >
            <CartesianGrid strokeDasharray="3 3" />

            <XAxis dataKey="displayDate" />

            <YAxis
              allowDecimals={false}
              label={{
                value: "People",
                angle: -90,
                position: "insideLeft",
              }}
            />

            <Tooltip />

            <Legend />

            <Line
              type="monotone"
              dataKey="average_crowd"
              name="Average Crowd"
              strokeWidth={3}
              dot={{ r: 4 }}
            />

            <Line
              type="monotone"
              dataKey="peak_crowd"
              name="Peak Crowd"
              strokeWidth={3}
              dot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export default CrowdChart;
