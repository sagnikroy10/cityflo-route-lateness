from __future__ import annotations
import argparse, json
from .pipeline import CityfloPipeline, parse_timestamp

def main() -> None:
    parser = argparse.ArgumentParser(description='Auditable Cityflo route lateness verdict')
    parser.add_argument('--route-id', required=True)
    parser.add_argument('--as-of', required=True, help='Timezone-aware ISO-8601 timestamp, e.g. 2026-06-15T07:30:00+05:30')
    parser.add_argument('--data-dir', default='data')
    parser.add_argument('--json', action='store_true', dest='as_json')
    args = parser.parse_args()
    result = CityfloPipeline(args.data_dir).verdict(args.route_id, parse_timestamp(args.as_of))
    if args.as_json:
        print(json.dumps(result, indent=2, sort_keys=True)); return
    display_name = result['route_name'].encode('ascii', 'backslashreplace').decode()
    print(f"{display_name} at {result['as_of']}: {result['verdict']}")
    print(f"reason: {result['reason'] or 'numeric schedule-progress estimate'}")
    print(f"delay_minutes: {result['delay_minutes']}")
    print(f"spatial_uncertainty_minutes: {result['spatial_uncertainty_minutes']}")
    print(f"trip_id: {result.get('trip_id')}")
if __name__ == '__main__': main()
