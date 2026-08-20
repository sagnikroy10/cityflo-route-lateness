"""Polyline distance and projection utilities using only the Python standard library."""
from __future__ import annotations
from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt
from typing import Sequence

EARTH_RADIUS_M = 6_371_000.0

@dataclass(frozen=True)
class Point:
    lat: float
    lon: float

@dataclass(frozen=True)
class Projection:
    distance_along_m: float
    total_distance_m: float
    progress: float
    error_m: float
    segment_index: int

def haversine_m(a: Point, b: Point) -> float:
    d_lat, d_lon = radians(b.lat-a.lat), radians(b.lon-a.lon)
    x = sin(d_lat/2)**2 + cos(radians(a.lat))*cos(radians(b.lat))*sin(d_lon/2)**2
    return 2*EARTH_RADIUS_M*atan2(sqrt(x), sqrt(1-x))

def cumulative_distances(stops: Sequence[Point]) -> list[float]:
    if len(stops) < 2:
        raise ValueError('A route needs at least two ordered stops')
    result = [0.0]
    for a, b in zip(stops, stops[1:]):
        result.append(result[-1] + haversine_m(a, b))
    if result[-1] == 0:
        raise ValueError('Route polyline has zero length')
    return result

def project_point(point: Point, stops: Sequence[Point]) -> Projection:
    """Project a point onto the nearest stop-polyline segment in a local metre plane."""
    cumulative = cumulative_distances(stops)
    reference_lat = sum(s.lat for s in stops) / len(stops)
    x_scale, y_scale = 111_320*cos(radians(reference_lat)), 111_320.0
    px, py = point.lon*x_scale, point.lat*y_scale
    best: tuple[float, float, int] | None = None
    for index, (a, b) in enumerate(zip(stops, stops[1:])):
        ax, ay, bx, by = a.lon*x_scale, a.lat*y_scale, b.lon*x_scale, b.lat*y_scale
        dx, dy = bx-ax, by-ay
        denominator = dx*dx + dy*dy
        fraction = 0.0 if denominator == 0 else max(0.0, min(1.0, ((px-ax)*dx+(py-ay)*dy)/denominator))
        qx, qy = ax+fraction*dx, ay+fraction*dy
        error = sqrt((px-qx)**2 + (py-qy)**2)
        along = cumulative[index] + fraction*(cumulative[index+1]-cumulative[index])
        if best is None or error < best[0]:
            best = (error, along, index)
    assert best is not None
    error, along, index = best
    return Projection(along, cumulative[-1], max(0.0, min(1.0, along/cumulative[-1])), error, index)
