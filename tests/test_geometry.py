import unittest
from src.geometry import Point, cumulative_distances, project_point

class GeometryTests(unittest.TestCase):
    def test_distance_and_projection(self):
        stops = [Point(19.0,72.0), Point(19.0,72.01)]
        total = cumulative_distances(stops)[-1]
        projection = project_point(Point(19.0,72.005), stops)
        self.assertGreater(total, 900)
        self.assertAlmostEqual(projection.progress, .5, places=2)
        self.assertLess(projection.error_m, 1)

    def test_projection_error_is_diagnostic(self):
        projection = project_point(Point(19.01,72.005), [Point(19.0,72.0), Point(19.0,72.01)])
        self.assertGreater(projection.error_m, 1000)
        self.assertGreaterEqual(projection.progress, 0)
        self.assertLessEqual(projection.progress, 1)

if __name__ == '__main__': unittest.main()
