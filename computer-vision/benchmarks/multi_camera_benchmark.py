"""Repeatable synthetic multi-camera benchmark.

This benchmark exercises the real CameraWorker lifecycle without opening a
camera, loading YOLO weights, or writing to PostgreSQL. It is intentionally
labelled synthetic: its backend counters are a bounded in-process sink, not a
measurement of a running FastAPI/PostgreSQL/React deployment.

Run from computer-vision:

    python benchmarks/multi_camera_benchmark.py --duration 5
"""

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import camera_manager


class FakeResponse:
    def raise_for_status(self):
        return None


class SyntheticCapture:
    def __init__(self, source_fps, width, height):
        self.source_fps = source_fps
        self.frame = SimpleNamespace(shape=(height, width, 3))
        self.released = False

    def isOpened(self):
        return not self.released

    def read(self):
        time.sleep(1 / self.source_fps)
        return (False, None) if self.released else (True, self.frame)

    def set(self, _property, _value):
        return True

    def release(self):
        self.released = True


class SyntheticDetector:
    def __init__(self, inference_delay):
        self.inference_delay = inference_delay

    def track(self, _frame):
        time.sleep(self.inference_delay)
        return SimpleNamespace(boxes=None)


class Sink:
    def __init__(self, response_delay):
        self.response_delay = response_delay
        self.calls = []
        self.lock = threading.Lock()

    def post(self, url, **_kwargs):
        started = time.perf_counter()
        time.sleep(self.response_delay)
        with self.lock:
            self.calls.append({"url": url, "started": started, "finished": time.perf_counter()})
        return FakeResponse()


class SyntheticSession:
    def __init__(self, sink):
        self.sink = sink
        self.closed = False

    def post(self, url, **kwargs):
        return self.sink.post(url, **kwargs)

    def close(self):
        self.closed = True


def _percentile(values, percentile):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1)))
    return ordered[index]


def run_case(camera_count, duration, source_fps, inference_delay, backend_delay, width, height, processing_interval):
    sink = Sink(backend_delay)
    captures = []
    sessions = []
    process = psutil.Process(os.getpid())
    samples = []
    sampling_stop = threading.Event()

    def make_capture(_source):
        capture = SyntheticCapture(source_fps, width, height)
        captures.append(capture)
        return capture

    def make_detector():
        return SyntheticDetector(inference_delay)

    def make_session():
        session = SyntheticSession(sink)
        sessions.append(session)
        return session

    def sample_resources():
        process.cpu_percent(None)
        while not sampling_stop.wait(0.1):
            samples.append({
                "cpu_percent": process.cpu_percent(None),
                "rss_bytes": process.memory_info().rss,
            })

    configs = [
        {
            "id": index,
            "room_id": index,
            "source_type": "WEBCAM",
            "source": str(index),
            "agent_token": "benchmark-token",
            "processing_interval": processing_interval,
        }
        for index in range(1, camera_count + 1)
    ]
    resource_thread = threading.Thread(target=sample_resources, daemon=True)
    started = time.monotonic()
    resource_thread.start()
    with _patch(camera_manager.cv2, "VideoCapture", make_capture), \
         _patch(camera_manager, "PersonDetector", make_detector), \
         _patch(camera_manager.requests, "Session", make_session), \
         _patch(camera_manager, "CAMERA_HEARTBEAT_INTERVAL", max(duration + 1, 5)), \
         _patch(camera_manager, "UPDATE_INTERVAL", 0.5):
        manager = camera_manager.CameraProcessingManager(configs)
        time.sleep(duration)
        manager.stop()
    elapsed = time.monotonic() - started
    sampling_stop.set()
    resource_thread.join(timeout=2)

    snapshots = manager.metrics_snapshot()
    crowd_calls = [call for call in sink.calls if call["url"].endswith("/api/crowd/")]
    heartbeat_calls = [call for call in sink.calls if call["url"].endswith("/api/monitoring/internal/heartbeat")]
    simulated_sink_ms = [
        (call["finished"] - call["started"]) * 1000 for call in crowd_calls
    ]
    max_rss = max((sample["rss_bytes"] for sample in samples), default=process.memory_info().rss)
    average_cpu = sum(sample["cpu_percent"] for sample in samples) / len(samples) if samples else 0.0
    maximum_cpu = max((sample["cpu_percent"] for sample in samples), default=0.0)

    return {
        "stream_type": "synthetic-mocked",
        "camera_count": camera_count,
        "elapsed_seconds": round(elapsed, 3),
        "configuration": {
            "source_fps": source_fps,
            "resolution": f"{width}x{height}",
            "inference_delay_ms": round(inference_delay * 1000, 3),
            "backend_sink_delay_ms": round(backend_delay * 1000, 3),
            "processing_interval": processing_interval,
        },
        "cameras": snapshots,
        "resource_usage": {
            "average_process_cpu_percent": round(average_cpu, 3),
            "maximum_process_cpu_percent": round(maximum_cpu, 3),
            "peak_rss_mb": round(max_rss / (1024 * 1024), 3),
        },
        "simulated_backend_sink": {
            "crowd_writes": len(crowd_calls),
            "crowd_writes_per_second": round(len(crowd_calls) / elapsed, 3),
            "heartbeat_writes": len(heartbeat_calls),
            "websocket_updates": len(crowd_calls),
            "websocket_updates_per_second": round(len(crowd_calls) / elapsed, 3),
            "sink_latency_p50_ms": round(_percentile(simulated_sink_ms, 50), 3),
            "sink_latency_p95_ms": round(_percentile(simulated_sink_ms, 95), 3),
        },
        "dashboard_update_latency": {
            "real_frontend_measured": False,
            "simulated_worker_to_backend_sink_p50_ms": round(_percentile(simulated_sink_ms, 50), 3),
            "note": "A real FastAPI/PostgreSQL/WebSocket/React dashboard was not part of this synthetic run.",
        },
        "cleanup": {
            "released_captures": all(capture.released for capture in captures),
            "closed_sessions": all(session.closed for session in sessions),
        },
    }


class _patch:
    def __init__(self, target, attribute, value):
        self.target = target
        self.attribute = attribute
        self.value = value
        self.original = None

    def __enter__(self):
        self.original = getattr(self.target, self.attribute)
        setattr(self.target, self.attribute, self.value)
        return self

    def __exit__(self, *_args):
        setattr(self.target, self.attribute, self.original)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--source-fps", type=float, default=15.0)
    parser.add_argument("--inference-delay-ms", type=float, default=10.0)
    parser.add_argument("--backend-delay-ms", type=float, default=10.0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--processing-interval", type=int, default=1)
    args = parser.parse_args()
    if args.duration <= 0 or args.source_fps <= 0 or args.processing_interval <= 0:
        parser.error("duration, source-fps, and processing-interval must be positive")

    results = [
        run_case(
            camera_count=count,
            duration=args.duration,
            source_fps=args.source_fps,
            inference_delay=args.inference_delay_ms / 1000,
            backend_delay=args.backend_delay_ms / 1000,
            width=args.width,
            height=args.height,
            processing_interval=args.processing_interval,
        )
        for count in (1, 2, 3)
    ]
    print(json.dumps({"benchmark": "multi_camera", "results": results}, indent=2))


if __name__ == "__main__":
    main()
