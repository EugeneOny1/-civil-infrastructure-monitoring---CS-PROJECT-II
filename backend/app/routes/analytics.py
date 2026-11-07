from datetime import datetime, timezone, timedelta
import calendar
from collections import defaultdict
from flask import Blueprint, jsonify, request, make_response
from ..services.database import db_service
from ..services.weather_service import weather_service
from ..utils.auth_helpers import role_required

KENYA_47_COUNTIES = [
    'Mombasa', 'Kwale', 'Kilifi', 'Tana River', 'Lamu', 'Taita Taveta',
    'Garissa', 'Wajir', 'Mandera', 'Marsabit', 'Isiolo', 'Meru',
    'Tharaka Nithi', 'Embu', 'Kitui', 'Machakos', 'Makueni', 'Nyandarua',
    'Nyeri', 'Kirinyaga', "Murang'a", 'Kiambu', 'Turkana', 'West Pokot',
    'Samburu', 'Trans Nzoia', 'Uasin Gishu', 'Elgeyo Marakwet', 'Nandi',
    'Baringo', 'Laikipia', 'Nakuru', 'Narok', 'Kajiado', 'Kericho',
    'Bomet', 'Kakamega', 'Vihiga', 'Bungoma', 'Busia', 'Siaya',
    'Kisumu', 'Homa Bay', 'Migori', 'Kisii', 'Nyamira', 'Nairobi'
]

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

@analytics_bp.route('/summary', methods=['GET'])
@role_required('engineer', 'admin')
def get_summary(current_user):
    """
    FR-07: Summary metrics for the Engineer Monitoring Dashboard (Figure 4.7).
    """
    from ..models.report import InfrastructureReport

    all_reports = db_service.find('infrastructure_reports')
    all_assessments = db_service.find('ai_assessments')

    # Active defect queue: cases requiring active professional attention (excludes Resolved)
    active_count = sum(1 for r in all_reports if InfrastructureReport.normalize_lifecycle_status(r.get('status')) in [InfrastructureReport.STATUS_RECEIVED, InfrastructureReport.STATUS_UNDER_REVIEW])
    flagged_unusual_count = sum(1 for r in all_reports if r.get('status') == 'Flagged for Review' or r.get('metadata', {}).get('is_unusual') is True)
    verified_count = sum(1 for r in all_reports if InfrastructureReport.normalize_lifecycle_status(r.get('status')) in [InfrastructureReport.STATUS_VERIFIED, InfrastructureReport.STATUS_RESOLVED])

    # Relative visual severity distribution
    critical_count = sum(1 for a in all_assessments if a.get('relative_severity') in ['Critical', 'High'])
    moderate_count = sum(1 for a in all_assessments if a.get('relative_severity') in ['Moderate', 'Medium'])
    low_count = sum(1 for a in all_assessments if a.get('relative_severity') == 'Low')

    # Defect category counts (Crack, Pothole, Surface deterioration)
    crack_count = sum(1 for a in all_assessments if str(a.get('defect_class')).lower() == 'crack')
    pothole_count = sum(1 for a in all_assessments if str(a.get('defect_class')).lower() == 'pothole')
    surface_count = sum(1 for a in all_assessments if 'surface' in str(a.get('defect_class')).lower())

    from flask import current_app
    model_version = current_app.config.get('MODEL_VERSION', 'ssd_mobilenet_v2_lr00625_step8000_v2')

    resp = make_response(jsonify({
        'active_defect_queue': active_count,
        'flagged_unusual_count': flagged_unusual_count,
        'verified_inspections': verified_count,
        'total_submissions': len(all_reports),
        'model_architecture': 'Single Shot MultiBox Detector (SSD)',
        'model_backbone': 'MobileNetV2',
        'model_version': model_version,
        'severity_breakdown': {
            'Critical': critical_count,
            'Moderate': moderate_count,
            'Medium': moderate_count,
            'Low': low_count
        },
        'defect_class_breakdown': {
            'Crack': crack_count,
            'Pothole': pothole_count,
            'Surface deterioration': surface_count
        }
    }), 200)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@analytics_bp.route('/trends', methods=['GET'])
