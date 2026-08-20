"""Explicit quality rules for live route-lateness snapshots."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from .geometry import Point, haversine_m

FRESHNESS_SECONDS = 90
INGEST_LAG_SECONDS = 60
IMPLAUSIBLE_SPEED_KMPH = 100
CATEGORY_TOLERANCE_MINUTES = 2.0

@dataclass(frozen=True)
class QualityDecision:
    usable: bool
    flags: list[str]

def snapshot_quality(recorded_at: datetime, received_at: datetime, as_of: datetime) -> QualityDecision:
    flags: list[str] = []
    if recorded_at > as_of or received_at > as_of:
        flags.append('FUTURE_PING')
    if (as_of-recorded_at).total_seconds() > FRESHNESS_SECONDS or (as_of-received_at).total_seconds() > FRESHNESS_SECONDS:
        flags.append('STALE_PING')
    if (received_at-recorded_at).total_seconds() > INGEST_LAG_SECONDS:
        flags.append('DELAYED_TELEMETRY')
    return QualityDecision(not flags, flags)

def implied_speed_kmph(previous: Point, previous_at: datetime, current: Point, current_at: datetime) -> float | None:
    seconds = (current_at-previous_at).total_seconds()
    if seconds <= 0:
        return None
    return haversine_m(previous, current)/seconds*3.6

def classify(delay_minutes: float, uncertainty_minutes: float) -> str:
    lower, upper = delay_minutes-uncertainty_minutes, delay_minutes+uncertainty_minutes
    if lower > CATEGORY_TOLERANCE_MINUTES:
        return 'LATE'
    if upper < -CATEGORY_TOLERANCE_MINUTES:
        return 'EARLY'
    if lower >= -CATEGORY_TOLERANCE_MINUTES and upper <= CATEGORY_TOLERANCE_MINUTES:
        return 'ON_TIME'
    return 'UNKNOWN'
