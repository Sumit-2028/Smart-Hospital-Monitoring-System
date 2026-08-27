MODEL_NAME = "yolo26n.pt"

CAMERA_INDEX = 0

CONFIDENCE_THRESHOLD = 0.4

# Number of people required for congestion
CROWD_THRESHOLD = 5

# How frequently crowd data is sent to backend
UPDATE_INTERVAL = 0.5

# Number of frames an ID can disappear
# before we consider the person to have left.
TRACKING_GRACE_FRAMES = 15

BACKEND_URL = "http://127.0.0.1:8000"

TRACKER = "bytetrack.yaml"