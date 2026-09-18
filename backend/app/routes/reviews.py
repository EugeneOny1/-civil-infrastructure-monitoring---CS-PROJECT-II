from datetime import datetime
from flask import Blueprint, request, jsonify
from ..models.review import ProfessionalReview
from ..models.report import InfrastructureReport
from ..services.db import db_service
from ..utils.auth_helpers import get_current_user

reviews_bp = Blueprint('reviews', __name__, url_prefix='/api/reviews')

@reviews_bp.route('/<assessment_id>', methods=['POST'])
def submit_review(assessment_id):
    """
    FR-06: Professional Review Sign-Off (Wireframe Figure 4.8).
    Allows licensed civil engineers to confirm or override AI detection and severity.
    """
    data = request.get_json() or {}
    decision = data.get('decision', ProfessionalReview.DECISION_CONFIRMED)
    comments = data.get('comments', '').strip()
    override_details = data.get('override_details', {})
    
    user = get_current_user()
    reviewer_id = user.get('_id') if user else 'usr_eng_01'

    # Verify assessment exists
    assessment = db_service.find_one('ai_assessments', {'_id': assessment_id})
    if not assessment:
        return jsonify({'error': 'AIAssessment record not found.'}), 404

    # Create or update ProfessionalReview
    existing_review = db_service.find_one('professional_reviews', {'assessment_id': assessment_id})
    if existing_review:
        db_service.update_one('professional_reviews', {'_id': existing_review['_id']}, {
            'decision': decision,
            'comments': comments,
            'override_details': override_details,
            'reviewer_id': reviewer_id,
            'review_date': datetime.utcnow().isoformat()
        })
        review_id = existing_review['_id']
    else:
        review = ProfessionalReview(
            assessment_id=assessment_id,
            reviewer_id=reviewer_id,
            decision=decision,
            comments=comments or 'Concur with automated AI defect assessment.',
            override_details=override_details
        )
        review_id = db_service.insert('professional_reviews', review.to_dict())

    # Find associated image and report
    image = db_service.find_one('submitted_images', {'_id': assessment.get('image_id')})
    if image:
        report_id = image.get('report_id')
        new_status = InfrastructureReport.STATUS_VERIFIED if decision == 'Confirmed' else InfrastructureReport.STATUS_SCHEDULED
        db_service.update_one('infrastructure_reports', {'_id': report_id}, {'status': new_status})

    return jsonify({
        'message': 'Professional sign-off submitted successfully.',
        'review_id': review_id,
        'decision': decision,
        'status': 'Verified'
    }), 200

@reviews_bp.route('/<assessment_id>', methods=['GET'])
def get_review(assessment_id):
    """Retrieves existing professional certification review for an assessment."""
    review = db_service.find_one('professional_reviews', {'assessment_id': assessment_id})
    if not review:
        return jsonify({'message': 'No review completed for this assessment yet.', 'review': None}), 200
    return jsonify({'review': review})
