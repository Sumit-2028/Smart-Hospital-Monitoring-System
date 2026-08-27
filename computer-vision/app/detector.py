from ultralytics import YOLO

from app.config import MODEL_NAME, CONFIDENCE_THRESHOLD, TRACKER


class PersonDetector:

    def __init__(self):
        self.model = YOLO(MODEL_NAME)

    def track(self, frame):
        results = self.model.track(
            frame,
            persist=True,
            tracker=TRACKER,
            conf=CONFIDENCE_THRESHOLD,
            classes=[0],
            verbose=False
        )

        return results[0]