from flask import Blueprint, jsonify
from ..services.database import db_service
from ..utils.auth_helpers import role_required

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

@analytics_bp.route('/summary', methods=['GET'])
@role_required('engineer', 'admin')
def get_summary(current_user):
    """
    FR-07: Summary metrics for the Engineer Monitoring Dashboard (Figure 4.7).
    """
    all_reports = db_service.find('infrastructure_reports')
    all_assessments = db_service.find('ai_assessments')

    pending_count = sum(1 for r in all_reports if r.get('status') == 'Pending')
    verified_count = sum(1 for r in all_reports if r.get('status') in ['Verified', 'Resolved'])

    # Relative visual severity distribution
    critical_count = sum(1 for a in all_assessments if a.get('relative_severity') == 'Critical')
    medium_count = sum(1 for a in all_assessments if a.get('relative_severity') == 'Medium')
    low_count = sum(1 for a in all_assessments if a.get('relative_severity') == 'Low')

    # Defect category counts (Crack, Pothole, Surface Deterioration)
    crack_count = sum(1 for a in all_assessments if a.get('defect_class') == 'Crack')
    pothole_count = sum(1 for a in all_assessments if a.get('defect_class') == 'Pothole')
    surface_count = sum(1 for a in all_assessments if a.get('defect_class') == 'Surface Deterioration')

    return jsonify({
        'active_defect_queue': pending_count,
        'verified_inspections': verified_count,
        'total_submissions': len(all_reports),
        'model_architecture': 'Single Shot MultiBox Detector (SSD)',
        'model_backbone': 'MobileNetV2',
        'model_version': 'SSD-MobileNetV2-v1.0',
        'severity_breakdown': {
            'Critical': critical_count,
            'Medium': medium_count,
            'Low': low_count
        },
        'defect_class_breakdown': {
            'Crack': crack_count,
            'Pothole': pothole_count,
            'Surface Deterioration': surface_count
        }
    }), 200

@analytics_bp.route('/trends', methods=['GET'])
@role_required('engineer', 'admin')
def get_degradation_trends(current_user):
    """
    FR-09 & Figure 4.7: Historical Structural Condition Trends.
    Returns condition tracking points across inspection periods.
    """
    trends = [
        {'period': 'May', 'condition_score': 92, 'action_threshold': 68, 'defects_logged': 4},
        {'period': 'Jun', 'condition_score': 89, 'action_threshold': 68, 'defects_logged': 7},
        {'period': 'Jul', 'condition_score': 82, 'action_threshold': 68, 'defects_logged': 11},
        {'period': 'Aug', 'condition_score': 77, 'action_threshold': 68, 'defects_logged': 14},
        {'period': 'Sep', 'condition_score': 70, 'action_threshold': 68, 'defects_logged': 18},
        {'period': 'Oct', 'condition_score': 64, 'action_threshold': 68, 'defects_logged': 22}
    ]
    return jsonify({
        'trend_data': trends,
        'action_threshold': 68,
        'current_condition_rating': 'Prioritized for Maintenance Review'
    }), 200
