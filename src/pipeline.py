"""Read-only CSV pipeline for an auditable Cityflo route lateness verdict."""
from __future__ import annotations
import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from .geometry import Point, Projection, project_point
from .quality import FRESHNESS_SECONDS, INGEST_LAG_SECONDS, IMPLAUSIBLE_SPEED_KMPH, classify, implied_speed_kmph, snapshot_quality

CONTEXT_BEFORE = timedelta(minutes=15)
CONTEXT_AFTER = timedelta(minutes=90)
HIGH_PROJECTION_ERROR_M = 1500.0  # diagnostic only; never a hard rejection

@dataclass(frozen=True)
class Route:
    route_id: str; route_name: str; runtime_min: int
@dataclass(frozen=True)
class Trip:
    trip_id: str; route_id: str; vehicle_id: str; service_date: str; start: datetime; end: datetime
@dataclass
class ResolvedPing:
    ping_id: str; vehicle_id: str; operator_id: str; recorded_at: datetime; received_at: datetime; point: Point
    trip_id: str | None = None; route_id: str | None = None; progress: float | None = None
    projection_error_m: float | None = None; route_length_m: float | None = None; flags: list[str] = field(default_factory=list)

def parse_timestamp(value: str) -> datetime:
    value = value.strip().replace('Z', '+00:00')
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError(f'timestamp is not timezone-aware: {value}')
    return result

def read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    if not path.exists(): raise FileNotFoundError(f'Missing required dataset: {path}')
    with path.open(newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f'{path.name} missing required columns: {sorted(required-set(reader.fieldnames or []))}')
        rows = list(reader)
    if not rows: raise ValueError(f'{path.name} is empty')
    if any(any(value is None or value == '' for value in row.values()) for row in rows):
        raise ValueError(f'{path.name} contains blank values; no rows were silently dropped')
    return rows

