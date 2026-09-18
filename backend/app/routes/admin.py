from flask import Blueprint, request, jsonify
from ..models.user import User
from ..services.db import db_service
from ..utils.auth_helpers import role_required

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

@admin_bp.route('/users', methods=['GET'])
def list_users():
    """FR-10: Lists system users and filters pending engineer verification requests."""
    role_filter = request.args.get('role')
    query = {}
    if role_filter:
        query['role'] = role_filter

    users = db_service.find('users', query)
    sanitized = [User.from_dict(u).to_dict() for u in users]
    return jsonify({'users': sanitized, 'count': len(sanitized)})

@admin_bp.route('/users/<user_id>/verify', methods=['PUT'])
def verify_professional_user(user_id):
    """
    FR-10: Administrator verification of professional engineer or inspector accounts.
    Status can be 'verified' or 'rejected'.
    """
    data = request.get_json() or {}
    new_status = data.get('status', 'verified')
    if new_status not in ['verified', 'rejected', 'pending']:
        return jsonify({'error': 'Invalid verification status.'}), 400

    target = db_service.find_one('users', {'_id': user_id})
    if not target:
        return jsonify({'error': 'User not found.'}), 404

    db_service.update_one('users', {'_id': user_id}, {'verification_status': new_status})

    return jsonify({
        'message': f"User verification status updated to '{new_status}'.",
        'user_id': user_id,
        'verification_status': new_status
    })
