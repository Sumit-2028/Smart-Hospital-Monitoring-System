"""Live end-to-end smoke workflow for a dedicated test deployment.

The script validates an already-running backend and camera agent. It never
starts YOLO or invents camera detections. Deterministic crowd readings are
available only behind two explicit safety gates and must target a dedicated
test database.

Examples:

    # Verify registrations and wait for real workers to produce readings:
    python scripts/e2e_smoke.py --admin-username admin \
        --camera 1:10 --camera 2:11 --require-live

    # Run deterministic lifecycle/API/CSV/audit/WS checks on an isolated DB:
    $env:E2E_TEST_DATABASE = "1"
    python scripts/e2e_smoke.py --admin-username admin \
        --camera 1:10 --camera 2:11 --deterministic-camera 1:10 \
        --allow-deterministic-test-writes
"""

import argparse
import asyncio
import csv
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SmokeFailure(RuntimeError):
    pass


def http_json(base_url, method, path, *, token=None, camera_token=None, body=None, params=None):
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if camera_token:
        headers["X-Camera-Agent-Token"] = camera_token
    encoded = None
    if body is not None:
        encoded = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=encoded, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "json" in content_type:
                return response.status, json.loads(raw.decode("utf-8")), response.headers
            return response.status, raw, response.headers
    except HTTPError as error:
        raw = error.read()
        try:
            detail = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = {"detail": "non-JSON error response"}
        raise SmokeFailure(f"{method} {path} returned HTTP {error.code}: {detail.get('detail', 'request failed')}") from error
    except URLError as error:
        raise SmokeFailure(f"{method} {path} could not be reached: {error.reason}") from error


def parse_mapping(value):
    try:
        camera_id, room_id = (int(part) for part in value.split(":", 1))
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("camera mapping must be CAMERA_ID:ROOM_ID") from error
    if camera_id < 1 or room_id < 1:
        raise argparse.ArgumentTypeError("camera and room IDs must be positive")
    return camera_id, room_id


def require(condition, message):
    if not condition:
        raise SmokeFailure(message)


def login(base_url, username, password):
    status, data, _ = http_json(
        base_url,
        "POST",
        "/api/admin/login",
        body={"username": username, "password": password},
    )
    require(status == 200 and data.get("access_token"), "administrator login did not return a token")
    return data["access_token"]


def validate_camera_mappings(base_url, token, camera_token, mappings):
    _, admin_cameras, _ = http_json(base_url, "GET", "/api/admin/cameras", token=token)
    _, agent_cameras, _ = http_json(base_url, "GET", "/api/monitoring/internal/cameras", camera_token=camera_token)
    admin_by_id = {camera["id"]: camera for camera in admin_cameras}
    agent_by_id = {camera["id"]: camera for camera in agent_cameras}
    for camera_id, expected_room_id in mappings:
        camera = admin_by_id.get(camera_id)
        require(camera is not None, f"camera {camera_id} is not registered")
        require(camera["room_id"] == expected_room_id, f"camera {camera_id} is mapped to room {camera['room_id']}, expected {expected_room_id}")
        require(camera["active"], f"camera {camera_id} is inactive")
        agent_camera = agent_by_id.get(camera_id)
        require(agent_camera is not None, f"camera {camera_id} is not present in the active camera-agent configuration")
        require(agent_camera["room_id"] == expected_room_id, f"camera-agent mapping for camera {camera_id} is incorrect")


def post_reading(base_url, camera_token, camera_id, person_count):
    _, data, _ = http_json(
        base_url,
        "POST",
        "/api/crowd/",
        camera_token=camera_token,
        body={"camera_id": camera_id, "person_count": person_count},
    )
    require(data.get("camera_id") == camera_id, "reading camera_id did not round-trip")
    return data


def run_deterministic_lifecycle(base_url, token, camera_token, camera_id, room_id):
    _, rooms, _ = http_json(base_url, "GET", "/api/admin/rooms", token=token)
    room = next((item for item in rooms if item["id"] == room_id), None)
    require(room is not None and room["active"], f"test room {room_id} is not active")
    capacity = room["capacity"]
    below = max(0, capacity - 1)

    normal = post_reading(base_url, camera_token, camera_id, below)
    require(normal["room_id"] == room_id and normal["status"] in {"NORMAL", "WARNING"}, "below-threshold reading was scoped incorrectly")
    started = post_reading(base_url, camera_token, camera_id, capacity)
    require(started["event"] == "STARTED", "congestion event did not start")
    ongoing = post_reading(base_url, camera_token, camera_id, capacity + 1)
    require(ongoing["event"] == "ONGOING", "congestion event did not remain active")
    resolved = post_reading(base_url, camera_token, camera_id, below)
    require(resolved["event"] == "ENDED", "congestion event did not resolve")

    _, history, _ = http_json(base_url, "GET", "/api/crowd/events/history", params={"room_id": room_id, "status": "RESOLVED"})
    require(history["total"] >= 1, "resolved event was not returned by event history")
    _, alerts, _ = http_json(base_url, "GET", "/api/crowd/alerts/active", params={"room_id": room_id})
    require(alerts["total"] == 0, "resolved event still appears in active alerts")

    _, csv_bytes, _ = http_json(
        base_url,
        "GET",
        "/api/reports/crowd-readings.csv",
        token=token,
        params={"room_id": room_id, "camera_id": camera_id},
    )
    rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8"))))
    require(rows and all(int(row["room_id"]) == room_id and int(row["camera_id"]) == camera_id for row in rows), "CSV report contains an incorrect room or camera scope")

    _, audit, _ = http_json(base_url, "GET", "/api/admin/audit-logs", token=token)
    actions = {item["action"] for item in audit["items"]}
    require("REPORT_EXPORTED" in actions, "report export audit event was not found")
    return {"room_id": room_id, "camera_id": camera_id, "reading_rows_in_export": len(rows)}


