from datetime import datetime, timezone
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

    # Update associated infrastructure report status and audit trail
    now_iso = datetime.now(timezone.utc).isoformat()
    image = db_service.find_one('submitted_images', {'_id': assessment.get('image_id')})
    if image:
        report_id = image.get('report_id')
        rep = db_service.find_one('infrastructure_reports', {'_id': report_id})
        if rep:
            meta = rep.get('metadata') or {}
            history = meta.get('status_history', [])
            history.append({
                'status': InfrastructureReport.STATUS_VERIFIED,
                'timestamp': now_iso,
                'updated_by': reviewer_id,
                'note': f"Engineer {decision}: {comments or 'Concurred with automated assessment.'}"
            })
            meta['status_history'] = history
            meta['engineer_decision'] = decision
            meta['engineer_notes'] = comments
            meta['reviewed_by'] = reviewer_id
            meta['reviewed_at'] = now_iso
            meta['requires_engineer_review'] = False
            db_service.update_one('infrastructure_reports', {'_id': report_id}, {
                'status': InfrastructureReport.STATUS_VERIFIED,
                'metadata': meta
            })

    return jsonify({
        'message': 'Engineer review and assessment validation submitted successfully.',
        'review_id': review_id,
        'decision': decision,
        'status': InfrastructureReport.STATUS_VERIFIED
    }), 200

@reviews_bp.route('/report/<report_id>', methods=['POST'])
@role_required('engineer', 'admin')
def review_by_report(current_user, report_id):
    """
    Direct Engineer Defect Review and Sign-off by Report ID.
    Transitions lifecycle status (Under Review -> Verified -> Resolved)
    and records engineer evaluation notes.
    """
    data = request.get_json() or {}
    decision = data.get('decision', 'Confirmed')
    target_status = data.get('target_status', InfrastructureReport.STATUS_VERIFIED)
    notes = data.get('notes', data.get('comments', '')).strip()
    reviewer_id = str(current_user.get('_id') or current_user.get('user_id'))
    reviewer_name = current_user.get('name', 'Civil Engineer')

    report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    if not report:
        return jsonify({'error': 'Infrastructure report not found.'}), 404

    current_status = InfrastructureReport.canonical_status(report.get('status', 'Received'))
    target_status = InfrastructureReport.canonical_status(target_status)

    if not InfrastructureReport.can_transition(current_status, target_status):
        return jsonify({'error': f"Transition from '{current_status}' to '{target_status}' is not permitted."}), 400

    now_iso = datetime.now(timezone.utc).isoformat()
    meta = report.get('metadata') or {}
    history = meta.get('status_history', [])
    history.append({
        'status': target_status,
        'timestamp': now_iso,
        'updated_by': reviewer_name,
        'note': f"Review {decision}: {notes or 'Status updated by reviewing engineer.'}"
    })
    meta['status_history'] = history
    meta['engineer_decision'] = decision
    meta['engineer_notes'] = notes
    meta['reviewed_by'] = reviewer_name
    meta['reviewed_at'] = now_iso
    if target_status in [InfrastructureReport.STATUS_VERIFIED, InfrastructureReport.STATUS_RESOLVED]:
        meta['requires_engineer_review'] = False

    db_service.update_one('infrastructure_reports', {'_id': report_id}, {
        'status': target_status,
        'metadata': meta
    })

    return jsonify({
        'message': f"Report successfully transitioned to '{target_status}'.",
        'report_id': report_id,
        'previous_status': current_status,
        'status': target_status,
        'engineer_decision': decision,
        'updated_at': now_iso
    }), 200

@reviews_bp.route('/<assessment_id>', methods=['GET'])
@role_required('engineer', 'admin')
def get_review(current_user, assessment_id):
    """Retrieves professional review record for a defect assessment."""
    review = db_service.find_one('professional_reviews', {'assessment_id': assessment_id})
    if not review:
        return jsonify({'message': 'No review completed for this assessment yet.', 'review': None}), 200
    return jsonify({'review': review}), 200
