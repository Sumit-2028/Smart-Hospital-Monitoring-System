# Smart Hospital Monitoring System

Software-first hospital operations monitoring for waiting-area crowd and
congestion visibility. The current demonstration uses a computer webcam,
YOLO person detection, tracking IDs, FastAPI, PostgreSQL, WebSocket updates,
and a React analytics dashboard. Physical sensors are planned but are not
connected yet.

## Current status

Implemented and active:

- Person detection and tracking with YOLO and ByteTrack
- Waiting-area region of interest (ROI)
- Tracking-ID-based entry and exit detection
- Crowd counting without counting the same person in every frame
- Configurable congestion threshold and congestion events
- FastAPI REST API
- PostgreSQL persistence for crowd readings and congestion events
- WebSocket live updates
- React live dashboard
- Daily and hourly crowd analytics using Indian Standard Time (IST)

Planned but not connected:

- ESP32
- MQ-135 air-quality sensor
- RC522/MFRC522 RFID reader
- Ultrasonic dustbin-level sensor

See [Hardware.txt](Hardware.txt) for the complete wiring, power, component,
and future integration guide.

## Architecture

```text
Computer webcam
      |
      v
OpenCV -> YOLO -> ByteTrack -> ROI entry/exit -> crowd count
                                                      |
                                                      v
                                              FastAPI /api/crowd/
                                                |             |
                                                v             v
                                           PostgreSQL      WebSocket /ws
                                                              |
                                                              v
                                                        React dashboard
                                                        and analytics
```

Future ESP32 sensor telemetry will be an additional path to FastAPI. It must
not replace the camera/YOLO crowd path or send sensor readings to the crowd
endpoint.

## Repository structure

```text
smart-hospital-monitoring/
├── backend/
│   ├── app/
│   │   ├── models/              SQLAlchemy models
│   │   ├── routes/              FastAPI endpoints
│   │   ├── services/            Crowd and congestion logic
│   │   ├── time_utils.py        UTC/IST conversion helpers
│   │   ├── database.py          PostgreSQL connection/session setup
│   │   └── main.py              FastAPI application and WebSocket endpoint
│   ├── .env.example
│   └── requirements.txt
├── computer-vision/
│   ├── app/
│   │   ├── detector.py          YOLO detection/tracking wrapper
│   │   ├── tracker.py           ROI tracking and entry/exit state
│   │   ├── config.py            Camera, threshold, and backend settings
│   │   └── main.py              Webcam processing loop
│   ├── models/                  Local model assets, if used
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/          Dashboard and chart components
│   │   ├── pages/               React pages
│   │   ├── config.js             API, WebSocket, and IST display helpers
│   │   └── App.jsx              Live dashboard and routing
│   ├── .env.example
│   └── package.json
├── Hardware.txt                 Future hardware implementation guide
└── README.md
```

## Requirements

- Windows, macOS, or Linux
- Python 3.11 or a compatible recent Python version
- PostgreSQL
- Node.js and npm
- A working computer webcam for the computer-vision process
- A YOLO model file configured by `MODEL_NAME` (the repository currently uses
  `yolo26n.pt`)

The physical ESP32 and sensors are not required to run the current software
demonstration.

## Backend setup

Open a terminal in `backend`:

```powershell
cd "smart-hospital-monitoring\backend"
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create the local environment file:

```powershell
Copy-Item .env.example .env
```

Edit `backend/.env` and set a real PostgreSQL connection string. Example
format:

```env
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/smart_hospital
CROWD_THRESHOLD=5
CAMERA_INDEX=0
UPDATE_INTERVAL=0.5
BACKEND_URL=http://127.0.0.1:8000
```

Do not commit `.env`, passwords, or other credentials.

Start FastAPI:

```powershell
python -m uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`.

On Windows, `tzdata` is required for `ZoneInfo("Asia/Kolkata")` and is
included in `backend/requirements.txt`.

## Computer-vision setup

Open a second terminal in `computer-vision`:

```powershell
cd "smart-hospital-monitoring\computer-vision"
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.main
```

The process opens the configured webcam, draws the waiting-area ROI, and
sends crowd readings to the backend at the configured update interval. Press
`Q` in the OpenCV window to stop it.

The computer-vision configuration loads the shared values from
`backend/.env` when available:

| Setting | Purpose | Default |
| --- | --- | --- |
| `MODEL_NAME` | YOLO model filename | `yolo26n.pt` |
| `CAMERA_INDEX` | OpenCV camera index | `0` |
| `CROWD_THRESHOLD` | Count at which status becomes `CONGESTED` | `5` |
| `UPDATE_INTERVAL` | Seconds between REST submissions | `0.5` |
| `BACKEND_URL` | FastAPI base URL | `http://127.0.0.1:8000` |
| `CONFIDENCE_THRESHOLD` | YOLO confidence threshold | `0.4` |
| `TRACKING_GRACE_FRAMES` | Missing frames tolerated before exit | `15` |
| `TRACKER` | Ultralytics tracker configuration | `bytetrack.yaml` |

The threshold is sent with every crowd reading. The backend calculates the
status from the submitted `person_count` and `threshold`.

## Frontend setup

Open a third terminal in `frontend`:

```powershell
cd "smart-hospital-monitoring\frontend"
npm install
Copy-Item .env.example .env
npm run dev
```

The Vite development server normally runs at `http://localhost:5173`.

