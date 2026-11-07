import urllib.request
import urllib.parse
import json
import logging
from datetime import datetime, timezone, timedelta
from .database import db_service

logger = logging.getLogger('WeatherService')

class WeatherService:
    """
    Sections 36, 37 & 38: Open-Meteo Historical Weather Integration.
    Retrieves and caches daily precipitation data from Open-Meteo Archive API
    to compute evidence-based temporal associations between rainfall windows and defect reports.
    
    CRITICAL CONSTRAINT: All statements must be framed strictly as 'Observed association',
    NEVER as causal claims ('Rain caused these potholes').
    """
    API_URL = "https://archive-api.open-meteo.com/v1/archive"

    def __init__(self):
        pass

    def get_historical_precipitation(self, latitude: float, longitude: float, start_date_str: str, end_date_str: str):
        """
        Retrieves daily precipitation sum (mm) for the given coordinate and date span.
        Caches in MongoDB collection 'weather_cache' to avoid repeated external calls.
        """
        try:
            lat_r = round(float(latitude), 2)
            lng_r = round(float(longitude), 2)
        except (ValueError, TypeError):
            return None

        cache_key = f"{lat_r}_{lng_r}_{start_date_str}_{end_date_str}"
        try:
            cached = db_service.find_one('weather_cache', {'cache_key': cache_key})
            if cached and 'daily' in cached:
                return cached['daily']
        except Exception as e:
            logger.warning(f"Failed reading weather cache: {e}")

        # Fetch from Open-Meteo Historical Weather API
        params = {
            'latitude': lat_r,
            'longitude': lng_r,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'daily': 'precipitation_sum,precipitation_hours',
            'timezone': 'UTC'
        }
        query_string = urllib.parse.urlencode(params)
        req_url = f"{self.API_URL}?{query_string}"

        try:
            req = urllib.request.Request(req_url, headers={'User-Agent': 'InfraVision-Civil-Infrastructure/2.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    payload = json.loads(response.read().decode('utf-8'))
                    daily = payload.get('daily')
                    if daily:
                        try:
                            db_service.insert('weather_cache', {
                                'cache_key': cache_key,
                                'latitude': lat_r,
                                'longitude': lng_r,
                                'start_date': start_date_str,
                                'end_date': end_date_str,
                                'daily': daily,
                                'cached_at': datetime.now(timezone.utc).isoformat()
                            })
                        except Exception as ins_err:
                            logger.warning(f"Failed storing weather cache: {ins_err}")
                        return daily
        except Exception as net_err:
            logger.warning(f"Open-Meteo weather request failed for {req_url}: {net_err}")
            return None

        return None

    def analyze_weather_associations(self, reports):
        """
        Computes evidence-based rainfall association across reports with coordinates.
        Checks preceding 7-day precipitation for reports.
        """
        if not reports:
            return None

        # Filter reports with valid coordinates and dates
        eligible = []
        for rep in reports:
            meta = rep.get('metadata') or {}
            lat = rep.get('latitude') or meta.get('latitude')
            lng = rep.get('longitude') or meta.get('longitude')
            dt_str = rep.get('date_submitted') or rep.get('created_at')
            if lat is not None and lng is not None and dt_str:
                try:
                    clean_str = dt_str.replace('Z', '+00:00')
                    if '+' in clean_str[10:] or '-' in clean_str[10:]:
                        dt = datetime.fromisoformat(clean_str)
                    else:
                        dt = datetime.fromisoformat(clean_str).replace(tzinfo=timezone.utc)
                    eligible.append({
                        'report_id': rep.get('report_id') or str(rep.get('_id')),
                        'defect_class': meta.get('defect_class') or rep.get('defect_class') or 'Defect',
                        'location': meta.get('location_name') or rep.get('location_name') or 'Monitored Corridor',
                        'latitude': float(lat),
                        'longitude': float(lng),
                        'date': dt
                    })
                except Exception:
                    continue

        if len(eligible) < 3:
            return {
                'has_sufficient_data': False,
                'message': 'Not enough historical coordinate-linked reports for weather correlation analysis.',
                'qualification': 'Observed historical association. Pavement deterioration involves coupled engineering factors including cumulative traffic loading, subgrade moisture, and drainage capacity.'
            }

        # Analyze preceding 7 days rainfall for up to 15 recent reports
        eligible_sample = sorted(eligible, key=lambda x: x['date'], reverse=True)[:15]
        wet_period_reports = 0
        total_analyzed = 0

        for item in eligible_sample:
            rep_date = item['date']
            start_dt = rep_date - timedelta(days=7)
            end_dt = rep_date - timedelta(days=1)
            start_str = start_dt.strftime('%Y-%m-%d')
            end_str = end_dt.strftime('%Y-%m-%d')

            daily = self.get_historical_precipitation(item['latitude'], item['longitude'], start_str, end_str)
            if daily and 'precipitation_sum' in daily:
                precip_vals = [p for p in daily['precipitation_sum'] if p is not None]
                total_precip_7d = sum(precip_vals) if precip_vals else 0.0
                total_analyzed += 1
                if total_precip_7d >= 10.0:  # ≥ 10mm accumulated rainfall
                    wet_period_reports += 1

        if total_analyzed < 3:
            return {
                'has_sufficient_data': False,
                'message': 'Insufficient cached meteorological observations.',
                'qualification': 'Observed historical association. Pavement deterioration involves coupled engineering factors including cumulative traffic loading, subgrade moisture, and drainage capacity.'
            }

        pct = round((wet_period_reports / total_analyzed) * 100)
        statement = f"{wet_period_reports} of {total_analyzed} defect reports ({pct}%) on monitored corridors occurred within 7 days following elevated rainfall (≥ 10 mm accumulated precipitation)."

        return {
            'has_sufficient_data': True,
            'total_analyzed': total_analyzed,
            'wet_period_reports': wet_period_reports,
            'percentage': pct,
            'statement': statement,
            'window': '7-day preceding precipitation',
            'provider': 'Open-Meteo Historical Weather API',
            'qualification': 'Observed historical association. Pavement deterioration involves coupled engineering factors including cumulative traffic loading, subgrade moisture, and drainage capacity.'
        }

weather_service = WeatherService()
