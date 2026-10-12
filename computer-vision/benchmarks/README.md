# Multi-camera benchmark

`multi_camera_benchmark.py` runs the real `CameraWorker` and
`CameraProcessingManager` with deterministic mocked capture, detection, and
HTTP sinks. It does not open a webcam, load YOLO weights, write PostgreSQL, or
connect to a browser WebSocket. Results are therefore synthetic regression
measurements, not physical-camera or end-to-end dashboard evidence.

Run it from `computer-vision`:

```powershell
python benchmarks/multi_camera_benchmark.py --duration 5
```

The output contains independent per-camera read/processed FPS, skipped and
failed frames, inference and HTTP timing, CPU/RSS samples, cleanup state, and
simulated crowd-write/broadcast rates. Change `--source-fps`, resolution,
`--inference-delay-ms`, `--backend-delay-ms`, or `--processing-interval` to
repeat a controlled comparison.

For a physical test, register each camera in the admin UI, start the backend,
start the camera agent, and collect the worker metrics from its structured log.
Use distinct rooms and verify the camera/room IDs in both the heartbeat and
crowd-reading payloads. The repository's `Hardware.txt` currently records that
no physical hardware is connected, so no physical-camera result is claimed.
