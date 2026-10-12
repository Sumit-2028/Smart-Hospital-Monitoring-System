# End-to-end integration workflow

This workflow separates three kinds of evidence:

1. Automated isolated API integration tests use an in-memory SQLite database.
2. The live smoke script checks a running FastAPI/PostgreSQL deployment and
   explicitly selected camera/room IDs.
3. Physical-camera and browser UI measurements require the operator's real
   hardware and are never reported by the automated suite.

## Automated checks

From `backend`:

```powershell
python -m pytest -q tests/test_e2e_integration.py
```

The test creates departments, rooms, cameras, and a super administrator in an
isolated in-memory database. It verifies camera-to-room mapping, deterministic
below/above/ongoing/resolved congestion transitions, room isolation, active
alerts, event history, CSV filters, audit records, invalid camera rejection,
camera disconnect/reconnect status, and the WebSocket payload contract.

It does not run YOLO, open a physical camera, or write to PostgreSQL.

The computer-vision regression checks remain:

```powershell
cd computer-vision
python -m unittest discover -s tests -v
```

## Dedicated live PostgreSQL deployment

Create a separate database for integration testing. Do not point this workflow
at a production or personal demonstration database because the deterministic
mode deliberately creates test crowd readings and audit rows.

Back up the test database before migrations, then from `backend` set process
environment variables so they override `backend/.env`:

```powershell
$env:DATABASE_URL = "postgresql+psycopg2://postgres:TEST_PASSWORD@localhost:5432/smart_hospital_e2e"
$env:ADMIN_TOKEN_SECRET = "a-long-random-e2e-only-secret"
$env:CAMERA_AGENT_TOKEN = "a-separate-e2e-camera-token"
python -m alembic upgrade head
python -m alembic check
python create_admin.py
python -m uvicorn app.main:app --reload
```

Use a separate terminal for the frontend:

```powershell
cd frontend
Copy-Item .env.example .env -Force
npm run dev
```

Use a third terminal for the camera agent. Register rooms and cameras in the
admin UI first. The agent retrieves active camera configuration from the
authenticated internal endpoint:

```powershell
cd computer-vision
python -m app.main
```

For a real webcam, select source type `WEBCAM` and the device index. For an
Android/IP stream, select `IP_STREAM` and enter the validated stream URL. Use
one occupancy camera per room; the application does not deduplicate people
across multiple views.

## Live registration and feed smoke test

Set credentials through environment variables rather than putting them in
shell history:

```powershell
$env:E2E_ADMIN_USERNAME = "the-test-admin"
$env:E2E_ADMIN_PASSWORD = "the-test-admin-password"
$env:CAMERA_AGENT_TOKEN = "the-e2e-camera-agent-token"
python scripts/e2e_smoke.py --camera 1:10 --camera 2:11 --camera 3:12 --require-live --wait-seconds 30
```

Each `--camera CAMERA_ID:ROOM_ID` is mandatory evidence for the intended
mapping. `--require-live` fails unless every selected room reports a connected
camera with a fresh frame. It does not convert a stale last count into a live
result.

The script reports camera mapping, registration status, and live-feed status.
It does not claim that detections came from real people unless the running
camera agent actually produced fresh readings.

## Deterministic lifecycle and WebSocket smoke test

Run this only against the dedicated test database. The two gates below are
intentional: the environment flag and the command-line flag are both required.

```powershell
$env:E2E_TEST_DATABASE = "1"
$env:E2E_ADMIN_USERNAME = "the-test-admin"
$env:E2E_ADMIN_PASSWORD = "the-test-admin-password"
$env:CAMERA_AGENT_TOKEN = "the-e2e-camera-agent-token"
python scripts/e2e_smoke.py `
  --camera 1:10 --camera 2:11 `
  --deterministic-camera 1:10 `
  --allow-deterministic-test-writes
```

This uses the authenticated crowd-ingestion API as a deterministic test seam;
it does not represent YOLO output. It verifies normal/warning input, event
start, ongoing peak update, resolution, event history, active-alert removal,
room/camera-filtered CSV output, report-export audit logging, and one
camera-to-WebSocket event. The reported WebSocket latency is backend-to-client
latency from the script; browser rendering latency is explicitly reported as
unmeasured.

## Browser-level checks

No browser automation dependency is currently installed. Manually open the
Vite URL and verify:

- the selected room card updates without a page refresh;
- another room card remains unchanged when only one camera posts;
- closing one camera marks only its room disconnected/stale;
- reconnecting the camera restores `FEED CONNECTED` and a new last-frame time;
- Admin, Reports, and Audit Log requests remain authenticated.

Record browser timing separately with the browser performance tools. Do not
report it as measured by the automated backend WebSocket test.

## Failure checks

The existing computer-vision tests cover unavailable capture, missing-frame
recovery, duplicate worker prevention, partial startup, dead-worker restart,
independent workers, and cleanup. The backend tests cover failed WebSocket
clients, database transaction handling, stale camera status, authentication,
auditing, reports, and room-scoped congestion behavior.

Do not reset PostgreSQL, run destructive migrations, or reuse production
credentials for this workflow.
