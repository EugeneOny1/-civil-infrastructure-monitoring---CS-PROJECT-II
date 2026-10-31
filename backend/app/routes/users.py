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

from ..models.report import InfrastructureReport

@users_bp.route('/reports', methods=['GET'])
@login_required
def get_user_reports(current_user):
    """FR-08: Citizen Tracking Module - retrieves all defect reports submitted by the active user."""
    user_id = str(current_user.get('_id') or current_user.get('user_id'))
    reports = db_service.find('infrastructure_reports', {'user_id': user_id}, sort_key='date_submitted', reverse=True)
    
    results = []
    for rep in reports:
        raw_status = rep.get('status', 'Received')
        canonical_status = InfrastructureReport.normalize_lifecycle_status(raw_status)
        is_unusual = (
            str(raw_status).lower() in ('flagged for review', 'flagged') or
            rep.get('metadata', {}).get('is_unusual') is True or
            rep.get('validation_status') == 'unusual'
        )
        rep['status'] = canonical_status
        if 'metadata' not in rep or not rep['metadata']:
            rep['metadata'] = {}
        rep['metadata']['is_unusual'] = is_unusual

        image = db_service.find_one('submitted_images', {'report_id': rep['_id']})
        assessment = db_service.find_one('ai_assessments', {'image_id': image['_id']}) if image else None
        review = db_service.find_one('professional_reviews', {'assessment_id': assessment['_id']}) if assessment else None
        results.append({
            'report': rep,
            'image_url': f"/api/reports/images/{image['image_path']}" if image else None,
            'assessment': assessment,
            'review': review
        })

    return jsonify({'reports': results, 'count': len(results)}), 200

from ..services.notification_service import notification_service

@users_bp.route('/notifications', methods=['GET'])
@login_required
def get_notifications(current_user):
    """Retrieves notifications for the active authenticated user."""
    user_id = str(current_user.get('_id') or current_user.get('user_id'))
    notifs = notification_service.get_user_notifications(user_id)
    unread_count = sum(1 for n in notifs if not n.get('is_read'))
    return jsonify({
        'notifications': notifs,
        'unread_count': unread_count,
        'count': len(notifs)
    }), 200

@users_bp.route('/notifications/<notification_id>/read', methods=['PATCH', 'POST'])
@login_required
def mark_notification_read(current_user, notification_id):
    """Marks a single citizen notification as read."""
    user_id = str(current_user.get('_id') or current_user.get('user_id'))
    success = notification_service.mark_as_read(user_id, notification_id)
    if success:
        return jsonify({'message': 'Notification marked as read.', 'notification_id': notification_id}), 200
    return jsonify({'error': 'Notification not found or access denied.'}), 404

@users_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read(current_user):
    """Marks all unread notifications for the user as read."""
    user_id = str(current_user.get('_id') or current_user.get('user_id'))
    count = notification_service.mark_all_as_read(user_id)
    return jsonify({'message': 'All notifications marked as read.', 'marked_count': count}), 200
