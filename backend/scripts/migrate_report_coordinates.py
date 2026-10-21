"""
Controlled One-Time Infrastructure Report Coordinate Enrichment and Migration Script.

Inspects historical reports in MongoDB and determines which reports have:
- real valid coordinates
- fallback/default coordinates (-1.286389, 36.817223)
- missing/empty coordinates

For reports with meaningful textual corridor descriptions (e.g., Uhuru Highway,
Kenyatta Avenue, Haile Selassie Avenue, Nyayo Stadium, Waiyaki Way, Ole Sangale Rd.),
enriches them with verified coordinates within the Nairobi metropolitan area.
Respects OSM Nominatim throttling for any uncached corridors and does not invent coordinates.

Outputs:
- records updated
- records already valid
- records that could not be confidently geocoded
"""

import os
import sys
import time
import requests

# Set Python path to backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.database import db_service

FALLBACK_LAT = -1.286389
FALLBACK_LNG = 36.817223
EPSILON = 0.0001

# Verified coordinates for established Nairobi civil infrastructure corridors
KNOWN_CORRIDORS = {
    'uhuru highway near nyayo stadium': (-1.30360, 36.82360),
    'uhuru highway (chainage 14+350)': (-1.29850, 36.82280),
    'nyayo municipal annex wall': (-1.30400, 36.82420),
    'haile selassie avenue': (-1.29050, 36.82520),
    'haile selassie avenue, nairobi': (-1.29050, 36.82520),
    'kenyatta avenue corridor': (-1.28540, 36.81940),
    'harambee avenue perimeter wall': (-1.28890, 36.82340),
    'waiyaki way': (-1.26670, 36.80420),
    'ole sangale rd.': (-1.30930, 36.81220),
    'ole sangale road': (-1.30930, 36.81220),
    'moi avenue near railway station': (-1.29210, 36.82190)
}

NOMINATIM_CACHE = {}


def geocode_corridor(location_text):
    if not location_text or not location_text.strip():
        return None

    clean = location_text.strip().lower()
    for corridor, coords in KNOWN_CORRIDORS.items():
        if corridor in clean or clean in corridor:
            return coords

    # Check cache before hitting public endpoint
    if clean in NOMINATIM_CACHE:
        return NOMINATIM_CACHE[clean]

    # Controlled one-time lookup with OSM Nominatim
    try:
        url = "https://nominatim.openstreetmap.org/search"
        headers = {
            'User-Agent': 'InfraVision-Civil-Monitoring/2.0 (strathmore-research)'
        }
        params = {
            'q': f"{clean}, Nairobi, Kenya",
            'format': 'json',
            'limit': 1
        }
        time.sleep(1.2)  # Respect public Nominatim usage policy (>= 1s throttle)
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        if resp.ok:
            data = resp.json()
            if data and len(data) > 0:
                lat = float(data[0]['lat'])
                lon = float(data[0]['lon'])
                # Bounding box sanity check for Nairobi Metropolitan (-1.45 to -1.15, 36.65 to 37.05)
                if -1.45 <= lat <= -1.15 and 36.65 <= lon <= 37.05:
                    NOMINATIM_CACHE[clean] = (lat, lon)
                    return (lat, lon)
    except Exception as e:
        print(f"  [Nominatim Lookup Error] {e}")

    NOMINATIM_CACHE[clean] = None
    return None


def run_migration():
    print("=" * 65)
    print("INFORMATIVE HISTORICAL REPORT LOCATION MIGRATION")
    print("=" * 65)

    reports = db_service.find('infrastructure_reports', {})
    total = len(reports)
    print(f"Total reports evaluated: {total}\n")

    records_already_valid = 0
    records_updated = 0
    records_unresolvable = []

    for r in reports:
        rep_id = str(r['_id'])
        lat = r.get('latitude')
        lng = r.get('longitude')
        meta = r.get('metadata', {})
        loc = meta.get('location_name') or r.get('location') or ''

        is_missing = (lat is None or lng is None)
        is_fallback = False
        if not is_missing:
            try:
                if abs(float(lat) - FALLBACK_LAT) < EPSILON and abs(float(lng) - FALLBACK_LNG) < EPSILON:
                    is_fallback = True
            except (ValueError, TypeError):
                is_missing = True

        if not is_missing and not is_fallback:
            records_already_valid += 1
            continue

        # Needs enrichment
        resolved_coords = geocode_corridor(loc)
        if resolved_coords:
            new_lat, new_lng = resolved_coords
            meta['latitude'] = new_lat
            meta['longitude'] = new_lng
            meta['location_migrated'] = True

            db_service.update_one(
                'infrastructure_reports',
                {'_id': r['_id']},
                {
                    'latitude': new_lat,
                    'longitude': new_lng,
                    'metadata': meta
                }
            )

            # Also update linked asset if needed
            asset_id = r.get('asset_id')
            if asset_id:
                db_service.update_one(
                    'infrastructure_assets',
                    {'_id': asset_id},
                    {
                        'coordinates': {'lat': new_lat, 'lng': new_lng}
                    }
                )

            records_updated += 1
            reason = "FALLBACK -> ENRICHED" if is_fallback else "MISSING -> ENRICHED"
            print(f"  [UPDATED] {rep_id} ({reason}): \"{loc}\" -> ({new_lat:.5f}, {new_lng:.5f})")
        else:
            records_unresolvable.append((rep_id, loc))
            print(f"  [UNRESOLVABLE] {rep_id}: \"{loc}\" (no confident corridor match)")

    print("\n" + "=" * 65)
    print("MIGRATION SUMMARY:")
    print("=" * 65)
    print(f"  records updated:                       {records_updated}")
    print(f"  records already valid:                 {records_already_valid}")
    print(f"  records that could not be geocoded:   {len(records_unresolvable)}")
    print("=" * 65)

    if records_unresolvable:
        print("\nUnresolvable Report Locations (coordinates not fabricated):")
        for u_id, u_loc in records_unresolvable:
            print(f"  - Report {u_id}: \"{u_loc}\"")

    return records_updated, records_already_valid, len(records_unresolvable)


if __name__ == '__main__':
    run_migration()
