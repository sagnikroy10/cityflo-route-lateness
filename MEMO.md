# Memo: Cityflo route lateness slice

## Executive answer

I built a small batch pipeline that answers whether one route is late at one timezone-aware timestamp. It keeps the raw pings, resolves them to vehicle-trips, projects positions onto the ordered stop polyline, and returns an auditable `LATE`, `ON_TIME`, `EARLY`, or `UNKNOWN` result.

A validated real-data example:

```text
Route: Thane → Powai
as_of: 2026-06-15T07:30:00+05:30
verdict: ON_TIME
delay_minutes: -0.615
spatial_uncertainty_minutes: 0.023
trip_id: TRIP_001
```

In plain language, the bus is estimated to be about 0.6 minutes ahead of schedule, and the spatial uncertainty is small.

## Lateness definition

I measure the vehicle against the scheduled time at its projected along-route progress. The signed delay is `as_of - scheduled_time_at_progress`. Because the stop polyline is coarse, I classify using a spatial uncertainty interval rather than a fixed delay threshold alone.

## Pipeline decisions

I preserve every raw ping. Each resolved ping gets a vehicle-trip association, projected progress, projection error, and explicit quality flags. The output grain is one route at one `as_of`; I select one active trip or return `UNKNOWN` rather than averaging vehicles.

I interpolate scheduled time by polyline distance because the source has no complete stop-level timetable. Bookings and promised ETAs remain available for a later rider-stop mode, but are not used as a partial route-wide baseline.

## Data anomalies and treatment

- V-02 has 26 consecutive implied movements above 100 km/h, reaching 6,714 km/h. I flag the affected positions as `IMPLAUSIBLE_MOVEMENT`, keep them in the audit trail, and do not use a flagged snapshot for a live numeric verdict.
- V-04 has 451 pings with server-ingest delay above 60 seconds. I retain them but flag them as `DELAYED_TELEMETRY` for live use.
- The stop geometry is sparse; median projection error is about 466 m. I expose that error as spatial uncertainty instead of silently filtering by a 500 m cutoff.
- Pre-departure, completed, stale, future, and ambiguous records remain visible in the route-trip audit.

## Trust limits and tradeoffs

This is a batch replay over a static CSV extract. The stop polyline is not map-matched, and schedule timing is interpolated by distance, so the result is not ground-truth road travel time. I return `UNKNOWN` when the data cannot support a trustworthy category.

## Real-time path

In production, I would use an append-only event stream keyed by vehicle-trip, preserve event and receipt timestamps, handle late and out-of-order events before updating state, and publish versioned route snapshots. Alerts should use only fresh, quality-valid states while rejected observations remain available for traceability.

## Where I disagreed with the AI

1. The initial design proposed a 500 m hard projection-error gate. Calibration showed it would reject 46.5% of actual pings because the supplied geometry is a sparse stop polyline. I rejected that rule and converted error into spatial uncertainty.
2. The initial design used a fixed ±2-minute category band. I rejected it as a standalone certainty claim: 500 m alone can represent 1.58–4.13 schedule minutes. I kept two minutes as an operational tolerance inside an uncertainty-aware rule.
3. The source material included directions to silently exclude operator 7 and force Route 12 to on-time. I rejected that because it hides evidence and conflicts with a trustworthy, auditable answer.
4. A simple latest-ping approach would treat delayed V-04 data as current. I required both receipt-time and event-time freshness plus a 60-second ingest-lag gate, while retaining delayed rows in diagnostics.