Optional frontend environment variables:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_WS_URL=ws://127.0.0.1:8000/ws
```

Open the URL shown by Vite. Use **Crowd Analytics** to view daily history,
selected-date hourly history, and recent congestion events.

## Recommended startup order

1. Start PostgreSQL and ensure the `smart_hospital` database exists.
2. Start the FastAPI backend.
3. Start the computer-vision process.
4. Start the React frontend.

The dashboard can load without the computer-vision process, but it will show
no new live readings until the CV process posts data.

## API reference

### Create a crowd reading

```text
POST /api/crowd/
```

Request:

```json
{
  "person_count": 3,
  "threshold": 5
}
```

The backend returns the reading, UTC timestamp, calculated status, and event
transition (`NONE`, `STARTED`, `ONGOING`, or `ENDED`).

### Latest reading

```text
GET /api/crowd/latest
```

Used to hydrate the dashboard before the next live WebSocket message arrives.

### Today summary

```text
GET /api/crowd/today
```

Returns average crowd, peak crowd/time, minimum crowd, congestion count and
duration, busiest IST hour, and the latest current-state fields.

### Daily history

```text
GET /api/crowd/history?days=7
```

`days` accepts values from 1 through 90. Each returned day contains:

```json
{
  "date": "2026-08-27",
  "average_crowd": 3.5,
  "peak_crowd": 8,
  "minimum_crowd": 1,
  "reading_count": 24
}
```

Dates are grouped by IST calendar date.

### Hourly history

```text
GET /api/crowd/history/2026-08-27
```

Hours are calculated after converting UTC timestamps to IST. Each hour
contains `hour`, `average_crowd`, `peak_crowd`, and `reading_count`.

### Congestion events

```text
GET /api/crowd/events
```

Returns the latest congestion events with start/end timestamps, peak crowd,
threshold, and resolved state.

### Live WebSocket

```text
ws://127.0.0.1:8000/ws
```

New crowd readings are broadcast to connected React clients. The frontend
handles connection loss and attempts to reconnect automatically.

## Crowd counting behavior

The tracker uses the center point of each YOLO bounding box to test whether a
tracking ID is inside the waiting-area ROI. The current ROI is approximately:

- 10% to 90% of frame width
- 15% to 90% of frame height

An ID entering the ROI is counted once. The same ID remaining in subsequent
frames does not increase the count. A temporarily missing ID is retained for
`TRACKING_GRACE_FRAMES` so short occlusions do not immediately cause a new
identity and double-counting. After the grace period, the ID is removed and a
leave event is produced.

The current count is the number of active tracked IDs in the ROI, not the
number of YOLO detections across frames.

## Timezone policy

- Existing PostgreSQL timestamp columns store UTC-naive values for schema
  compatibility.
- Backend timestamp helpers normalize database values as UTC.
- API timestamps include an explicit UTC offset.
- Daily grouping, hourly grouping, peak time, event times, and dashboard
  display use `Asia/Kolkata` / IST.
- The frontend current clock updates every second and is separate from the
  last crowd-reading timestamp.
- Timestamps must never be adjusted by manually adding 5 hours 30 minutes.

## Hardware integration boundary

The current software does not have a hardware telemetry route yet. The
existing hardware-oriented models (`SensorReading`, `AccessLog`, and `Alert`)
are placeholders for future integration.

When hardware is added:

- Keep the webcam/YOLO system as the authoritative crowd counter.
- Add a separate authenticated endpoint such as
  `POST /api/hardware/telemetry`.
- Do not send MQ-135, RFID, or ultrasonic values to `/api/crowd/`.
- Add typed hardware WebSocket messages without breaking crowd messages.
- Keep sensor and RFID data separate from crowd analytics.
- Mark missing, uncalibrated, and disconnected sensor values clearly.

See [Hardware.txt](Hardware.txt) for exact component recommendations,
ESP32 GPIO wiring, voltage-level protection, power requirements, calibration,
and future firmware/backend/frontend work.

## Testing and verification

Frontend checks:

```powershell
cd frontend
npm run lint
npm run build
```

Python syntax check:

```powershell
python -m compileall -q backend/app computer-vision/app
```

Before a real demonstration, manually verify:

- One person remains one tracked person across multiple frames.
- A second person increments the count once.
- Leaving the ROI eventually decrements the count after the grace period.
- A continuous threshold crossing creates only one active event.
- Falling below the threshold ends the event.
- Daily/hourly values are correct around midnight IST.
- The frontend handles backend or WebSocket interruptions gracefully.
- No physical sensor value is shown while its hardware is disconnected.

## Troubleshooting

### `ModuleNotFoundError: No module named 'tzdata'`

Activate the backend virtual environment and install the requirements:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### `ModuleNotFoundError: No module named 'dotenv'`

Activate the computer-vision virtual environment and install its requirements:

```powershell
cd computer-vision
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Backend does not start

- Confirm `backend/.env` exists.
- Confirm `DATABASE_URL` points to a running PostgreSQL instance.
- Confirm the database name exists.
- Run `python -m uvicorn app.main:app --reload` from the `backend` directory.

### Dashboard shows no live crowd data

- Confirm FastAPI is running on the configured URL.
- Confirm the computer-vision process can open the webcam.
- Confirm the CV process is using the same `BACKEND_URL` as the frontend API.
- Check the browser console for WebSocket connection errors.

### YOLO model cannot be loaded

- Confirm the configured model file exists in the computer-vision working
  directory or provide a valid `MODEL_NAME` path.
- Confirm the computer-vision requirements are installed in its own venv.
- Confirm the webcam and OpenCV window are available.

## Security and deployment notes

- Never commit `.env`, database passwords, Wi-Fi passwords, API keys, or
  private credentials.
- Replace local HTTP/WebSocket URLs with HTTPS/WSS behind a trusted deployment
  proxy.
- Authenticate ESP32 devices before accepting telemetry.
- Treat RFID UIDs as identifiers, not secure credentials.
- This project is an educational prototype and is not a certified medical
  device or a substitute for hospital safety controls.
