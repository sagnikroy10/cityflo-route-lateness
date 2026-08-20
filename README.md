# Cityflo Route Lateness

A small, standard-library Python pipeline answering: **is a selected route running late at a selected IST timestamp, and by how many minutes?**

## Problem and approach

The pipeline reads the supplied CSV bundle without modifying it, assigns pings to vehicle-trips, projects positions onto the ordered stop polyline, and calculates schedule-progress delay. It returns one route-level `LATE`, `EARLY`, `ON_TIME`, or `UNKNOWN` verdict with an audit trail.

Grains:

- Raw: one GPS ping.
- Resolved: one ping associated with one vehicle-trip.
- Output: one route at one timezone-aware `as_of` timestamp.

## Setup

Requires Python 3.11+ and no third-party packages. Download or copy the Cityflo CSV files into a local directory. Source data is read-only and is not committed.

```text
data/
  routes.csv
  stops.csv
  trips.csv
  bookings.csv
  gps_pings.csv
```

## Run

```powershell
python -m src.cli --data-dir C:\path\to\data --route-id 9 --as-of "2026-06-15T07:30:00+05:30"
python -m src.cli --data-dir C:\path\to\data --route-id 9 --as-of "2026-06-15T07:30:00+05:30" --json
```

The default data directory is `data/` relative to the project root.

## Output and UNKNOWN

The result includes the selected trip and ping, signed `delay_minutes`, `spatial_uncertainty_minutes`, expected schedule time at projected progress, quality policy, and an audit of every route-trip considered.

`UNKNOWN` always includes a structured reason, such as `STALE_PING`, `DELAYED_TELEMETRY`, `AMBIGUOUS_ACTIVE_TRIPS`, or `INSUFFICIENT_POSITION_PRECISION`.

## Assumptions and quality policy

- Timestamps must include an offset; Cityflo source timestamps are IST (`+05:30`).
- A 90-second freshness threshold is an operational assumption, not a fact of the historical dump.
- A 60-second server-ingest lag is a live-quality gate. Observed data has median lag 4 seconds and p95 6 seconds, while 451 pings exceed 60 seconds.
- Consecutive movement over 100 km/h is flagged as implausible. This isolates the observed V-02 corruption without deleting it.
- Projection error is never used as a 500 m rejection gate. It is exposed and converted to spatial uncertainty because the stop polyline is sparse.
- Operator 7 and Route 12 are processed normally. No hidden suppression or forced verdict exists.

See [DESIGN.md](DESIGN.md) for the complete rationale.

## Limitations

This is a batch replay over a static CSV extract. Stop geometry is not map-matched, schedule timing is interpolated by polyline distance, and a verdict can be `UNKNOWN` when position uncertainty overlaps a categorical boundary. Bookings are loaded and validated but are not used for the route-level schedule baseline; they would support a later rider-stop ETA mode.

## Real-time evolution

In production, ingest GPS events to an append-only stream, retain both event and receipt times, maintain state per vehicle-trip, apply the same quality rules under out-of-order arrivals, and publish versioned route snapshots. Alerting should suppress stale, delayed, or ambiguous telemetry while retaining its audit trail.

## Tests

```powershell
python -m unittest discover -s tests -t . -v
```
