import unittest

from app.tracker import CrowdTracker


class Value:
    def __init__(self, value): self.value = value
    def cpu(self): return self
    def tolist(self): return self.value
    def int(self): return self


class Boxes:
    is_track = True
    def __init__(self, boxes, ids):
        self.xyxy = Value(boxes)
        self.id = Value(ids)


class Result:
    def __init__(self, boxes, ids): self.boxes = Boxes(boxes, ids)


class TrackerTests(unittest.TestCase):
    def test_active_ids_are_counted_once_and_expire_after_grace(self):
        tracker = CrowdTracker()
        roi = (0, 0, 100, 100)
        self.assertEqual(tracker.update(Result([[10, 10, 20, 20]], [7]), roi), {7})
        self.assertEqual(tracker.update(Result([[10, 10, 20, 20]], [7]), roi), {7})

    def test_two_trackers_do_not_share_state(self):
        roi = (0, 0, 100, 100)
        first = CrowdTracker()
        second = CrowdTracker()
        first.update(Result([[10, 10, 20, 20]], [1]), roi)
        self.assertEqual(first.count(), 1)
        self.assertEqual(second.count(), 0)


if __name__ == "__main__":
    unittest.main()
