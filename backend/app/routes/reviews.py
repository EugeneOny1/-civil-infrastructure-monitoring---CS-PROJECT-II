from datetime import datetime
from flask import Blueprint, request, jsonify
from ..models.review import ProfessionalReview
from ..models.report import InfrastructureReport
from ..services.database import db_service
from ..utils.auth_helpers import role_required

reviews_bp = Blueprint('reviews', __name__, url_prefix='/api/reviews')

@reviews_bp.route('/<assessment_id>', methods=['POST'])
@role_required('engineer', 'admin')
def submit_review(current_user, assessment_id):
    """
    FR-06: Engineer Defect Review & Assessment Validation.
    Allows verified civil engineers/inspectors to review, validate, or override
    automated AI detection and relative visual severity, adding professional review notes.
    """
    data = request.get_json() or {}
    decision = data.get('decision', ProfessionalReview.DECISION_CONFIRMED)
    comments = data.get('comments', '').strip()
    override_details = data.get('override_details', {})

    if decision not in [ProfessionalReview.DECISION_CONFIRMED, ProfessionalReview.DECISION_OVERRIDDEN]:
        return jsonify({'error': 'Invalid decision. Must be Confirmed or Overridden.'}), 400

    reviewer_id = str(current_user.get('_id') or current_user.get('user_id'))

    # Verify assessment exists
    assessment = db_service.find_one('ai_assessments', {'_id': assessment_id})
    if not assessment:
        return jsonify({'error': 'AIAssessment record not found.'}), 404

    # Create or update ProfessionalReview record
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

    # Update associated infrastructure report status
    image = db_service.find_one('submitted_images', {'_id': assessment.get('image_id')})
    if image:
        report_id = image.get('report_id')
        new_status = InfrastructureReport.STATUS_VERIFIED
        db_service.update_one('infrastructure_reports', {'_id': report_id}, {'status': new_status})

    return jsonify({
        'message': 'Engineer review and assessment validation submitted successfully.',
        'review_id': review_id,
        'decision': decision,
        'status': InfrastructureReport.STATUS_VERIFIED
    }), 200

@reviews_bp.route('/<assessment_id>', methods=['GET'])
@role_required('engineer', 'admin')
def get_review(current_user, assessment_id):
    """Retrieves professional review record for a defect assessment."""
    review = db_service.find_one('professional_reviews', {'assessment_id': assessment_id})
    if not review:
        return jsonify({'message': 'No review completed for this assessment yet.', 'review': None}), 200
    return jsonify({'review': review}), 200
