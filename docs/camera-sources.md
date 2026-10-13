# Camera source configuration

The camera table already supports both source types. No migration is required
for switching an existing camera between a local device and a network stream.
The computer-vision process remains the only process that opens a physical
camera. Each active camera ID has at most one worker and one OpenCV
`VideoCapture` handle.

## Local laptop webcam

1. Connect the webcam to the computer that runs the computer-vision process.
2. Start FastAPI and the frontend, then open `/admin`.
3. Create or edit a camera and choose `WEBCAM`.
4. Enter the OpenCV device index, for example `0` for the first device or `1`
   for another device. The value must be a non-negative integer.
5. Assign the camera to an active room and save it.
6. Restart the computer-vision process, or wait for its configuration refresh.

The device index is local to the machine running the CV process. It is not the
index of the browser computer or phone.

## Android phone/IP camera

1. Install and start a phone camera application that exposes an HTTP, HTTPS,
   or RTSP stream. IP Webcam commonly exposes a URL similar to
   `http://PHONE_IP:8080/video`; the exact path depends on the application.
2. Connect the phone and the CV computer to the same reachable network. Use
   the phone's LAN address, not `localhost` or `127.0.0.1`.
3. From the CV computer, open the stream URL in a browser or test it with the
   application's documented endpoint. Confirm that it returns video before
   saving the camera.
4. In `/admin`, create or edit a camera and choose `IP_STREAM`.
5. Enter the complete `http://`, `https://`, or `rtsp://` URL and assign the
   camera to an active room.
6. Save the camera and restart the CV process, or wait for configuration
   refresh.

The URL is stored server-side for the trusted camera agent. It is not returned
by public camera status APIs, the room monitoring page, or the admin edit
response. Do not paste credentials into browser URLs unless the camera
application requires them; if credentials are required, keep them in the
protected server configuration and never put them in logs or screenshots.

## Run local and phone cameras simultaneously

1. Create two active rooms, for example `Laptop Waiting Area` and `Phone
   Waiting Area`.
2. Register one `WEBCAM` camera with source `0` for the laptop room.
3. Register one `IP_STREAM` camera with the phone application's reachable URL
   for the phone room.
4. Start the backend, then start one computer-vision process:

   ```powershell
   cd backend
   python -m uvicorn app.main:app --reload

   cd ..\computer-vision
   python -m app.main
   ```

5. Open the dashboard and each room's monitoring page. The selected room page
   must show only cameras assigned to that room.
6. Check `/api/monitoring/cameras` or the admin camera list for `CONNECTED`
   and a changing `last_frame_at`. `RECONNECTING`, `DISCONNECTED`, `ERROR`, or
   `STALE` means the configured source is not currently supplying fresh frames.

There is intentionally one active occupancy camera per room. Multiple cameras
may be registered for different rooms; cross-camera identity/deduplication is
not implemented. A failed phone stream does not substitute a laptop webcam or
stop the laptop worker.

## Changing a source safely

When editing an existing camera, the saved source is hidden. Leave the source
field blank to keep it unchanged. To replace it, select the new source type,
enter the complete new value, and save. The camera manager stops and joins the
old worker before starting the replacement worker for the same camera ID.

Invalid device indices and malformed network URLs are rejected by the API with
a validation error. A valid but unreachable network URL is accepted as
configuration and the worker reports bounded retries followed by `ERROR` or
`RECONNECTING`; it does not fabricate frames or counts.

## Troubleshooting

- `RECONNECTING` or `ERROR`: verify the URL from the CV computer, phone Wi-Fi,
  firewall settings, and the phone application's active stream endpoint.
- `STALE`: the last heartbeat/frame timestamp is older than the configured
  stale window. Check the CV process logs and the camera worker's camera ID.
- No preview but `CONNECTED`: confirm the CV process is posting JPEG frames and
  that the administrator session in the browser is current. The preview is an
  authenticated MJPEG stream and does not open the camera a second time.
- A local camera opens on the wrong device: use the device index visible to
  OpenCV on the CV computer and change the configured source; do not hardcode
  the index in application code.
