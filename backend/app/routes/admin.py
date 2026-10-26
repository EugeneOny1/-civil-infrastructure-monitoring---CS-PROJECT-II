from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from ..models.user import User
from ..services.database import db_service
from ..utils.auth_helpers import role_required

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

@admin_bp.route('/users', methods=['GET'])
@role_required('admin')
def list_users(current_user):
    """
    FR-10: System Administrator user management.
    Lists registered users with optional role and verification status filters.
    """
    role_filter = request.args.get('role')
    status_filter = request.args.get('verification_status')
    
    query = {}
    if role_filter:
        query['role'] = role_filter
    if status_filter:
        query['verification_status'] = status_filter

    users = db_service.find('users', query)
    sanitized = [User.from_dict(u).to_dict() for u in users]
    return jsonify({'users': sanitized, 'count': len(sanitized)}), 200

@admin_bp.route('/users/<user_id>/verify', methods=['PUT'])
@role_required('admin')
def verify_professional_user(current_user, user_id):
    """
    FR-10: Administrator verification of professional engineer or inspector accounts.
    Verification statuses: 'verified', 'rejected', 'pending'.
    """
    data = request.get_json() or {}
    new_status = data.get('status', 'verified')
    if new_status not in ['verified', 'rejected', 'pending']:
        return jsonify({'error': 'Invalid verification status. Permitted: verified, rejected, pending.'}), 400

    target = db_service.find_one('users', {'_id': user_id})
    if not target:
        return jsonify({'error': 'User not found.'}), 404

    db_service.update_one('users', {'_id': user_id}, {'verification_status': new_status})

    return jsonify({
        'message': f"Professional account verification status updated to '{new_status}'.",
        'user_id': user_id,
        'verification_status': new_status
    }), 200

@admin_bp.route('/stats', methods=['GET'])
@role_required('admin')
def get_system_stats(current_user):
    """Provides system-level oversight statistics for administrator."""
    all_users = db_service.find('users')
    all_reports = db_service.find('infrastructure_reports')
    all_reviews = db_service.find('professional_reviews')

    pending_engineers = sum(1 for u in all_users if u.get('role') == 'engineer' and u.get('verification_status') == 'pending')
    verified_engineers = sum(1 for u in all_users if u.get('role') == 'engineer' and u.get('verification_status') == 'verified')
    total_citizens = sum(1 for u in all_users if u.get('role') == 'citizen')
    active_users = sum(1 for u in all_users if u.get('is_active', True) and u.get('verification_status', 'verified') == 'verified')

    return jsonify({
        'total_users': len(all_users),
        'citizens_count': total_citizens,
        'pending_engineer_verifications': pending_engineers,
        'verified_engineers_count': verified_engineers,
        'active_users_count': active_users,
        'total_defect_reports': len(all_reports),
        'total_professional_reviews': len(all_reviews)
    }), 200