class CityfloPipeline:
    def __init__(self, data_dir: str | Path):
        root = Path(data_dir)
        route_rows = read_csv(root/'routes.csv', {'route_id','route_name','scheduled_runtime_min'})
        stop_rows = read_csv(root/'stops.csv', {'stop_id','lat','lon','route_id','seq'})
        trip_rows = read_csv(root/'trips.csv', {'trip_id','route_id','vehicle_id','service_date','scheduled_start','scheduled_end'})
        self.bookings = read_csv(root/'bookings.csv', {'booking_id','trip_id','boarding_stop_id','booked_at','promised_eta'})
        ping_rows = read_csv(root/'gps_pings.csv', {'ping_id','vehicle_id','operator_id','lat','lon','recorded_at','received_at'})
        self.routes = {r['route_id']: Route(r['route_id'], r['route_name'], int(r['scheduled_runtime_min'])) for r in route_rows}
        self.stops: dict[str, list[Point]] = {route_id: [] for route_id in self.routes}
        for row in sorted(stop_rows, key=lambda r: (r['route_id'], int(r['seq']))):
            if row['route_id'] not in self.stops: raise ValueError(f'orphan stop route {row["route_id"]}')
            self.stops[row['route_id']].append(Point(float(row['lat']), float(row['lon'])))
        self.trips = [Trip(r['trip_id'],r['route_id'],r['vehicle_id'],r['service_date'],parse_timestamp(r['scheduled_start']),parse_timestamp(r['scheduled_end'])) for r in trip_rows]
        if any(t.route_id not in self.routes for t in self.trips): raise ValueError('trips.csv references unknown route')
        self.raw_ping_count = len(ping_rows)
        self.pings = [ResolvedPing(r['ping_id'],r['vehicle_id'],r['operator_id'],parse_timestamp(r['recorded_at']),parse_timestamp(r['received_at']),Point(float(r['lat']),float(r['lon']))) for r in ping_rows]
        self._resolve_pings()

    def _resolve_pings(self) -> None:
        for ping in self.pings:
            candidates = [t for t in self.trips if t.vehicle_id == ping.vehicle_id and t.service_date == ping.recorded_at.date().isoformat() and t.start-CONTEXT_BEFORE <= ping.recorded_at <= t.end+CONTEXT_AFTER]
            if not candidates:
                ping.flags.append('NO_TRIP_ASSIGNMENT'); continue
            if len(candidates) > 1:
                ping.flags.append('AMBIGUOUS_TRIP'); continue
            trip = candidates[0]; projection: Projection = project_point(ping.point, self.stops[trip.route_id])
            ping.trip_id, ping.route_id = trip.trip_id, trip.route_id
            ping.progress, ping.projection_error_m, ping.route_length_m = projection.progress, projection.error_m, projection.total_distance_m
            if projection.error_m > HIGH_PROJECTION_ERROR_M: ping.flags.append('HIGH_PROJECTION_ERROR')
            if ping.recorded_at < trip.start: ping.flags.append('PRE_DEPARTURE')
            if ping.recorded_at > trip.end and projection.progress >= .98: ping.flags.append('COMPLETED_POSITION')
        by_trip: dict[str, list[ResolvedPing]] = {}
        for ping in self.pings:
            if ping.trip_id: by_trip.setdefault(ping.trip_id, []).append(ping)
        for records in by_trip.values():
            records.sort(key=lambda p: p.recorded_at)
            previous: ResolvedPing | None = None
            for ping in records:
                if previous is not None:
                    speed = implied_speed_kmph(previous.point, previous.recorded_at, ping.point, ping.recorded_at)
                    if speed is not None and speed > IMPLAUSIBLE_SPEED_KMPH: ping.flags.append('IMPLAUSIBLE_MOVEMENT')
                previous = ping

    def _trip_records(self, trip: Trip) -> list[ResolvedPing]:
        return [p for p in self.pings if p.trip_id == trip.trip_id]

    @staticmethod
    def _serialize_ping(ping: ResolvedPing | None) -> dict[str, Any] | None:
        if ping is None: return None
        return {'ping_id': ping.ping_id, 'vehicle_id': ping.vehicle_id, 'operator_id': ping.operator_id, 'recorded_at': ping.recorded_at.isoformat(), 'received_at': ping.received_at.isoformat(), 'progress': ping.progress, 'projection_error_m': ping.projection_error_m, 'flags': ping.flags}

    def verdict(self, route_id: str, as_of: datetime) -> dict[str, Any]:
        if as_of.tzinfo is None: raise ValueError('as_of must be timezone-aware')
        if route_id not in self.routes: raise ValueError(f'Unknown route_id {route_id}')
        route = self.routes[route_id]
        in_context = [t for t in self.trips if t.route_id == route_id and t.start-CONTEXT_BEFORE <= as_of <= t.end+CONTEXT_AFTER]
        audit: list[dict[str, Any]] = []
        active: list[tuple[Trip, ResolvedPing]] = []
        for trip in in_context:
            records = [p for p in self._trip_records(trip) if p.received_at <= as_of and p.recorded_at <= as_of]
            latest = max(records, key=lambda p: p.received_at, default=None)
            item: dict[str, Any] = {'trip_id':trip.trip_id,'vehicle_id':trip.vehicle_id,'scheduled_start':trip.start.isoformat(),'scheduled_end':trip.end.isoformat(),'latest_received_ping':self._serialize_ping(latest)}
            if latest is None:
                item['candidate_reason'] = 'NO_PING_RECEIVED_BY_AS_OF'; audit.append(item); continue
            quality = snapshot_quality(latest.recorded_at, latest.received_at, as_of)
            flags = list(dict.fromkeys(latest.flags + quality.flags))
            if latest.recorded_at < trip.start: flags.append('PRE_DEPARTURE')
            if latest.recorded_at > trip.end and (latest.progress or 0) >= .98: flags.append('COMPLETED_POSITION')
            item['flags'] = flags
            blocking = {'FUTURE_PING','STALE_PING','DELAYED_TELEMETRY','IMPLAUSIBLE_MOVEMENT','PRE_DEPARTURE','COMPLETED_POSITION','AMBIGUOUS_TRIP','NO_TRIP_ASSIGNMENT'}
            if any(flag in blocking for flag in flags):
                item['candidate_reason'] = next(flag for flag in flags if flag in blocking); audit.append(item); continue
            item['candidate_reason'] = 'ACTIVE_CANDIDATE'; audit.append(item); active.append((trip, latest))
        base = {'route_id':route_id,'route_name':route.route_name,'as_of':as_of.isoformat(),'raw_ping_count':self.raw_ping_count,'quality_policy':{'freshness_seconds':FRESHNESS_SECONDS,'ingest_lag_seconds':INGEST_LAG_SECONDS,'implausible_speed_kmph':IMPLAUSIBLE_SPEED_KMPH},'trip_audit':audit}
        if not in_context:
            return base | {'verdict':'UNKNOWN','reason':'NO_SCHEDULED_TRIP','delay_minutes':None,'spatial_uncertainty_minutes':None}
        if len(active) == 0:
            reasons = sorted({x.get('candidate_reason','NO_TRUSTWORTHY_ACTIVE_TRIP') for x in audit})
            return base | {'verdict':'UNKNOWN','reason':reasons[0] if len(reasons)==1 else 'NO_TRUSTWORTHY_ACTIVE_TRIP','delay_minutes':None,'spatial_uncertainty_minutes':None}
        if len(active) > 1:
            return base | {'verdict':'UNKNOWN','reason':'AMBIGUOUS_ACTIVE_TRIPS','delay_minutes':None,'spatial_uncertainty_minutes':None}
        trip, ping = active[0]
        assert ping.progress is not None and ping.projection_error_m is not None and ping.route_length_m is not None
        scheduled_at_progress = trip.start + (trip.end-trip.start)*ping.progress
        delay = (as_of-scheduled_at_progress).total_seconds()/60
        uncertainty = ping.projection_error_m/ping.route_length_m*route.runtime_min
        result = base | {'trip_id':trip.trip_id,'vehicle_id':trip.vehicle_id,'verdict':classify(delay,uncertainty),'reason':None,'delay_minutes':round(delay,3),'spatial_uncertainty_minutes':round(uncertainty,3),'scheduled_time_at_progress':scheduled_at_progress.isoformat(),'selected_ping':self._serialize_ping(ping)}
        if result['verdict'] == 'UNKNOWN': result['reason'] = 'INSUFFICIENT_POSITION_PRECISION'
        return result
