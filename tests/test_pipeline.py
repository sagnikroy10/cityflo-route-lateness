import csv, tempfile, unittest
from datetime import datetime
from pathlib import Path
from src.pipeline import CityfloPipeline

AS='2026-06-15T07:05:00+05:30'
def write(path, name, fields, rows):
    with (path/name).open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields);w.writeheader();w.writerows(rows)
def bundle(extra_trips=None, pings=None):
    root=Path(tempfile.mkdtemp())
    write(root,'routes.csv',['route_id','route_name','scheduled_runtime_min'],[{'route_id':'1','route_name':'Test','scheduled_runtime_min':'10'}])
    write(root,'stops.csv',['stop_id','lat','lon','route_id','seq'],[{'stop_id':'a','lat':'19','lon':'72','route_id':'1','seq':'1'},{'stop_id':'b','lat':'19','lon':'72.01','route_id':'1','seq':'2'}])
    trips=[{'trip_id':'t1','route_id':'1','vehicle_id':'v1','service_date':'2026-06-15','scheduled_start':'2026-06-15T07:00:00+05:30','scheduled_end':'2026-06-15T07:10:00+05:30'}]
    if extra_trips: trips.extend(extra_trips)
    write(root,'trips.csv',list(trips[0]),trips)
    write(root,'bookings.csv',['booking_id','trip_id','boarding_stop_id','booked_at','promised_eta'],[{'booking_id':'b1','trip_id':'t1','boarding_stop_id':'a','booked_at':'2026-06-14T07:00:00+05:30','promised_eta':'2026-06-15T07:00:00+05:30'}])
    default=[{'ping_id':'p1','vehicle_id':'v1','operator_id':'7','lat':'19','lon':'72.005','recorded_at':AS,'received_at':AS}]
    write(root,'gps_pings.csv',list(default[0]),pings or default)
    return root
class PipelineTests(unittest.TestCase):
    def test_numeric_on_time_and_operator_is_retained(self):
        result=CityfloPipeline(bundle()).verdict('1',datetime.fromisoformat(AS))
        self.assertEqual(result['verdict'],'ON_TIME');self.assertEqual(result['selected_ping']['operator_id'],'7')
    def test_late_early_and_precision_unknown(self):
        root=bundle(); p=CityfloPipeline(root)
        self.assertEqual(p.verdict('1',datetime.fromisoformat('2026-06-15T07:09:00+05:30'))['verdict'],'UNKNOWN') # stale snapshot
        late=bundle(pings=[{'ping_id':'p1','vehicle_id':'v1','operator_id':'5','lat':'19','lon':'72.005','recorded_at':'2026-06-15T07:09:00+05:30','received_at':'2026-06-15T07:09:00+05:30'}])
        self.assertEqual(CityfloPipeline(late).verdict('1',datetime.fromisoformat('2026-06-15T07:09:00+05:30'))['verdict'],'LATE')
        early=bundle(pings=[{'ping_id':'p1','vehicle_id':'v1','operator_id':'5','lat':'19','lon':'72.005','recorded_at':'2026-06-15T07:01:00+05:30','received_at':'2026-06-15T07:01:00+05:30'}])
        self.assertEqual(CityfloPipeline(early).verdict('1',datetime.fromisoformat('2026-06-15T07:01:00+05:30'))['verdict'],'EARLY')
    def test_delayed_future_predeparture_and_completed_are_unknown(self):
        delayed=bundle(pings=[{'ping_id':'p','vehicle_id':'v1','operator_id':'5','lat':'19','lon':'72.005','recorded_at':'2026-06-15T07:03:50+05:30','received_at':'2026-06-15T07:05:00+05:30'}])
        self.assertEqual(CityfloPipeline(delayed).verdict('1',datetime.fromisoformat(AS))['reason'],'DELAYED_TELEMETRY')
        pre=bundle(pings=[{'ping_id':'p','vehicle_id':'v1','operator_id':'5','lat':'19','lon':'72','recorded_at':'2026-06-15T06:55:00+05:30','received_at':'2026-06-15T06:55:00+05:30'}])
        self.assertEqual(CityfloPipeline(pre).verdict('1',datetime.fromisoformat('2026-06-15T06:55:00+05:30'))['reason'],'PRE_DEPARTURE')
    def test_multiple_active_trips_are_ambiguous(self):
        trip={'trip_id':'t2','route_id':'1','vehicle_id':'v2','service_date':'2026-06-15','scheduled_start':'2026-06-15T07:00:00+05:30','scheduled_end':'2026-06-15T07:10:00+05:30'}
        pings=[{'ping_id':'p1','vehicle_id':'v1','operator_id':'5','lat':'19','lon':'72.005','recorded_at':AS,'received_at':AS},{'ping_id':'p2','vehicle_id':'v2','operator_id':'5','lat':'19','lon':'72.005','recorded_at':AS,'received_at':AS}]
        self.assertEqual(CityfloPipeline(bundle([trip],pings)).verdict('1',datetime.fromisoformat(AS))['reason'],'AMBIGUOUS_ACTIVE_TRIPS')
    def test_v02_style_latest_jump_is_rejected(self):
        pings=[{'ping_id':'p1','vehicle_id':'v1','operator_id':'5','lat':'19','lon':'72','recorded_at':'2026-06-15T07:04:50+05:30','received_at':'2026-06-15T07:04:50+05:30'},{'ping_id':'p2','vehicle_id':'v1','operator_id':'5','lat':'19.03','lon':'72','recorded_at':AS,'received_at':AS}]
        self.assertEqual(CityfloPipeline(bundle(pings=pings)).verdict('1',datetime.fromisoformat(AS))['reason'],'IMPLAUSIBLE_MOVEMENT')
if __name__ == '__main__': unittest.main()
