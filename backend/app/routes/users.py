from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash
from ..models.user import User
from ..services.database import db_service
from ..utils.auth_helpers import login_required

users_bp = Blueprint('users', __name__, url_prefix='/api/users')

@users_bp.route('/profile', methods=['GET'])
@login_required
def get_profile(current_user):
    """Retrieves current authenticated user's profile details."""
    return jsonify({'user': User.from_dict(current_user).to_dict()}), 200

@users_bp.route('/profile', methods=['PUT'])
@login_required
def update_profile(current_user):
    """Updates user personal details (name or password)."""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    new_password = data.get('new_password', '').strip()

    updates = {}
    if name:
        updates['name'] = name
    if new_password:
        if len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters.'}), 400
        updates['password_hash'] = generate_password_hash(new_password)

    if updates:
        db_service.update_one('users', {'_id': current_user['_id']}, updates)

    updated_user = db_service.find_one('users', {'_id': current_user['_id']})
    return jsonify({
        'message': 'Profile updated successfully.',
        'user': User.from_dict(updated_user).to_dict()
    }), 200

@users_bp.route('/reports', methods=['GET'])
@login_required
def get_user_reports(current_user):
    """FR-08: Citizen Tracking Module - retrieves all defect reports submitted by the active user."""
    user_id = str(current_user.get('_id') or current_user.get('user_id'))
    reports = db_service.find('infrastructure_reports', {'user_id': user_id}, sort_key='date_submitted', reverse=True)
    
    results = []
    for rep in reports:
        image = db_service.find_one('submitted_images', {'report_id': rep['_id']})
        assessment = db_service.find_one('ai_assessments', {'image_id': image['_id']}) if image else None
        results.append({
            'report': rep,
            'image_url': f"/api/reports/images/{image['image_path']}" if image else None,
            'assessment': assessment
        })

    return jsonify({'reports': results, 'count': len(results)}), 200
