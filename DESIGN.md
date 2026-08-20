# Design: route lateness at an `as_of` timestamp

## Scope and grains

- **Raw grain:** one GPS ping, preserved without alteration.
- **Resolved grain:** one ping associated with one vehicle-trip, with projected route progress and quality flags.
- **Output grain:** one selected route at one timezone-aware IST `as_of` timestamp.

## Trip assignment and projection

A ping is associated only with a same-vehicle, same-service-date trip in a context window of 15 minutes before scheduled start through 90 minutes after scheduled end. Zero candidates are `NO_TRIP_ASSIGNMENT`; multiple candidates are `AMBIGUOUS_TRIP`. Pre-departure and completed positions remain diagnostic rows and cannot create a current lateness verdict.

Stops are ordered by `seq` into line segments. A point is projected to its nearest segment in a local metre plane; the result provides progress, cumulative route distance, and `projection_error_m`. This is a stop polyline, not road map matching.

## Lateness and uncertainty

`scheduled_time_at_progress = scheduled_start + progress × (scheduled_end - scheduled_start)`

`delay_minutes = as_of - scheduled_time_at_progress`

`spatial_uncertainty_minutes = projection_error_m / route_polyline_length_m × scheduled_runtime_minutes`

Two minutes is an operational tolerance, not the full measurement error:

- `LATE` when `delay - uncertainty > 2`.
- `EARLY` when `delay + uncertainty < -2`.
- `ON_TIME` when the complete interval lies within ±2.
- Otherwise `UNKNOWN` with `INSUFFICIENT_POSITION_PRECISION`.

## Quality policy

Raw records are never deleted or silently suppressed. Each resolved ping retains flags.

- **Freshness:** both event and receipt timestamps must be within 90 seconds of `as_of`. This is an explicit operational assumption; the observed stream has no internal receipt gaps above 90 seconds.
- **Ingest lag:** `received_at - recorded_at` must be at most 60 seconds. Observed median is 4 seconds and p95 is 6 seconds, while 451 records exceed 60 seconds, up to 47.1 minutes.
- **Movement:** consecutive points above 100 km/h are implausible. The dataset contains 26 such pairs, all on V-02, max 6,714 km/h.
- **Projection:** no 500 m hard rejection exists. A 500 m cutoff would reject 46.5% of supplied pings; high error is diagnostic and feeds uncertainty.
- **No special suppression:** operator 7 is retained, and Route 12 is never forced to on-time.

## Active trip and UNKNOWN

For the requested route, evaluate scheduled trips in the context window. Select exactly one trip with a latest ping received by `as_of` that passes freshness, ingest-lag, movement, pre-departure, and completion checks. Zero candidates return a specific `UNKNOWN`; multiple candidates return `AMBIGUOUS_ACTIVE_TRIPS`. Vehicles are never averaged.

This favors an honest `UNKNOWN` over a stale or corrupted live claim.