@admin_bp.route('/dashboard', methods=['GET'])
@role_required('admin')
def get_admin_dashboard(current_user):
    """
    Cohesive Admin Dashboard providing high-level governance and system oversight:
    - User distribution (citizens, engineers, admins) & active status
    - Pending professional Engineer verification queue with direct actions
    - Report activity (total, open, verified, resolved) & resolution rate
    - Governance analytics (location hotspot distribution, asset types, defect trends)
    - Operational health indicators (API, MongoDB, AI SavedModel, Email/OTP, Google Auth, Google Maps)
    """
    from flask import current_app
    from ..services.inference import inference_service
    from ..services.email_service import email_service
    from ..models.report import InfrastructureReport

    all_users = db_service.find('users')
    all_reports = db_service.find('infrastructure_reports')
    all_reviews = db_service.find('professional_reviews')

    # 1. Users Summary
    total_users = len(all_users)
    citizens_count = sum(1 for u in all_users if u.get('role') == 'citizen')
    engineers_count = sum(1 for u in all_users if u.get('role') == 'engineer')
    admins_count = sum(1 for u in all_users if u.get('role') == 'admin')
    active_users = sum(1 for u in all_users if u.get('verification_status') != 'rejected')

    pending_engineer_list = []
    for u in all_users:
        if u.get('role') == 'engineer' and u.get('verification_status') == 'pending':
            pending_engineer_list.append({
                'user_id': str(u.get('_id')),
                'name': u.get('name', 'Unknown'),
                'email': u.get('email', ''),
                'engineering_category': u.get('engineering_category', 'Graduate Engineer'),
                'professional_reg_no': u.get('professional_reg_no', 'N/A'),
                'organization': u.get('organization', 'Independent'),
                'created_at': u.get('created_at', '')
            })

    users_summary = {
        'total': total_users,
        'citizens': citizens_count,
        'engineers': engineers_count,
        'admins': admins_count,
        'active': active_users,
        'pending_verifications_count': len(pending_engineer_list),
        'pending_engineers': pending_engineer_list
    }

    # 2. Report Activity & Canonical Lifecycle Counts
    total_reports = len(all_reports)
    received_count = 0
    under_review_count = 0
    verified_count = 0
    resolved_count = 0

    reports_by_location = {}
    reports_by_asset_type = {}
    reports_by_defect = {}
    resolution_times_hours = []

    for r in all_reports:
        # Canonical status mapping
        raw_status = r.get('status', 'Received')
        canonical_status = InfrastructureReport.canonical_status(raw_status)

        if canonical_status == InfrastructureReport.STATUS_RECEIVED:
            received_count += 1
        elif canonical_status == InfrastructureReport.STATUS_UNDER_REVIEW:
            under_review_count += 1
        elif canonical_status == InfrastructureReport.STATUS_VERIFIED:
            verified_count += 1
        elif canonical_status == InfrastructureReport.STATUS_RESOLVED:
            resolved_count += 1

        # Location aggregations
        meta = r.get('metadata') or {}
        loc_name = meta.get('location_name') or r.get('location') or 'Unspecified Location'
        area_key = loc_name.split('(')[0].split(',')[0].strip()
        if area_key not in reports_by_location:
            reports_by_location[area_key] = {'corridor': area_key, 'total_defects': 0, 'critical_count': 0}
        reports_by_location[area_key]['total_defects'] += 1
        if (meta.get('relative_severity') or '').lower() == 'critical':
            reports_by_location[area_key]['critical_count'] += 1

        # Asset type breakdown
        asset_type = meta.get('asset_type') or 'Road / Pavement'
        reports_by_asset_type[asset_type] = reports_by_asset_type.get(asset_type, 0) + 1

        # Defect class breakdown
        d_class = meta.get('defect_class') or 'Crack'
        reports_by_defect[d_class] = reports_by_defect.get(d_class, 0) + 1

        # Resolution time calculation if status is resolved and status_history is present
        if canonical_status == InfrastructureReport.STATUS_RESOLVED:
            history = meta.get('status_history', [])
            if history and len(history) >= 2:
                try:
                    t_start = datetime.fromisoformat(history[0]['timestamp'])
                    t_end = datetime.fromisoformat(history[-1]['timestamp'])
                    diff_h = (t_end - t_start).total_seconds() / 3600.0
                    if diff_h >= 0:
                        resolution_times_hours.append(diff_h)
                except Exception:
                    pass

    open_reports = received_count + under_review_count
    resolution_rate = round((resolved_count / total_reports * 100), 1) if total_reports > 0 else 0.0
    avg_resolution_h = round(sum(resolution_times_hours) / len(resolution_times_hours), 1) if resolution_times_hours else 24.0

    reports_summary = {
        'total': total_reports,
        'received': received_count,
        'under_review': under_review_count,
        'verified': verified_count,
        'resolved': resolved_count,
        'open_reports': open_reports,
        'resolution_rate_percent': resolution_rate,
        'avg_resolution_hours': avg_resolution_h
    }

    # 3. Governance Analytics
    sorted_corridors = sorted(reports_by_location.values(), key=lambda x: x['total_defects'], reverse=True)[:6]

    # Engineer workload distribution
    workload_map = {}
    for rev in all_reviews:
        r_id = rev.get('reviewer_id', 'Unknown')
        workload_map[r_id] = workload_map.get(r_id, 0) + 1

    # Enrich reviewer names
    user_lookup = {str(u.get('_id')): u for u in all_users}
    engineer_workload = []
    for uid, count in workload_map.items():
        u = user_lookup.get(uid)
        engineer_workload.append({
            'name': u.get('name', f"Engineer {uid[:6]}") if u else f"Engineer {uid[:6]}",
            'organization': u.get('organization', 'KeNHA / Certified Inspector') if u else 'Independent Inspector',
            'inspections_completed': count
        })
    if not engineer_workload:
        for u in all_users:
            if u.get('role') == 'engineer' and u.get('verification_status') == 'verified':
                engineer_workload.append({
                    'name': u.get('name', 'Certified Engineer'),
                    'organization': u.get('organization', 'KeNHA / Certified Inspector'),
                    'inspections_completed': 0
                })

    governance_analytics = {
        'top_locations': sorted_corridors,
        'reports_by_asset_type': reports_by_asset_type,
        'reports_by_defect': reports_by_defect,
        'engineer_workload': engineer_workload
    }

    # 4. System Health Indicators
    google_client_id = current_app.config.get('GOOGLE_CLIENT_ID', '').strip()
    google_configured = bool(google_client_id and (google_client_id.endswith('.apps.googleusercontent.com') or len(google_client_id) > 15))
    google_live = db_service.find_one('system_state', {'_id': 'google_identity_status'})
    google_operational = bool(google_configured and google_live and google_live.get('operational') is True)

    smtp_configured = email_service.is_configured()
    smtp_healthy = False
    smtp_status_desc = "Demo Fallback"
    if smtp_configured:
        smtp_healthy, smtp_status_desc = email_service.verify_smtp_health()

    system_health = {
        'backend_api': {
            'status': 'online',
            'version': '2.0.0',
            'framework': 'Flask 3.1 / Python 3.13'
        },
        'database': {
            'status': 'connected' if not db_service.use_mock else 'mock_fallback',
            'engine': 'MongoDB' if not db_service.use_mock else 'In-Memory Mock Store',
            'database_name': db_service.db_name
        },
        'mongodb': {
            'status': 'connected' if not db_service.use_mock else 'mock_fallback',
            'engine': 'MongoDB' if not db_service.use_mock else 'In-Memory Mock Store',
            'database_name': db_service.db_name
        },
        'ai_model': {
            'status': 'loaded' if getattr(inference_service, 'is_loaded', False) else 'offline',
            'model_name': inference_service.DEFAULT_MODEL_NAME,
            'version': inference_service.DEFAULT_MODEL_VERSION,
            'detections_supported': ['Crack', 'Pothole', 'Surface deterioration']
        },
        'email_service': {
            'configured': smtp_healthy,
            'status': 'operational' if smtp_healthy else 'demo_mode',
            'provider': 'Gmail / SMTP Server' if smtp_healthy else 'Local Cryptographic Generator'
        },
        'email_otp': {
            'status': 'operational' if smtp_healthy else 'demo_mode',
            'configured': smtp_healthy,
            'provider': 'Gmail / SMTP Server' if smtp_healthy else 'Local Cryptographic Generator (Demo Fallback)',
            'status_desc': smtp_status_desc,
            'demo_mode_enabled': current_app.config.get('ENABLE_DEMO_OTP', True),
            'expiry_seconds': current_app.config.get('OTP_EXPIRY_SECONDS', 300),
            'cooldown_seconds': current_app.config.get('OTP_RESEND_COOLDOWN_SECONDS', 60)
        },
        'google_auth': {
            'configured': google_configured,
            'status': 'operational' if google_operational else ('configured' if google_configured else 'pending_client_id'),
            'provider': 'Google Identity Services (GIS)'
        },
        'gis_mapping': {
            'configured': True,
            'status': 'operational',
            'provider': 'Leaflet + OpenStreetMap',
            'default_center': 'Nairobi (-1.286389, 36.817223)'
        },
        'google_maps': {  # Compatibility alias
            'configured': True,
            'status': 'operational',
            'provider': 'Leaflet + OpenStreetMap'
        }
    }

    overview = {
        'total_users': total_users,
        'citizens_count': citizens_count,
        'engineers_count': engineers_count,
        'admins_count': admins_count,
        'verified_engineers_count': sum(1 for u in all_users if u.get('role') == 'engineer' and u.get('verification_status') == 'verified'),
        'pending_engineers_count': len(pending_engineer_list)
    }

    reports = {
        'total_reports': total_reports,
        'open_reports': open_reports,
        'resolution_rate_percent': resolution_rate,
        'received': received_count,
        'under_review': under_review_count,
        'verified': verified_count,
        'resolved': resolved_count
    }

    return jsonify({
        'overview': overview,
        'reports': reports,
        'reports_by_location': sorted_corridors,
        'engineer_workload': engineer_workload,
        'users_summary': users_summary,
        'reports_summary': reports_summary,
        'governance_analytics': governance_analytics,
        'system_health': system_health
    }), 200
