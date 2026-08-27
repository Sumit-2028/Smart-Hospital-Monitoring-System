from app.config import TRACKING_GRACE_FRAMES


class CrowdTracker:

    def __init__(self):

        self.people = {}

        self.previous_ids = set()

    def update(self, result, roi):

        detected_ids = set()

        if result.boxes is not None and result.boxes.is_track:

            boxes = result.boxes.xyxy.cpu().tolist()
            track_ids = result.boxes.id.int().cpu().tolist()

            for box, track_id in zip(boxes, track_ids):

                x1, y1, x2, y2 = box

                center_x = int((x1 + x2) / 2)
                center_y = int((y1 + y2) / 2)

                inside_roi = self.point_inside_roi(
                    center_x,
                    center_y,
                    roi
                )

                if inside_roi:

                    detected_ids.add(track_id)

                    if track_id not in self.people:

                        self.people[track_id] = {
                            "missing_frames": 0
                        }

                    else:

                        self.people[track_id][
                            "missing_frames"
                        ] = 0

        # Increase missing frame count
        for track_id in list(self.people.keys()):

            if track_id not in detected_ids:

                self.people[track_id][
                    "missing_frames"
                ] += 1

                if (
                    self.people[track_id][
                        "missing_frames"
                    ] > TRACKING_GRACE_FRAMES
                ):

                    del self.people[track_id]

        return set(self.people.keys())

    @staticmethod
    def point_inside_roi(x, y, roi):

        x1, y1, x2, y2 = roi

        return (
            x1 <= x <= x2
            and
            y1 <= y <= y2
        )

    def count(self):

        return len(self.people)

    def get_events(self):

        current_ids = set(self.people.keys())

        entered = current_ids - self.previous_ids
        left = self.previous_ids - current_ids

        self.previous_ids = current_ids.copy()

        return {
            "entered": entered,
            "left": left
        }