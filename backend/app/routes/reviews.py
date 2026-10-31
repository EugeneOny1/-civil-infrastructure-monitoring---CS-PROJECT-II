from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from ..models.review import ProfessionalReview
from ..models.report import InfrastructureReport
from ..services.database import db_service
from ..utils.auth_helpers import role_required

reviews_bp = Blueprint('reviews', __name__, url_prefix='/api/reviews')

VALID_NEXT_ACTIONS = [
    'Continue monitoring',
    'On-site inspection recommended',
    'Refer to maintenance / responsible asset team',
    'Issue Safety Advisory',
    'No further action required at this stage'
]

@reviews_bp.route('/<assessment_id>', methods=['POST'])
@role_required('engineer', 'admin')
def submit_review(current_user, assessment_id):
    """
    FR-06: Engineer Defect Review & Assessment Validation.
    Allows verified civil engineers/inspectors to review, validate, or override
    automated AI detection and relative visual severity, adding professional review notes
    and next action recommendations.
    """
    data = request.get_json() or {}
    decision = data.get('decision', ProfessionalReview.DECISION_CONFIRMED)
    comments = data.get('comments', '').strip()
    override_details = data.get('override_details', {})
    next_action = data.get('next_action', '').strip()
    follow_up_date = data.get('follow_up_date', '').strip()

    if decision not in [ProfessionalReview.DECISION_CONFIRMED, ProfessionalReview.DECISION_OVERRIDDEN]:
        return jsonify({'error': 'Invalid decision. Must be Confirmed or Overridden.'}), 400

    if next_action and next_action not in VALID_NEXT_ACTIONS:
        return jsonify({'error': f"Invalid next action. Permitted options: {', '.join(VALID_NEXT_ACTIONS)}"}), 400

    reviewer_id = str(current_user.get('_id') or current_user.get('user_id'))

    # Verify assessment exists
    assessment = db_service.find_one('ai_assessments', {'_id': assessment_id})
    if not assessment:
        return jsonify({'error': 'AIAssessment record not found.'}), 404

    # Enforce read-only mode for resolved reports
    image = db_service.find_one('submitted_images', {'_id': assessment.get('image_id')})
    if image:
        report_id = image.get('report_id')
        rep = db_service.find_one('infrastructure_reports', {'_id': report_id})
        if rep and InfrastructureReport.canonical_status(rep.get('status')) == InfrastructureReport.STATUS_RESOLVED:
            return jsonify({'error': 'This defect report has already completed professional review and resolution and is in read-only mode.'}), 400

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
            submitter_id = str(rep.get('user_id') or meta.get('submitted_by_id') or '')
            is_self_review = bool(submitter_id and submitter_id == reviewer_id)
            reviewer_name = current_user.get('name', 'Civil Engineer')

            history = meta.get('status_history', [])
            note_prefix = "Engineer (Self-submitted inspection)" if is_self_review else "Engineer"
            action_log = f" [Next Action: {next_action}]" if next_action else ""
            history.append({
                'status': InfrastructureReport.STATUS_VERIFIED,
                'timestamp': now_iso,
                'updated_by': f"{reviewer_name} (Reviewer)",
                'submitter_id': submitter_id,
                'reviewer_id': reviewer_id,
                'is_self_review': is_self_review,
                'next_action': next_action,
                'follow_up_date': follow_up_date if next_action == 'On-site inspection recommended' else '',
                'note': f"{note_prefix} {decision}: {comments or 'Concurred with automated assessment.'}{action_log}"
            })
            meta['status_history'] = history
            meta['engineer_decision'] = decision
            meta['engineer_notes'] = comments
            meta['submitted_by_id'] = submitter_id
            meta['reviewer_id'] = reviewer_id
            meta['reviewed_by'] = reviewer_name
            meta['reviewed_at'] = now_iso
            meta['is_self_review'] = is_self_review
            meta['requires_engineer_review'] = False
            if next_action:
                meta['next_action'] = next_action
            if follow_up_date and next_action == 'On-site inspection recommended':
                meta['follow_up_date'] = follow_up_date

            meta['engineer_assessment'] = {
                'decision': decision,
                'override_details': override_details,
                'comments': comments,
                'next_action': next_action,
                'follow_up_date': follow_up_date if next_action == 'On-site inspection recommended' else '',
                'reviewer_id': reviewer_id,
                'reviewer_name': reviewer_name,
                'reviewed_at': now_iso
            }

            db_service.update_one('infrastructure_reports', {'_id': report_id}, {
                'status': InfrastructureReport.STATUS_VERIFIED,
                'metadata': meta
            })

            # Citizen feedback notification on professional review
            if submitter_id:
                from ..services.notification_service import notification_service
                action_text = f" Next Action: {next_action}." if next_action else ""
                date_text = f" Target Inspection: {follow_up_date}." if (follow_up_date and next_action == 'On-site inspection recommended') else ""
                if decision == ProfessionalReview.DECISION_OVERRIDDEN:
                    orig_class = assessment.get('defect_class', 'Defect')
                    orig_sev = assessment.get('relative_severity', 'Low')
                    corr_class = override_details.get('override_class', orig_class)
                    corr_sev = override_details.get('override_severity', orig_sev)
                    changes = []
                    if corr_class != orig_class:
                        changes.append(f"{orig_class} → {corr_class}")
                    if corr_sev != orig_sev:
                        changes.append(f"{orig_sev} → {corr_sev}")
                    change_str = ", ".join(changes) if changes else f"{corr_class} ({corr_sev})"
                    reason_str = f" Reason: {comments}." if comments else ""
                    msg = f"Engineer assessment updated: {change_str}.{reason_str}{action_text}{date_text}"
                    notification_service.create_notification(submitter_id, report_id, 'override', 'Assessment Updated', msg)
                else:
                    feedback_str = f" Engineer feedback: {comments}." if comments and comments != 'Confirmed' else ""
                    msg = f"Your report has been professionally verified.{feedback_str}{action_text}{date_text}"
                    notification_service.create_notification(submitter_id, report_id, 'verified', 'Report Verified', msg)

    return jsonify({
        'message': 'Engineer review and assessment validation submitted successfully.',
        'review_id': review_id,
        'decision': decision,
        'next_action': next_action,
        'follow_up_date': follow_up_date,
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
    next_action = data.get('next_action', '').strip()
    follow_up_date = data.get('follow_up_date', '').strip()
    reviewer_id = str(current_user.get('_id') or current_user.get('user_id'))
    reviewer_name = current_user.get('name', 'Civil Engineer')

    if next_action and next_action not in VALID_NEXT_ACTIONS:
        return jsonify({'error': f"Invalid next action. Permitted options: {', '.join(VALID_NEXT_ACTIONS)}"}), 400

    report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    if not report:
        return jsonify({'error': 'Infrastructure report not found.'}), 404

    current_status = InfrastructureReport.canonical_status(report.get('status', 'Received'))
    target_status = InfrastructureReport.canonical_status(target_status)

    if current_status == InfrastructureReport.STATUS_RESOLVED:
        return jsonify({'error': 'This defect report has already completed professional review and resolution and is in read-only mode.'}), 400

    if not InfrastructureReport.can_transition(current_status, target_status):
        return jsonify({'error': f"Transition from '{current_status}' to '{target_status}' is not permitted."}), 400

    now_iso = datetime.now(timezone.utc).isoformat()
    meta = report.get('metadata') or {}
    submitter_id = str(report.get('user_id') or meta.get('submitted_by_id') or '')
    is_self_review = bool(submitter_id and submitter_id == reviewer_id)

    history = meta.get('status_history', [])
    note_prefix = "Review (Self-submitted report)" if is_self_review else "Review"
    action_log = f" [Next Action: {next_action}]" if next_action else ""
    history.append({
        'status': target_status,
        'timestamp': now_iso,
        'updated_by': f"{reviewer_name} (Reviewer)",
        'submitter_id': submitter_id,
        'reviewer_id': reviewer_id,
        'is_self_review': is_self_review,
        'next_action': next_action,
        'follow_up_date': follow_up_date if next_action == 'On-site inspection recommended' else '',
        'note': f"{note_prefix} {decision}: {notes or 'Status updated by reviewing engineer.'}{action_log}"
    })
    meta['status_history'] = history
    meta['engineer_decision'] = decision
    meta['engineer_notes'] = notes
    meta['submitted_by_id'] = submitter_id
    meta['reviewer_id'] = reviewer_id
    meta['reviewed_by'] = reviewer_name
    meta['reviewed_at'] = now_iso
    meta['is_self_review'] = is_self_review
    override_details = data.get('override_details', {})
    if target_status in [InfrastructureReport.STATUS_VERIFIED, InfrastructureReport.STATUS_RESOLVED]:
        meta['requires_engineer_review'] = False

    if next_action:
        meta['next_action'] = next_action
    if follow_up_date and next_action == 'On-site inspection recommended':
        meta['follow_up_date'] = follow_up_date

    meta['engineer_assessment'] = {
        'decision': decision,
        'override_details': override_details,
        'notes': notes,
        'next_action': next_action,
        'follow_up_date': follow_up_date if next_action == 'On-site inspection recommended' else '',
        'reviewer_id': reviewer_id,
        'reviewer_name': reviewer_name,
        'reviewed_at': now_iso
    }

    db_service.update_one('infrastructure_reports', {'_id': report_id}, {
        'status': target_status,
        'metadata': meta
    })

    # Dispatch citizen report feedback notification
    if submitter_id:
        from ..services.notification_service import notification_service
        action_text = f" Next Action: {next_action}." if next_action else ""
        date_text = f" Target Inspection: {follow_up_date}." if (follow_up_date and next_action == 'On-site inspection recommended') else ""
        if target_status == InfrastructureReport.STATUS_RESOLVED:
            feedback_str = f" Note: {notes}" if notes else ""
            msg = f"Your infrastructure report has been marked resolved.{feedback_str}"
            notification_service.create_notification(submitter_id, report_id, 'resolved', 'Report Resolved', msg)
        elif decision == 'Overridden' and override_details:
            corr_class = override_details.get('override_class')
            corr_sev = override_details.get('override_severity')
            orig_class = meta.get('defect_class', 'Defect')
            orig_sev = meta.get('relative_severity', 'Low')
            changes = []
            if corr_class and corr_class != orig_class:
                changes.append(f"{orig_class} → {corr_class}")
            if corr_sev and corr_sev != orig_sev:
                changes.append(f"{orig_sev} → {corr_sev}")
            change_str = ", ".join(changes) if changes else (f"{corr_class} ({corr_sev})" if corr_class else "Updated")
            reason_str = f" Reason: {notes}." if notes else ""
            msg = f"Engineer assessment updated: {change_str}.{reason_str}{action_text}{date_text}"
            notification_service.create_notification(submitter_id, report_id, 'override', 'Assessment Updated', msg)
        elif target_status == InfrastructureReport.STATUS_VERIFIED:
            feedback_str = f" Engineer feedback: {notes}." if notes and notes != 'Confirmed' else ""
            msg = f"Your report has been professionally verified.{feedback_str}{action_text}{date_text}"
            notification_service.create_notification(submitter_id, report_id, 'verified', 'Report Verified', msg)

    return jsonify({
        'message': f"Report successfully transitioned to '{target_status}'.",
        'report_id': report_id,
        'previous_status': current_status,
        'status': target_status,
        'engineer_decision': decision,
        'next_action': next_action,
        'follow_up_date': follow_up_date,
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

@reviews_bp.route('/<report_id>/safety-advisory', methods=['POST'])
@role_required('engineer', 'admin')
def issue_safety_advisory(current_user, report_id):
    """
    FR-06 / Section S: Engineer-issued Report-Linked Safety Advisory.
    Controlled categories:
    - Exercise caution
    - Avoid this area
    - Dangerous road defect
    - Reduce speed / drive with caution
    - Inspection underway
    - Temporary access concern
    """
    import uuid
    from ..services.notification_service import notification_service

    ALLOWED_CATEGORIES = [
        'Exercise caution',
        'Avoid this area',
        'Dangerous road defect',
        'Reduce speed / drive with caution',
        'Inspection underway',
        'Temporary access concern'
    ]

    data = request.get_json() or {}
    category = data.get('category', '').strip()
    note = data.get('note', '').strip()

    if category not in ALLOWED_CATEGORIES:
        return jsonify({
            'error': f"Invalid advisory category. Permitted: {', '.join(ALLOWED_CATEGORIES)}"
        }), 400

    report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    if not report:
        return jsonify({'error': 'Infrastructure report not found.'}), 404

    now_iso = datetime.now(timezone.utc).isoformat()
    eng_id = str(current_user.get('_id') or current_user.get('user_id'))
    eng_name = current_user.get('name', 'Civil Engineer')

    advisory_doc = {
        'advisory_id': f"adv_{uuid.uuid4().hex[:10]}",
        'report_id': report_id,
        'category': category,
        'professional_note': note,
        'location_name': report.get('location_name', 'Monitored Infrastructure'),
        'latitude': report.get('latitude'),
        'longitude': report.get('longitude'),
        'issued_by_id': eng_id,
        'issued_by_name': eng_name,
        'issued_at': now_iso
    }

    # Store in report metadata
    meta = report.get('metadata') or {}
    meta['safety_advisory'] = advisory_doc
    db_service.update_one('infrastructure_reports', {'_id': report_id}, {'metadata': meta})

    # Record and dispatch operational notification
    notification_service.create_safety_advisory(advisory_doc)

    return jsonify({
        'message': 'Safety advisory published successfully.',
        'advisory': advisory_doc
    }), 201
