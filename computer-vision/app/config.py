import os
from pathlib import Path

from dotenv import load_dotenv


# The backend .env is shared by the two local processes. Shell variables win.
load_dotenv(Path(__file__).resolve().parents[2] / "backend" / ".env")


def get_int(name, default=None):
    raw_value = os.getenv(name, default)

    if raw_value is None:
        raise RuntimeError(f"{name} is not configured")

    try:
        return int(raw_value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"{name} must be an integer") from error


def get_float(name, default):
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"{name} must be a number") from error


MODEL_NAME = os.getenv("MODEL_NAME", "yolo26n.pt")

CAMERA_INDEX = get_int("CAMERA_INDEX", 0)

CONFIDENCE_THRESHOLD = 0.4

# Number of people required for congestion
# CROWD_THRESHOLD is normally supplied by the shared backend/.env. The
# fallback keeps the demo usable before a local .env has been completed.
CROWD_THRESHOLD = get_int("CROWD_THRESHOLD", 5)

if CROWD_THRESHOLD <= 0:
    raise RuntimeError("CROWD_THRESHOLD must be greater than zero")

# How frequently crowd data is sent to backend
UPDATE_INTERVAL = get_float("UPDATE_INTERVAL", 0.5)

if UPDATE_INTERVAL <= 0:
    raise RuntimeError("UPDATE_INTERVAL must be greater than zero")

# Number of frames an ID can disappear
# before we consider the person to have left.
TRACKING_GRACE_FRAMES = 15

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

TRACKER = "bytetrack.yaml"
