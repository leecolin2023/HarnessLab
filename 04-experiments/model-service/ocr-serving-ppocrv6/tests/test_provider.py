import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.provider import normalize_result


class FakeResult:
    json = {"res": {"rec_texts": ["DEMO"], "rec_scores": [0.97],
                    "rec_boxes": [[1, 2, 100, 25]]}}


class TestNormalization(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(normalize_result([FakeResult()])[0]["text"], "DEMO")

    def test_empty(self):
        self.assertEqual(normalize_result([{"res": {}}]), [])


if __name__ == "__main__":
    unittest.main()