@role_required('engineer', 'admin')
def get_historical_defect_trends(current_user):
    """
    Database-driven Historical Defect Trends.
    Replaces static/artificial condition index with real infrastructure defect observations
    grouped over time by Defect Class or Visual Severity.
    """
    time_range = request.args.get('range', '6m').lower().strip()
    view_by = request.args.get('view_by', 'defect_class').lower().strip()
    county_filter = request.args.get('county', 'all').strip()
    ward_filter = request.args.get('ward', 'all').strip()

    if view_by not in ['defect_class', 'visual_severity']:
        view_by = 'defect_class'

    now = datetime.now(timezone.utc)
    all_reports = db_service.find('infrastructure_reports')
    all_assessments = {str(a.get('report_id') or a.get('_id')): a for a in db_service.find('ai_assessments')}

    # Pre-parse report dates
    parsed_reports = []
    for rep in all_reports:
        dt_str = rep.get('date_submitted') or rep.get('created_at')
        if not dt_str:
            continue
        try:
            # Handle ISO formats with or without timezone
            clean_str = dt_str.replace('Z', '+00:00')
            if '+' in clean_str[10:] or '-' in clean_str[10:]:
                # Timezone aware
                dt = datetime.fromisoformat(clean_str)
            else:
                dt = datetime.fromisoformat(clean_str).replace(tzinfo=timezone.utc)
        except Exception:
            try:
                dt = datetime.strptime(dt_str[:10], '%Y-%m-%d').replace(tzinfo=timezone.utc)
            except Exception:
                continue

        meta = rep.get('metadata') or {}
        loc_name = str(meta.get('location_name') or rep.get('location_name') or rep.get('description') or '')
        rep_county = str(meta.get('county') or rep.get('county') or '')

        # County filter
        if county_filter and county_filter.lower() != 'all':
            c_low = county_filter.lower()
            if c_low not in loc_name.lower() and c_low not in rep_county.lower():
                continue

        # Ward / sub-county filter
        if ward_filter and ward_filter.lower() != 'all' and ward_filter.lower() != 'all areas':
            if ward_filter.lower() not in loc_name.lower():
                continue

        parsed_reports.append((dt, rep, meta, loc_name))

    # Define time boundaries and chronological period buckets
    if time_range == '3m':
        # 12 weekly periods across past 90 days
        num_weeks = 12
        start_date = now - timedelta(days=num_weeks * 7)
        periods = []
        for w in range(num_weeks):
            w_start = start_date + timedelta(days=w * 7)
            w_end = w_start + timedelta(days=6)
            label = f"{w_start.strftime('%d %b')} - {w_end.strftime('%d %b')}"
            periods.append({
                'key': f"W{w}",
                'label': label,
                'start': w_start,
                'end': w_end + timedelta(days=1)
            })
    elif time_range == '12m':
        # 12 calendar months
        periods = []
        cur_year, cur_month = now.year, now.month
        for i in range(11, -1, -1):
            m = cur_month - i
            y = cur_year
            while m <= 0:
                m += 12
                y -= 1
            start_m = datetime(y, m, 1, tzinfo=timezone.utc)
            last_day = calendar.monthrange(y, m)[1]
            end_m = datetime(y, m, last_day, 23, 59, 59, tzinfo=timezone.utc)
            periods.append({
                'key': f"{y}-{m:02d}",
                'label': f"{calendar.month_abbr[m]} {y}",
                'start': start_m,
                'end': end_m
            })
    elif time_range == 'all':
        # From earliest report to current month
        earliest_year = now.year
        earliest_month = now.month
        for dt, _, _, _ in parsed_reports:
            if (dt.year, dt.month) < (earliest_year, earliest_month):
                earliest_year = dt.year
                earliest_month = dt.month
        
        # At least 6 months
        months_span = (now.year - earliest_year) * 12 + (now.month - earliest_month) + 1
        months_span = max(months_span, 6)
        periods = []
        for i in range(months_span - 1, -1, -1):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            start_m = datetime(y, m, 1, tzinfo=timezone.utc)
            last_day = calendar.monthrange(y, m)[1]
            end_m = datetime(y, m, last_day, 23, 59, 59, tzinfo=timezone.utc)
            periods.append({
                'key': f"{y}-{m:02d}",
                'label': f"{calendar.month_abbr[m]} {y}",
                'start': start_m,
                'end': end_m
            })
    else:
        # Default: 6 calendar months
        time_range = '6m'
        periods = []
        cur_year, cur_month = now.year, now.month
        for i in range(5, -1, -1):
            m = cur_month - i
            y = cur_year
            while m <= 0:
                m += 12
                y -= 1
            start_m = datetime(y, m, 1, tzinfo=timezone.utc)
            last_day = calendar.monthrange(y, m)[1]
            end_m = datetime(y, m, last_day, 23, 59, 59, tzinfo=timezone.utc)
            periods.append({
                'key': f"{y}-{m:02d}",
                'label': f"{calendar.month_abbr[m]} {y}",
                'start': start_m,
                'end': end_m
            })

    # Initialize trend buckets with zero counts (no artificial gaps or interpolation)
    if view_by == 'defect_class':
        series_keys = ['Crack', 'Pothole', 'Surface deterioration']
    else:
        series_keys = ['Critical', 'Medium', 'Low']

    trend_buckets = []
    for p in periods:
        b = {
            'period': p['label'],
            'total': 0
        }
        for k in series_keys:
            b[k] = 0
        trend_buckets.append((p, b))

    # Aggregate actual database reports
    total_in_period = 0
    defect_counts = defaultdict(int)
    critical_in_period = 0
    resolved_in_period = 0
    location_counts = defaultdict(int)

    earliest_bound = periods[0]['start']
    latest_bound = periods[-1]['end']

    for dt, rep, meta, loc_name in parsed_reports:
        if not (earliest_bound <= dt <= latest_bound):
            continue

        total_in_period += 1
        rep_status = rep.get('status', 'Received')
        if rep_status == 'Resolved':
            resolved_in_period += 1

        # Class determination
        raw_class = str(meta.get('defect_class') or rep.get('defect_class') or '').strip().lower()
        if 'pothole' in raw_class:
            defect_class = 'Pothole'
        elif 'crack' in raw_class:
            defect_class = 'Crack'
        elif 'surface' in raw_class:
            defect_class = 'Surface deterioration'
        else:
            defect_class = 'Pothole'  # standard canonical fallback

        defect_counts[defect_class] += 1

        # Severity determination
        raw_sev = str(meta.get('relative_severity') or rep.get('relative_severity') or '').strip().lower()
        if raw_sev in ['critical', 'high']:
            severity = 'Critical'
            critical_in_period += 1
        elif raw_sev in ['medium', 'moderate']:
            severity = 'Medium'
        else:
            severity = 'Low'

        if loc_name:
            location_counts[loc_name] += 1

        # Locate bucket
        for p_info, bucket in trend_buckets:
            if p_info['start'] <= dt <= p_info['end']:
                bucket['total'] += 1
                if view_by == 'defect_class':
                    bucket[defect_class] = bucket.get(defect_class, 0) + 1
                else:
                    bucket[severity] = bucket.get(severity, 0) + 1
                break

    trend_data = [b for _, b in trend_buckets]

    # Secondary summary computations
    most_reported_defect = max(defect_counts.items(), key=lambda x: x[1])[0] if defect_counts else 'None'
    most_active_loc = max(location_counts.items(), key=lambda x: x[1])[0] if location_counts else 'None'

    # Compute genuine data-based recurrence insights (Section 31)
    month_critical_counts = defaultdict(int)
    corridor_defect_map = defaultdict(lambda: defaultdict(int))
    for dt, rep, meta, loc_name in parsed_reports:
        if not (earliest_bound <= dt <= latest_bound):
            continue
        raw_sev = str(meta.get('relative_severity') or rep.get('relative_severity') or '').strip().lower()
        if raw_sev in ['critical', 'high']:
            m_label = f"{calendar.month_name[dt.month]} {dt.year}"
            month_critical_counts[m_label] += 1
        raw_class = str(meta.get('defect_class') or rep.get('defect_class') or '').strip().lower()
        d_class = 'Pothole' if 'pothole' in raw_class else ('Crack' if 'crack' in raw_class else 'Surface deterioration')
        if loc_name:
            corridor_defect_map[loc_name][d_class] += 1

    peak_crit_month = max(month_critical_counts.items(), key=lambda x: x[1]) if month_critical_counts else None
    top_corridor_recurrent = None
    if most_active_loc != 'None' and most_active_loc in corridor_defect_map:
        d_map = corridor_defect_map[most_active_loc]
        if d_map:
            top_corridor_recurrent = max(d_map.items(), key=lambda x: x[1])

    recurrence_insights = []
    if most_reported_defect != 'None':
        recurrence_insights.append({
            'title': 'Most Frequently Reported Defect',
            'value': f"{most_reported_defect} ({defect_counts[most_reported_defect]} observations)",
            'basis': 'Historical observation count in active period'
        })
    if most_active_loc != 'None':
        recurrence_insights.append({
            'title': 'Most Active Monitored Corridor',
            'value': f"{most_active_loc} ({location_counts[most_active_loc]} reports)",
            'basis': 'Corridor report concentration'
        })
    if peak_crit_month:
        recurrence_insights.append({
            'title': 'Month with Highest Critical Reports',
            'value': f"{peak_crit_month[0]} ({peak_crit_month[1]} critical reports)",
            'basis': 'Temporal critical density'
        })
    if top_corridor_recurrent:
        recurrence_insights.append({
            'title': f"Most Recurring Defect on {most_active_loc}",
            'value': f"{top_corridor_recurrent[0]} ({top_corridor_recurrent[1]} occurrences)",
            'basis': 'Corridor-level defect recurrence pattern'
        })

    # -------------------------------------------------------------------------
    # Sections 34, 35, 36: Dynamic Data-Driven Monitoring Insights
    # -------------------------------------------------------------------------
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)
    crit_30d = 0
    crit_prev_30d = 0
    asset_type_counts = defaultdict(int)
    corridor_total_counts = defaultdict(int)

    received_to_verified_durations = []
    verified_to_resolved_durations = []

    is_geo_filtered = (county_filter.lower() != 'all') or (ward_filter and ward_filter.lower() != 'all' and ward_filter.lower() != 'all areas')
    scoped_reports = [r for _, r, _, _ in parsed_reports] if is_geo_filtered else all_reports

    for rep in scoped_reports:
        meta = rep.get('metadata') or {}
        dt_str = rep.get('date_submitted') or rep.get('created_at')
        if not dt_str:
            continue
        try:
            clean_str = dt_str.replace('Z', '+00:00')
            if '+' in clean_str[10:] or '-' in clean_str[10:]:
                dt = datetime.fromisoformat(clean_str)
            else:
                dt = datetime.fromisoformat(clean_str).replace(tzinfo=timezone.utc)
        except Exception:
            continue

        raw_sev = str(meta.get('relative_severity') or rep.get('relative_severity') or '').strip().lower()
        if raw_sev in ['critical', 'high']:
            if thirty_days_ago <= dt <= now:
                crit_30d += 1
            elif sixty_days_ago <= dt < thirty_days_ago:
                crit_prev_30d += 1

        a_type = meta.get('asset_type') or rep.get('asset_type') or 'Road / Pavement'
        asset_type_counts[a_type] += 1

        c_loc = meta.get('location_name') or rep.get('location_name') or rep.get('description') or ''
        if c_loc:
            corridor_total_counts[c_loc] += 1

        hist = meta.get('status_history') or []
        rec_time = None
        ver_time = None
        res_time = None
        for h in hist:
            s = str(h.get('status')).lower()
            t_str = h.get('timestamp')
            if not t_str:
                continue
            try:
                clean_t = t_str.replace('Z', '+00:00')
                if '+' in clean_t[10:] or '-' in clean_t[10:]:
                    t_val = datetime.fromisoformat(clean_t)
                else:
                    t_val = datetime.fromisoformat(clean_t).replace(tzinfo=timezone.utc)
                if s == 'received' and not rec_time:
                    rec_time = t_val
                elif s == 'verified' and not ver_time:
                    ver_time = t_val
                elif s == 'resolved' and not res_time:
                    res_time = t_val
            except Exception:
                continue

        if rec_time and ver_time and ver_time >= rec_time:
            received_to_verified_durations.append((ver_time - rec_time).total_seconds())
        if ver_time and res_time and res_time >= ver_time:
            verified_to_resolved_durations.append((res_time - ver_time).total_seconds())

    avg_rec_to_ver_str = "Not enough historical data for this selection"
    if received_to_verified_durations:
        avg_hrs = sum(received_to_verified_durations) / (len(received_to_verified_durations) * 3600)
        avg_rec_to_ver_str = f"{round(avg_hrs / 24, 1)} days" if avg_hrs >= 48 else f"{round(avg_hrs, 1)} hours"

    avg_ver_to_res_str = "Not enough historical data for this selection"
    if verified_to_resolved_durations:
        avg_hrs = sum(verified_to_resolved_durations) / (len(verified_to_resolved_durations) * 3600)
        avg_ver_to_res_str = f"{round(avg_hrs / 24, 1)} days" if avg_hrs >= 48 else f"{round(avg_hrs, 1)} hours"

    crit_change_str = "No prior period comparison"
    if crit_prev_30d > 0:
        pct_change = round(((crit_30d - crit_prev_30d) / crit_prev_30d) * 100)
        prefix = "+" if pct_change > 0 else ""
        crit_change_str = f"{prefix}{pct_change}% vs previous 30 days"

    top_asset = max(asset_type_counts.items(), key=lambda x: x[1])[0] if asset_type_counts else "Road / Pavement"
    top_repeat_corridor = max(corridor_total_counts.items(), key=lambda x: x[1]) if corridor_total_counts else None

    # Weather Association Analysis & Pattern Intelligence (Sections 14-26, 36-38)
    weather_insight = weather_service.analyze_weather_associations(scoped_reports)
    pattern_intelligence = weather_service.analyze_pattern_intelligence(scoped_reports, county_filter, ward_filter)

    has_scoped_data = len(scoped_reports) >= 3
    monitoring_insights = {
        'has_sufficient_data': has_scoped_data,
        'message': None if has_scoped_data else 'Not enough historical data for this selection.',
        'critical_last_30d': crit_30d if has_scoped_data else 0,
        'critical_change': crit_change_str if has_scoped_data else 'No prior period comparison',
        'top_asset_type': top_asset if has_scoped_data else 'None',
        'top_corridor_repeat': f"{top_repeat_corridor[0]} ({top_repeat_corridor[1]} reports)" if (has_scoped_data and top_repeat_corridor) else "Not enough historical data for this selection",
        'avg_received_to_verified': avg_rec_to_ver_str if has_scoped_data else "Not enough historical data for this selection",
        'avg_verified_to_resolved': avg_ver_to_res_str if has_scoped_data else "Not enough historical data for this selection",
        'weather_insight': weather_insight,
        'pattern_intelligence': pattern_intelligence
    }

    has_data = total_in_period > 0
    geo_label = county_filter if county_filter != 'all' else 'this selection'

    resp_data = {
        'trend_data': trend_data,
        'time_range': time_range,
        'view_by': view_by,
        'series': series_keys,
        'has_sufficient_data': has_data,
        'message': None if has_data else f'No defect reports recorded for {geo_label} in the selected period.',
        'summary': {
            'most_reported_defect': most_reported_defect if has_data else 'None',
            'critical_reports_count': critical_in_period,
            'resolved_reports_count': resolved_in_period,
            'most_active_location': most_active_loc if has_data else 'None',
            'total_reports': total_in_period,
            'recurrence_insights': recurrence_insights
        },
        'monitoring_insights': monitoring_insights,
        'filter_options': {
            'counties': ['All Counties'] + KENYA_47_COUNTIES,
            'wards': [
                'All Areas',
                'CBD',
                'Westlands',
                'Kileleshwa',
                'Lavington',
                'Kilimani',
                'Langata',
                'Upper Hill',
                'Industrial Area',
                'South B',
                'Ngong Road'
            ]
        }
    }

    resp = make_response(jsonify(resp_data), 200)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@analytics_bp.route('/critical-calendar', methods=['GET'])