async def websocket_reading_probe(base_url, camera_token, camera_id, count):
    try:
        import websockets
    except ImportError as error:
        raise SmokeFailure("websockets is not installed; backend WebSocket probe was skipped") from error

    ws_url = base_url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://") + "/ws"
    started_at = time.perf_counter()
    async with websockets.connect(ws_url, open_timeout=5) as socket:
        await asyncio.to_thread(post_reading, base_url, camera_token, camera_id, count)
        while True:
            raw = await asyncio.wait_for(socket.recv(), timeout=10)
            message = json.loads(raw)
            if message.get("event_type") != "crowd.reading":
                continue
            require(message.get("camera_id") == camera_id, "WebSocket message contained the wrong camera ID")
            return {
                "event_type": message.get("event_type"),
                "camera_id": message.get("camera_id"),
                "room_id": message.get("room_id"),
                "worker_to_websocket_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "browser_ui_measured": False,
            }


def wait_for_live_feed(base_url, mappings, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    last = {}
    while time.monotonic() < deadline:
        _, rooms, _ = http_json(base_url, "GET", "/api/monitoring/rooms")
        by_room = {room["room_id"]: room for room in rooms}
        last = {camera_id: by_room.get(room_id, {}).get("camera") for camera_id, room_id in mappings}
        if all(camera and camera["status"] == "CONNECTED" and camera.get("last_frame_at") for camera in last.values()):
            return {"connected": True, "cameras": last}
        time.sleep(1)
    return {"connected": False, "cameras": last}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--admin-username", default=os.getenv("E2E_ADMIN_USERNAME"))
    parser.add_argument("--admin-password", default=os.getenv("E2E_ADMIN_PASSWORD"))
    parser.add_argument("--camera-agent-token", default=os.getenv("CAMERA_AGENT_TOKEN"))
    parser.add_argument("--camera", action="append", type=parse_mapping, required=True, metavar="CAMERA_ID:ROOM_ID")
    parser.add_argument("--require-live", action="store_true", help="fail unless all selected feeds are CONNECTED with fresh frames")
    parser.add_argument("--wait-seconds", type=int, default=20)
    parser.add_argument("--deterministic-camera", type=parse_mapping, metavar="CAMERA_ID:ROOM_ID")
    parser.add_argument("--allow-deterministic-test-writes", action="store_true")
    args = parser.parse_args()

    require(args.admin_username and args.admin_password, "provide --admin-username/--admin-password or E2E_ADMIN_USERNAME/E2E_ADMIN_PASSWORD")
    require(args.camera_agent_token, "provide --camera-agent-token or CAMERA_AGENT_TOKEN")
    if args.deterministic_camera:
        require(args.allow_deterministic_test_writes, "deterministic readings require --allow-deterministic-test-writes")
        require(os.getenv("E2E_TEST_DATABASE") == "1", "set E2E_TEST_DATABASE=1 only when the backend uses a dedicated test database")
        require(args.deterministic_camera in args.camera, "deterministic camera mapping must also be listed with --camera")

    token = login(args.base_url, args.admin_username, args.admin_password)
    validate_camera_mappings(args.base_url, token, args.camera_agent_token, args.camera)
    result = {"base_url": args.base_url, "camera_mappings": [{"camera_id": c, "room_id": r} for c, r in args.camera]}

    if args.require_live:
        live = wait_for_live_feed(args.base_url, args.camera, args.wait_seconds)
        result["real_camera_smoke"] = live
        require(live["connected"], "one or more selected cameras did not become CONNECTED with a fresh frame")

    if args.deterministic_camera:
        camera_id, room_id = args.deterministic_camera
        result["deterministic_lifecycle"] = run_deterministic_lifecycle(args.base_url, token, args.camera_agent_token, camera_id, room_id)
        result["websocket"] = asyncio.run(websocket_reading_probe(args.base_url, args.camera_agent_token, camera_id, 0))
    else:
        result["deterministic_lifecycle"] = "not run; no test readings inserted"
        result["websocket"] = "not run; use the deterministic test seam to trigger a known event"

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SmokeFailure as error:
        print(f"E2E smoke failed: {error}", file=sys.stderr)
        sys.exit(1)
