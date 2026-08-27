import time

import cv2
import requests

from app.config import (
    CAMERA_INDEX,
    CROWD_THRESHOLD,
    UPDATE_INTERVAL,
    BACKEND_URL
)

from app.detector import PersonDetector
from app.tracker import CrowdTracker


def send_crowd_data(person_count):

    try:

        response = requests.post(
            f"{BACKEND_URL}/api/crowd/",
            json={
                "person_count": person_count,
                "threshold": CROWD_THRESHOLD
            },
            timeout=2
        )

        if response.status_code != 200:
            print(
                f"Backend error: {response.status_code}"
            )

    except requests.RequestException as error:

        print(
            f"Backend unavailable: {error}"
        )


def main():

    camera = cv2.VideoCapture(CAMERA_INDEX)

    if not camera.isOpened():

        print("ERROR: Could not open webcam.")
        return

    detector = PersonDetector()
    tracker = CrowdTracker()

    last_update_time = 0

    print("Smart Hospital Crowd Monitoring Started")
    print("Press Q to exit.")

    roi = None

    while True:

        success, frame = camera.read()

        if not success:

            print("ERROR: Could not read frame.")
            break

        height, width = frame.shape[:2]

        if roi is None:

            roi = (
                int(width * 0.10),
                int(height * 0.15),
                int(width * 0.90),
                int(height * 0.90)
            )

        # YOLO tracking happens continuously
        result = detector.track(frame)

        current_ids = tracker.update(
            result,
            roi
        )

        person_count = tracker.count()

        events = tracker.get_events()

        # People entering the waiting area
        for track_id in events["entered"]:

            print(
                f"PERSON ENTERED | ID: {track_id}"
            )

        # People leaving the waiting area
        for track_id in events["left"]:

            print(
                f"PERSON LEFT | ID: {track_id}"
            )

        # Determine congestion status
        if person_count >= CROWD_THRESHOLD:

            status = "CONGESTED"

        else:

            status = "NORMAL"

        # Send count to backend at configured interval
        current_time = time.time()

        if (
            current_time - last_update_time
            >= UPDATE_INTERVAL
        ):

            send_crowd_data(person_count)

            last_update_time = current_time

        # Draw YOLO detections
        annotated = result.plot()

        # Draw waiting-area ROI
        x1, y1, x2, y2 = roi

        cv2.rectangle(
            annotated,
            (x1, y1),
            (x2, y2),
            (255, 255, 0),
            2
        )

        cv2.putText(
            annotated,
            "WAITING AREA",
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 0),
            2
        )

        # Display current people count
        cv2.putText(
            annotated,
            f"PEOPLE: {person_count}",
            (30, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

        # Display congestion status
        cv2.putText(
            annotated,
            f"STATUS: {status}",
            (30, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255)
            if status == "CONGESTED"
            else (0, 255, 0),
            2
        )

        # Display threshold
        cv2.putText(
            annotated,
            f"THRESHOLD: {CROWD_THRESHOLD}",
            (30, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )

        # Display webcam window
        cv2.imshow(
            "Smart Hospital - Crowd Monitoring",
            annotated
        )

        # Press Q to exit
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):

            break

    camera.release()

    cv2.destroyAllWindows()


if __name__ == "__main__":

    main()