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

    return jsonify({
        'total_users': len(all_users),
        'citizens_count': total_citizens,
        'pending_engineer_verifications': pending_engineers,
        'verified_engineers_count': verified_engineers,
        'total_defect_reports': len(all_reports),
        'total_professional_reviews': len(all_reviews)
    }), 200
