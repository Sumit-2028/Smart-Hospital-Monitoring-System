export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

export const WS_URL =
  import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8000/ws";

export const IST_TIME_ZONE = "Asia/Kolkata";

const timeOptions = {
  timeZone: IST_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: true,
};

export function formatISTTime(value, options = {}) {
  if (!value) {
    return "--";
  }

  const parsed = new Date(value);

  if (Number.isNaN(parsed.getTime())) {
    return "--";
  }

  const resolvedOptions = Object.keys(options).length
    ? { timeZone: IST_TIME_ZONE, ...options }
    : timeOptions;

  return parsed.toLocaleTimeString("en-IN", resolvedOptions);
}

export function formatISTDate(dateValue) {
  if (!dateValue) {
    return "--";
  }

  const [year, month, day] = dateValue.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));

  return parsed.toLocaleDateString("en-IN", {
    timeZone: "UTC",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatISTDateTime(value) {
  if (!value) {
    return "--";
  }

  const parsed = new Date(value);

  if (Number.isNaN(parsed.getTime())) {
    return "--";
  }

  return parsed.toLocaleString("en-IN", {
    timeZone: IST_TIME_ZONE,
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

export function getISTDateValue(value = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: IST_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);

  const values = Object.fromEntries(
    parts
      .filter(({ type }) => type !== "literal")
      .map(({ type, value: partValue }) => [type, partValue]),
  );

  return `${values.year}-${values.month}-${values.day}`;
}
