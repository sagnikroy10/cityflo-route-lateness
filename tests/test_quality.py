import unittest
from datetime import datetime, timedelta
from src.geometry import Point
from src.quality import classify, implied_speed_kmph, snapshot_quality

T = lambda text: datetime.fromisoformat(text)
class QualityTests(unittest.TestCase):
    def test_freshness_and_future_protection(self):
        as_of=T('2026-06-15T07:00:00+05:30')
        self.assertTrue(snapshot_quality(as_of-timedelta(seconds=10), as_of-timedelta(seconds=5), as_of).usable)
        self.assertIn('STALE_PING', snapshot_quality(as_of-timedelta(seconds=91), as_of-timedelta(seconds=5), as_of).flags)
        self.assertIn('FUTURE_PING', snapshot_quality(as_of, as_of+timedelta(seconds=1), as_of).flags)

    def test_ingest_lag(self):
        as_of=T('2026-06-15T07:00:00+05:30')
        self.assertIn('DELAYED_TELEMETRY', snapshot_quality(as_of-timedelta(seconds=61), as_of, as_of).flags)

    def test_v02_style_corruption(self):
        start=T('2026-06-15T07:00:00+05:30')
        speed=implied_speed_kmph(Point(19,72), start, Point(19.03,72), start+timedelta(seconds=10))
        self.assertGreater(speed, 100)

    def test_uncertainty_classification(self):
        self.assertEqual(classify(5,1), 'LATE')
        self.assertEqual(classify(-5,1), 'EARLY')
        self.assertEqual(classify(1,0.5), 'ON_TIME')
        self.assertEqual(classify(3,2), 'UNKNOWN')

if __name__ == '__main__': unittest.main()