@role_required('engineer', 'admin')
def get_critical_calendar(current_user):
    """
    Critical Reports Calendar (Sections 28 & 29, 40 & 41).
    Calculates concentration of Critical infrastructure reports over actual dates.
    Grounded strictly in verified database observations; no fabricated dates or counts.
    Explicitly represents: Critical Reports Calendar = Critical reports received over time.
    """
    time_range = request.args.get('range', '6m').lower().strip()
    county_filter = request.args.get('county', 'all').strip()
    ward_filter = request.args.get('ward', 'all').strip()

    now = datetime.now(timezone.utc)
    all_reports = db_service.find('infrastructure_reports')

    if time_range == '3m':
        days_span = 90
    elif time_range == '12m':
        days_span = 365
    else:
        time_range = '6m'
        days_span = 180

    start_date = (now - timedelta(days=days_span)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    daily_critical = defaultdict(int)
    daily_report_ids = defaultdict(list)
    daily_defects = defaultdict(lambda: defaultdict(int))
    daily_corridors = defaultdict(lambda: defaultdict(int))
    total_critical = 0

    for rep in all_reports:
        meta = rep.get('metadata') or {}
        raw_sev = str(meta.get('relative_severity') or rep.get('relative_severity') or '').strip().lower()
        if raw_sev not in ['critical', 'high']:
            continue

        loc_name = str(meta.get('location_name') or rep.get('location_name') or rep.get('description') or '')
        rep_county = str(meta.get('county') or rep.get('county') or '')
        if county_filter and county_filter.lower() != 'all':
            c_low = county_filter.lower()
            if c_low not in loc_name.lower() and c_low not in rep_county.lower():
                continue
        if ward_filter and ward_filter.lower() != 'all' and ward_filter.lower() != 'all areas' and ward_filter.lower() not in loc_name.lower():
            continue

        dt_str = rep.get('date_submitted') or rep.get('created_at')
        if not dt_str:
            continue
        try:
            clean_str = dt_str.replace('Z', '+00:00')
            if '+' in clean_str[10:] or '-' in clean_str[10:]:
                dt = datetime.fromisoformat(clean_str)
            else:
                dt = datetime.fromisoformat(clean_str).replace(tzinfo=timezone.utc)
        except Exception:
            try:
                dt = datetime.strptime(dt_str[:10], '%Y-%m-%d').replace(tzinfo=timezone.utc)
            except Exception:
                continue

        if start_date <= dt <= end_date:
            day_key = dt.strftime('%Y-%m-%d')
            daily_critical[day_key] += 1
            disp_id = rep.get('display_id') or (f"#REP-{rep.get('report_id')[-6:].upper()}" if rep.get('report_id') else f"#REP-{str(rep.get('_id'))[-6:].upper()}")
            daily_report_ids[day_key].append(disp_id)
            d_class = meta.get('defect_class') or rep.get('defect_class') or 'Defect'
            daily_defects[day_key][d_class] += 1
            if loc_name:
                daily_corridors[day_key][loc_name] += 1
            total_critical += 1

    ref_coords = None
    if county_filter and county_filter.lower() != 'all':
        for rep in all_reports:
            meta = rep.get('metadata') or {}
            c_low = county_filter.lower()
            loc_n = str(meta.get('location_name') or rep.get('location_name') or '').lower()
            rep_c = str(meta.get('county') or rep.get('county') or '').lower()
            if c_low in loc_n or c_low in rep_c:
                lat = rep.get('latitude') or meta.get('latitude')
                lng = rep.get('longitude') or meta.get('longitude')
                if lat and lng:
                    try:
                        ref_coords = (float(lat), float(lng))
                        break
                    except (ValueError, TypeError):
                        pass

    # Build continuous day records for calendar grid
    days = []
    cur = start_date
    max_count = 0
    while cur <= end_date:
        d_key = cur.strftime('%Y-%m-%d')
        cnt = daily_critical.get(d_key, 0)
        if cnt > max_count:
            max_count = cnt

        if cnt == 0:
            intensity = 0
        elif cnt == 1:
            intensity = 1
        elif cnt == 2:
            intensity = 2
        else:
            intensity = 3

        defect_breakdown = dict(daily_defects.get(d_key, {}))
        corridor_counts = daily_corridors.get(d_key, {})
        top_corridor = max(corridor_counts.items(), key=lambda x: x[1])[0] if corridor_counts else ''

        rainfall_7d = None
        if cnt > 0 and ref_coords:
            try:
                win = weather_service.get_report_rainfall_windows(ref_coords[0], ref_coords[1], cur)
                if win:
                    rainfall_7d = win.get('precip_7d')
            except Exception:
                rainfall_7d = None

        days.append({
            'date': d_key,
            'day_of_week': cur.weekday(),
            'count': cnt,
            'intensity': intensity,
            'reports': daily_report_ids.get(d_key, []),
            'defect_breakdown': defect_breakdown,
            'top_corridor': top_corridor,
            'rainfall_7d': rainfall_7d
        })
        cur += timedelta(days=1)

    # Build month-centric carousel groupings (Sections 6-12)
    months_map = {}
    for d in days:
        m_key = d['date'][:7]
        if m_key not in months_map:
            y, m_num = int(m_key[:4]), int(m_key[5:7])
            months_map[m_key] = {
                'key': m_key,
                'label': f"{calendar.month_name[m_num]} {y}",
                'year': y,
                'month': m_num,
                'days': [],
                'total_critical': 0,
                'defect_counts': defaultdict(int),
                'corridor_counts': defaultdict(int),
                'resolved_during_month': 0
            }
        m_obj = months_map[m_key]
        m_obj['days'].append(d)
        m_obj['total_critical'] += d['count']
        for c_name, c_cnt in d.get('defect_breakdown', {}).items():
            m_obj['defect_counts'][c_name] += c_cnt
        if d.get('top_corridor'):
            m_obj['corridor_counts'][d['top_corridor']] += d['count']

    # Attribute resolved reports during each month for this geographic scope
    for rep in all_reports:
        r_status = rep.get('status')
        if r_status == 'Resolved':
            meta = rep.get('metadata') or {}
            loc_n = str(meta.get('location_name') or rep.get('location_name') or rep.get('description') or '')
            rep_c = str(meta.get('county') or rep.get('county') or '')
            if county_filter and county_filter.lower() != 'all':
                c_low = county_filter.lower()
                if c_low not in loc_n.lower() and c_low not in rep_c.lower():
                    continue
            if ward_filter and ward_filter.lower() != 'all' and ward_filter.lower() != 'all areas' and ward_filter.lower() not in loc_n.lower():
                continue
            r_dt_str = rep.get('resolved_at') or rep.get('last_updated_at') or rep.get('date_submitted')
            if r_dt_str and len(r_dt_str) >= 7:
                r_m_key = r_dt_str[:7]
                if r_m_key in months_map:
                    months_map[r_m_key]['resolved_during_month'] += 1

    months_list = []
    for m_key in sorted(months_map.keys()):
        m_data = months_map[m_key]
        top_def = max(m_data['defect_counts'].items(), key=lambda x: x[1])[0] if m_data['defect_counts'] else 'None'
        top_corr = max(m_data['corridor_counts'].items(), key=lambda x: x[1])[0] if m_data['corridor_counts'] else 'None'
        months_list.append({
            'key': m_key,
            'label': m_data['label'],
            'year': m_data['year'],
            'month': m_data['month'],
            'days': m_data['days'],
            'total_critical': m_data['total_critical'],
            'most_reported_defect': top_def,
            'most_active_corridor': top_corr,
            'resolved_during_month': m_data['resolved_during_month']
        })

    resp = make_response(jsonify({
        'time_range': time_range,
        'total_critical_reports': total_critical,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'days': days,
        'months': months_list,
        'max_daily_count': max_count,
        'note': 'Critical Reports Calendar = Critical reports received over time (temporal concentration)'
    }), 200)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


