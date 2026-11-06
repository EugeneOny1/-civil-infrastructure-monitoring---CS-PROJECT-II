from datetime import datetime, timezone, timedelta
import calendar
from collections import defaultdict
from flask import Blueprint, jsonify, request, make_response
from ..services.database import db_service
from ..utils.auth_helpers import role_required

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

        # County filter
        if county_filter and county_filter.lower() != 'all':
            if county_filter.lower() not in loc_name.lower():
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

    has_data = total_in_period > 0

    resp_data = {
        'trend_data': trend_data,
        'time_range': time_range,
        'view_by': view_by,
        'series': series_keys,
        'has_sufficient_data': has_data,
        'message': None if has_data else 'Not enough historical report data is available for this period.',
        'summary': {
            'most_reported_defect': most_reported_defect,
            'critical_reports_count': critical_in_period,
            'resolved_reports_count': resolved_in_period,
            'most_active_location': most_active_loc,
            'total_reports': total_in_period,
            'recurrence_insights': recurrence_insights
        },
        'filter_options': {
            'counties': ['All Counties', 'Nairobi', 'Mombasa', 'Kisumu', 'Nakuru', 'Kiambu', 'Machakos', 'Uasin Gishu'],
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
    Critical Reports Calendar (Sections 28 & 29).
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
    total_critical = 0

    for rep in all_reports:
        meta = rep.get('metadata') or {}
        raw_sev = str(meta.get('relative_severity') or rep.get('relative_severity') or '').strip().lower()
        if raw_sev not in ['critical', 'high']:
            continue

        loc_name = str(meta.get('location_name') or rep.get('location_name') or rep.get('description') or '')
        if county_filter and county_filter.lower() != 'all' and county_filter.lower() not in loc_name.lower():
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
            total_critical += 1

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

        days.append({
            'date': d_key,
            'day_of_week': cur.weekday(),
            'count': cnt,
            'intensity': intensity,
            'reports': daily_report_ids.get(d_key, [])
        })
        cur += timedelta(days=1)

    resp = make_response(jsonify({
        'time_range': time_range,
        'total_critical_reports': total_critical,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'days': days,
        'max_daily_count': max_count,
        'note': 'Critical Reports Calendar = Critical reports received over time (temporal concentration)'
    }), 200)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


