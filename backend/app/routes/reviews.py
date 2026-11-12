from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from ..models.review import ProfessionalReview
from ..models.report import InfrastructureReport
from ..services.database import db_service
from ..services.severity import severity_service
from ..utils.auth_helpers import role_required

reviews_bp = Blueprint('reviews', __name__, url_prefix='/api/reviews')

VALID_NEXT_ACTIONS = [
    'Continue monitoring',
    'On-site inspection recommended',
    'Refer to maintenance / responsible asset team',
    'Issue Safety Advisory',
    'No further action required at this stage'
]

def get_default_notebook_template(asset_type: str = 'Road / Pavement') -> dict:
    is_building = 'building' in (asset_type or '').lower()
    if is_building:
        items = [
            "Confirm reported structural / building defect type",
            "Inspect foundation / load-bearing wall condition",
            "Assess crack width, orientation and displacement",
            "Check for dampness, spalling, or reinforcement corrosion",
            "Evaluate building floor levels & vertical alignment",
            "Review occupant and public safety hazard level",
            "Determine if structural engineering evacuation/shoring required",
            "Assess drainage and stormwater impact on foundation",
            "Record recommended structural remedial action",
            "Schedule mandatory follow-up structural compliance inspection"
        ]
        title = "Building / Structural Inspection Objectives"
    else:
        items = [
            "Confirm reported defect type",
            "Inspect surrounding pavement condition",
            "Determine extent of visible distress",
            "Check for additional cracking/potholes/ravelling",
            "Review drainage/ponding evidence",
            "Assess road-user impact",
            "Determine likely maintenance priority",
            "Determine whether structural evaluation is required",
            "Record recommended remedial action",
            "Schedule follow-up inspection if necessary"
        ]
        title = "Road / Pavement Inspection Objectives"

    checklist = [
        {
            'id': f"obj_{i+1}",
            'text': text,
            'status': 'pending',
            'completed': False,
            'completed_by': None,
            'completed_at': None,
            'na_reason': ''
        }
        for i, text in enumerate(items)
    ]
    return {
        'title': title,
        'checklist': checklist,
        'note_cards': [],
        'evidence': [],
        'compliance_context': {},
        'last_updated_at': datetime.now(timezone.utc).isoformat(),
        'last_updated_by': 'System Initialization'
    }

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

            # Engineer Ownership & Accountability (Section 28)
            if not meta.get('original_verifying_engineer'):
                meta['original_verifying_engineer'] = {
                    'user_id': reviewer_id,
                    'name': reviewer_name,
                    'email': current_user.get('email', ''),
                    'verified_at': now_iso
                }
            if not meta.get('current_lead_engineer'):
                meta['current_lead_engineer'] = {
                    'user_id': reviewer_id,
                    'name': reviewer_name,
                    'email': current_user.get('email', ''),
                    'assigned_at': now_iso
                }
            meta['lead_engineer'] = meta.get('current_lead_engineer')
            if 'collaborators' not in meta:
                meta['collaborators'] = []
            if not meta.get('inspection_notebook') or not meta['inspection_notebook'].get('checklist'):
                meta['inspection_notebook'] = get_default_notebook_template(rep.get('asset_type') or meta.get('asset_type'))

            meta['assigned_engineer_id'] = reviewer_id
            meta['assigned_engineer_name'] = reviewer_name
            meta['assigned_engineer_email'] = current_user.get('email', '')
            meta['assigned_at'] = now_iso

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

    if current_status == InfrastructureReport.STATUS_RESOLVED and current_user.get('role') != 'admin':
        return jsonify({'error': 'This defect report has already completed professional review and resolution and is in read-only mode.'}), 400

    if current_user.get('role') != 'admin' and not InfrastructureReport.can_transition(current_status, target_status):
        return jsonify({'error': f"Transition from '{current_status}' to '{target_status}' is not permitted. Permitted forward lifecycle: Received -> Verified -> Under Review -> Resolved."}), 400

    now_iso = datetime.now(timezone.utc).isoformat()
    meta = report.get('metadata') or {}
    submitter_id = str(report.get('user_id') or meta.get('submitted_by_id') or '')
    is_self_review = bool(submitter_id and submitter_id == reviewer_id)

    # Resolution Guard when target is Resolved
    if target_status == InfrastructureReport.STATUS_RESOLVED:
        current_lead = meta.get('current_lead_engineer') or {}
        lead_id = str(current_lead.get('user_id') or meta.get('assigned_engineer_id') or '')
        if current_user.get('role') != 'admin' and lead_id and lead_id != reviewer_id:
            lead_name = current_lead.get('name') or meta.get('assigned_engineer_name', 'Lead Engineer')
            return jsonify({'error': f"Only the assigned Lead Engineer ({lead_name}) or an administrator can resolve this case."}), 403

        notebook = meta.get('inspection_notebook') or report.get('inspection_notebook') or {}
        checklist = notebook.get('checklist') or []
        incomplete_items = []
        for item in checklist:
            if isinstance(item, dict):
                st = item.get('status', 'pending')
                if st == 'pending' and not item.get('completed', False):
                    incomplete_items.append(item.get('text', 'Incomplete objective'))
                elif st == 'not_applicable' or item.get('is_na'):
                    if not str(item.get('na_reason', '')).strip():
                        incomplete_items.append(f"{item.get('text', 'Item')}: Missing N/A rationale")
        if incomplete_items:
            return jsonify({
                'error': f"Cannot resolve case: All inspection objectives must be completed or marked N/A with a documented reason. Pending/unjustified: {', '.join(incomplete_items[:3])}{'...' if len(incomplete_items) > 3 else ''}"
            }), 400

        if not notes and not notebook.get('summary_notes') and not notebook.get('note_cards'):
            return jsonify({
                'error': 'Cannot resolve case: A professional closure summary or engineering resolution note is required.'
            }), 400

    # Engineer Ownership & Accountability (Section 28)
    if target_status == InfrastructureReport.STATUS_VERIFIED:
        if not meta.get('original_verifying_engineer'):
            meta['original_verifying_engineer'] = {
                'user_id': reviewer_id,
                'name': reviewer_name,
                'email': current_user.get('email', ''),
                'verified_at': now_iso
            }
        if not meta.get('current_lead_engineer'):
            meta['current_lead_engineer'] = {
                'user_id': reviewer_id,
                'name': reviewer_name,
                'email': current_user.get('email', ''),
                'assigned_at': now_iso
            }
        if 'collaborators' not in meta:
            meta['collaborators'] = []
        if not meta.get('inspection_notebook') or not meta['inspection_notebook'].get('checklist'):
            meta['inspection_notebook'] = get_default_notebook_template(report.get('asset_type') or meta.get('asset_type'))

    if not meta.get('assigned_engineer_id'):
        meta['assigned_engineer_id'] = reviewer_id
        meta['assigned_engineer_name'] = reviewer_name
        meta['assigned_engineer_email'] = current_user.get('email', '')
        meta['assigned_at'] = now_iso

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

    # Automatically mark associated safety advisory inactive when report is Resolved
    if target_status == InfrastructureReport.STATUS_RESOLVED:
        meta['resolved_at'] = now_iso
        db_service.update_many('safety_advisories', {'report_id': report_id}, {
            'status': 'inactive',
            'closed_at': now_iso,
            'closed_reason': 'Report marked Resolved'
        })
        if 'safety_advisory' in meta and isinstance(meta['safety_advisory'], dict):
            meta['safety_advisory']['status'] = 'inactive'
            meta['safety_advisory']['closed_at'] = now_iso

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

    meta = report.get('metadata') or {}
    rep_loc = meta.get('location_name') or report.get('location_name') or report.get('location') or 'Monitored Infrastructure'
    rep_lat = report.get('latitude') or meta.get('latitude')
    rep_lng = report.get('longitude') or meta.get('longitude')

    advisory_doc = {
        'advisory_id': f"adv_{uuid.uuid4().hex[:10]}",
        'report_id': report_id,
        'category': category,
        'professional_note': note,
        'location_name': rep_loc,
        'latitude': rep_lat,
        'longitude': rep_lng,
        'issued_by_id': eng_id,
        'issued_by_name': eng_name,
        'issued_at': now_iso,
        'status': 'active'
    }

    # Store in report metadata
    meta['safety_advisory'] = advisory_doc
    db_service.update_one('infrastructure_reports', {'_id': report_id}, {'metadata': meta})

    # Record and dispatch operational notification
    notification_service.create_safety_advisory(advisory_doc)

    return jsonify({
        'message': 'Safety advisory published successfully.',
        'advisory': advisory_doc
    }), 201


@reviews_bp.route('/engineers/available', methods=['GET'])
@role_required('engineer', 'admin')
def get_available_engineers(current_user):
    """
    Returns list of accredited engineers eligible to be added as inspection collaborators.
    If report_id is provided, marks current lead engineer and existing collaborators.
    """
    report_id = request.args.get('report_id')
    lead_id = None
    collaborator_ids = set()
    if report_id:
        rep = db_service.find_one('infrastructure_reports', {'_id': report_id})
        if rep:
            meta = rep.get('metadata') or {}
            lead = meta.get('current_lead_engineer') or {}
            lead_id = str(lead.get('user_id') or meta.get('assigned_engineer_id') or '')
            for c in meta.get('collaborators', []):
                collaborator_ids.add(str(c.get('user_id')))

    all_users = db_service.find('users')
    engineers = []
    for u in all_users:
        if u.get('role') in ['engineer', 'admin']:
            u_id = str(u.get('_id') or u.get('user_id'))
            engineers.append({
                'user_id': u_id,
                'name': u.get('name', 'Certified Engineer'),
                'email': u.get('email', ''),
                'role': u.get('role', 'engineer'),
                'ebk_reg_no': u.get('ebk_reg_no', 'EBK-VERIFIED'),
                'organization': u.get('organization', 'KeNHA / Public Infrastructure'),
                'is_current_lead': bool(lead_id and u_id == lead_id),
                'is_collaborator': bool(u_id in collaborator_ids)
            })

    return jsonify({
        'engineers': engineers,
        'available_engineers': engineers
    }), 200


@reviews_bp.route('/report/<report_id>/collaborators', methods=['POST'])
@role_required('engineer', 'admin')
def add_collaborator(current_user, report_id):
    """
    Invites/assigns an accredited civil engineer as a collaborator on this defect inspection case.
    Authorized for Lead Engineer or Admin.
    """
    report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    if not report:
        return jsonify({'error': 'Report not found.'}), 404

    current_user_id = str(current_user.get('_id') or current_user.get('user_id'))
    meta = report.get('metadata') or {}
    lead = meta.get('current_lead_engineer') or {}
    lead_id = str(lead.get('user_id') or meta.get('assigned_engineer_id') or '')

    if current_user.get('role') != 'admin' and lead_id and lead_id != current_user_id:
        return jsonify({'error': 'Only the assigned Lead Engineer or an administrator may invite collaborators.'}), 403

    data = request.get_json() or {}
    engineer_id = str(data.get('engineer_id', '')).strip()
    role = data.get('role', 'Collaborator').strip() or 'Collaborator'
    invite_note = data.get('invite_note', '').strip()

    if not engineer_id:
        return jsonify({'error': 'engineer_id is required.'}), 400

    target_user = None
    for u in db_service.find('users'):
        if str(u.get('_id') or u.get('user_id')) == engineer_id:
            target_user = u
            break

    if not target_user:
        return jsonify({'error': 'Target engineer not found.'}), 404

    collaborators = meta.get('collaborators', [])
    if any(str(c.get('user_id')) == engineer_id for c in collaborators):
        return jsonify({'error': 'Engineer is already a collaborator on this case.'}), 400

    now_iso = datetime.now(timezone.utc).isoformat()
    new_collab = {
        'user_id': engineer_id,
        'name': target_user.get('name', 'Certified Engineer'),
        'email': target_user.get('email', ''),
        'role': role,
        'invited_by': current_user.get('name', 'Lead Engineer'),
        'invited_by_id': current_user_id,
        'invited_at': now_iso,
        'invite_note': invite_note
    }
    collaborators.append(new_collab)
    meta['collaborators'] = collaborators

    history = meta.get('status_history', [])
    history.append({
        'status': report.get('status'),
        'timestamp': now_iso,
        'updated_by': current_user.get('name', 'Lead Engineer'),
        'user_id': current_user_id,
        'note': f"Invited {target_user.get('name')} as {role}."
    })
    meta['status_history'] = history

    db_service.update_one('infrastructure_reports', {'_id': report_id}, {
        'metadata': meta,
        'last_updated_at': now_iso
    })

    from ..services.notification_service import notification_service
    loc = meta.get('location_name') or report.get('location_name') or 'Monitored defect'
    notification_service.create_notification(
        engineer_id,
        report_id,
        'assignment',
        'Inspection Collaboration Invite',
        f"You have been invited by {current_user.get('name')} as {role} for defect inspection at {loc}."
    )

    return jsonify({
        'message': f"Engineer {target_user.get('name')} invited successfully.",
        'collaborator': new_collab,
        'collaborators': collaborators
    }), 201


@reviews_bp.route('/report/<report_id>/collaborators/<engineer_id>', methods=['DELETE'])
@role_required('engineer', 'admin')
def remove_collaborator(current_user, report_id, engineer_id):
    """
    Removes a collaborator from the inspection case.
    Authorized for Lead Engineer or Admin.
    """
    report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    if not report:
        return jsonify({'error': 'Report not found.'}), 404

    current_user_id = str(current_user.get('_id') or current_user.get('user_id'))
    meta = report.get('metadata') or {}
    lead = meta.get('current_lead_engineer') or {}
    lead_id = str(lead.get('user_id') or meta.get('assigned_engineer_id') or '')

    if current_user.get('role') != 'admin' and lead_id and lead_id != current_user_id:
        return jsonify({'error': 'Only the assigned Lead Engineer or an administrator may remove collaborators.'}), 403

    collaborators = meta.get('collaborators', [])
    updated = [c for c in collaborators if str(c.get('user_id')) != str(engineer_id)]
    if len(updated) == len(collaborators):
        return jsonify({'error': 'Collaborator not found on this case.'}), 404

    now_iso = datetime.now(timezone.utc).isoformat()
    meta['collaborators'] = updated
    db_service.update_one('infrastructure_reports', {'_id': report_id}, {
        'metadata': meta,
        'last_updated_at': now_iso
    })

    return jsonify({
        'message': 'Collaborator removed successfully.',
        'collaborators': updated
    }), 200


@reviews_bp.route('/report/<report_id>/transfer-lead', methods=['POST'])
@role_required('engineer', 'admin')
def transfer_lead_engineer(current_user, report_id):
    """
    Transfers Lead Engineer responsibility with mandatory transfer reason.
    Authorized for current Lead Engineer or Admin.
    """
    report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    if not report:
        return jsonify({'error': 'Report not found.'}), 404

    current_user_id = str(current_user.get('_id') or current_user.get('user_id'))
    meta = report.get('metadata') or {}
    lead = meta.get('current_lead_engineer') or {}
    lead_id = str(lead.get('user_id') or meta.get('assigned_engineer_id') or '')

    if current_user.get('role') != 'admin' and lead_id and lead_id != current_user_id:
        return jsonify({'error': 'Only the current Lead Engineer or an administrator may transfer case leadership.'}), 403

    data = request.get_json() or {}
    new_lead_id = str(data.get('new_lead_engineer_id') or data.get('new_lead_id') or '').strip()
    reason = str(data.get('transfer_reason') or data.get('reason') or '').strip()

    if not new_lead_id:
        return jsonify({'error': 'new_lead_engineer_id is required.'}), 400
    if not reason:
        return jsonify({'error': 'A formal transfer reason is required.'}), 400

    target_user = None
    for u in db_service.find('users'):
        if str(u.get('_id') or u.get('user_id')) == new_lead_id:
            target_user = u
            break

    if not target_user:
        return jsonify({'error': 'Target engineer not found.'}), 404

    now_iso = datetime.now(timezone.utc).isoformat()
    old_lead_name = lead.get('name') or meta.get('assigned_engineer_name', current_user.get('name', 'Certified Engineer'))

    transfer_history = meta.get('lead_transfer_history', [])
    transfer_history.append({
        'from_user_id': lead_id or current_user_id,
        'from_name': old_lead_name,
        'to_user_id': new_lead_id,
        'to_name': target_user.get('name', 'Certified Engineer'),
        'reason': reason,
        'timestamp': now_iso,
        'authorized_by': current_user.get('name')
    })
    meta['lead_transfer_history'] = transfer_history

    new_lead_doc = {
        'user_id': new_lead_id,
        'name': target_user.get('name', 'Certified Engineer'),
        'email': target_user.get('email', ''),
        'assigned_at': now_iso
    }
    meta['current_lead_engineer'] = new_lead_doc
    meta['assigned_engineer_id'] = new_lead_id
    meta['assigned_engineer_name'] = target_user.get('name', 'Certified Engineer')
    meta['assigned_engineer_email'] = target_user.get('email', '')

    # Retain previous lead in collaborators team, remove promoted lead from collaborators
    collaborators = meta.get('collaborators', [])
    updated_collabs = [c for c in collaborators if str(c.get('user_id')) != new_lead_id]
    if lead_id and lead_id != new_lead_id and not any(str(c.get('user_id')) == lead_id for c in updated_collabs):
        updated_collabs.append({
            'user_id': lead_id,
            'name': old_lead_name,
            'email': meta.get('assigned_engineer_email', ''),
            'role': 'Former Lead Engineer',
            'invited_at': now_iso,
            'invited_by': current_user.get('name', 'Certified Engineer')
        })
    meta['collaborators'] = updated_collabs

    history = meta.get('status_history', [])
    history.append({
        'status': report.get('status'),
        'timestamp': now_iso,
        'updated_by': current_user.get('name', 'Lead Engineer'),
        'user_id': current_user_id,
        'note': f"Lead responsibility transferred from {old_lead_name} to {target_user.get('name')}. Reason: {reason}"
    })
    meta['status_history'] = history

    db_service.update_one('infrastructure_reports', {'_id': report_id}, {
        'metadata': meta,
        'last_updated_at': now_iso
    })

    from ..services.notification_service import notification_service
    loc = meta.get('location_name') or report.get('location_name') or 'Monitored defect'
    notification_service.create_notification(
        new_lead_id,
        report_id,
        'lead_assignment',
        'Lead Engineer Assigned',
        f"You are now the Lead Engineer for defect casework at {loc}. Transferred by {current_user.get('name')}: {reason}"
    )

    return jsonify({
        'message': f"Lead responsibility transferred to {target_user.get('name')}.",
        'current_lead_engineer': new_lead_doc,
        'lead_engineer': new_lead_doc
    }), 200


def process_field_measurements(data: dict, current_user: dict, default_defect: str = 'Pothole') -> tuple:
    """
    Processes, normalizes, and validates physical engineering measurements.
    Computes FHWA LTPP depth classification for potholes if valid measured depth exists.
    Maintains strict separation: does NOT infer depth or crack width from monocular images.
    """
    defect_type = (data.get('defect_type') or data.get('defect_class') or default_defect or 'Pothole').strip()
    reviewer_id = str(current_user.get('_id') or current_user.get('user_id'))
    reviewer_name = current_user.get('name', 'Certified Engineer')
    ebk_reg = current_user.get('registration_number') or current_user.get('ebk_number') or ''
    now_iso = datetime.now(timezone.utc).isoformat()
    measured_at = data.get('measured_at') or data.get('timestamp') or now_iso
    method = (data.get('method') or data.get('instrument') or 'Direct Field Measurement').strip()
    notes = (data.get('notes') or '').strip()

    measurements = {}
    fhwa_assessment = None

    if 'pothole' in defect_type.lower():
        depth = data.get('max_depth') if data.get('max_depth') is not None else data.get('depth')
        unit = (data.get('depth_unit') or data.get('unit') or 'mm').strip().lower()
        length = data.get('length')
        width = data.get('width')

        depth_mm = severity_service.normalize_measurement(depth, unit) if depth is not None else None
        length_mm = severity_service.normalize_measurement(length, unit) if length is not None else None
        width_mm = severity_service.normalize_measurement(width, unit) if width is not None else None

        measurements = {
            'max_depth_raw': depth,
            'max_depth_mm': depth_mm,
            'length_raw': length,
            'length_mm': length_mm,
            'width_raw': width,
            'width_mm': width_mm,
            'unit': unit,
            'method': method,
            'notes': notes
        }

        if depth_mm is not None:
            fhwa_assessment = severity_service.assess_pothole_fhwa(depth_mm, 'mm')
            if fhwa_assessment:
                fhwa_assessment['assessed_by'] = reviewer_name
                fhwa_assessment['assessed_by_id'] = reviewer_id
                fhwa_assessment['assessed_at'] = now_iso

    elif 'crack' in defect_type.lower():
        width = data.get('crack_width') if data.get('crack_width') is not None else data.get('width')
        length = data.get('crack_length') if data.get('crack_length') is not None else data.get('length')
        unit = (data.get('unit') or 'mm').strip().lower()

        width_mm = severity_service.normalize_measurement(width, unit) if width is not None else None
        length_mm = severity_service.normalize_measurement(length, unit) if length is not None else None

        measurements = {
            'crack_width_raw': width,
            'crack_width_mm': width_mm,
            'crack_length_raw': length,
            'crack_length_mm': length_mm,
            'unit': unit,
            'method': method,
            'notes': notes
        }
        # For cracks, record physical dimensions without fabricating an automated physical severity category
        fhwa_assessment = None

    else:
        # Surface deterioration or general civil asset distress
        area = data.get('area') or data.get('area_m2')
        length = data.get('length')
        width = data.get('width')
        unit = (data.get('unit') or 'm').strip().lower()

        measurements = {
            'area_m2': float(area) if area is not None else None,
            'length': float(length) if length is not None else None,
            'width': float(width) if width is not None else None,
            'unit': unit,
            'method': method,
            'notes': notes
        }
        fhwa_assessment = None

    record = {
        'source': 'professional_field_measurement',
        'defect_type': defect_type,
        'method': method,
        'measurements': measurements,
        'engineering_assessment': fhwa_assessment,
        'engineer_id': reviewer_id,
        'engineer_name': reviewer_name,
        'assessed_by_id': reviewer_id,
        'assessed_by': reviewer_name,
        'registration_number': ebk_reg,
        'timestamp': measured_at,
        'notes': notes
    }

    return record, fhwa_assessment


@reviews_bp.route('/report/<report_id>/inspection-notebook', methods=['POST', 'PUT'])
@role_required('engineer', 'admin')
def update_inspection_notebook(current_user, report_id):
    """
    Sections 30-33 & 43: Saves inspection checklist, visual note cards, evidence, and compliance context.
    Includes concurrency detection (expected_updated_at), physical measurements, and user attribution.
    """
    if current_user.get('role') not in ['engineer', 'admin']:
        return jsonify({'error': 'Forbidden: Only verified civil engineers or administrators may modify the inspection notebook.'}), 403

    data = request.get_json() or {}
    report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    if not report:
        return jsonify({'error': 'Infrastructure report not found.'}), 404

    now_iso = datetime.now(timezone.utc).isoformat()
    meta = report.get('metadata') or {}
    notebook = meta.get('inspection_notebook') or {}

    expected_updated_at = data.get('expected_updated_at')
    if expected_updated_at and notebook.get('last_updated_at'):
        if expected_updated_at != notebook.get('last_updated_at'):
            return jsonify({
                'error': 'Inspection notebook was modified by another engineer since you loaded it. Please reload the latest changes.',
                'current_notebook': notebook,
                'conflict': True
            }), 409

    cl = data.get('checklist') or data.get('inspection_checklist')
    if cl is not None:
        notebook['checklist'] = cl
    if 'note_cards' in data:
        notebook['note_cards'] = data['note_cards']
    if 'evidence' in data:
        notebook['evidence'] = data['evidence']
    if 'compliance_context' in data:
        notebook['compliance_context'] = data['compliance_context']
    if 'summary_notes' in data:
        notebook['summary_notes'] = data['summary_notes']

    # Process field measurements if provided
    if 'physical_measurements' in data:
        p_raw = data['physical_measurements']
        def_class = meta.get('defect_class') or report.get('defect_class') or 'Pothole'
        p_rec, p_fhwa = process_field_measurements(p_raw, current_user, default_defect=def_class)
        notebook['physical_measurements'] = p_rec
        meta['physical_measurements'] = p_rec
        if p_fhwa:
            notebook['physical_engineering_assessment'] = p_fhwa
            meta['physical_engineering_assessment'] = p_fhwa

    notebook['last_updated_at'] = now_iso
    notebook['last_updated_by'] = current_user.get('name', 'Civil Engineer')
    notebook['last_updated_by_id'] = str(current_user.get('_id') or current_user.get('user_id'))

    meta['inspection_notebook'] = notebook

    db_service.update_one('infrastructure_reports', {'_id': report_id}, {
        'metadata': meta,
        'last_updated_at': now_iso
    })

    return jsonify({
        'message': 'Inspection notebook updated successfully.',
        'inspection_notebook': notebook
    }), 200


@reviews_bp.route('/report/<report_id>/measurements', methods=['POST'])
@role_required('engineer', 'admin')
def record_physical_measurements(current_user, report_id):
    """
    Records professional physical field measurements (e.g. pothole depth, crack width).
    Strictly role-protected: Citizens cannot submit engineering measurements (returns 403).
    Computes FHWA LTPP depth classification for potholes if valid measured depth exists.
    """
    if current_user.get('role') not in ['engineer', 'admin']:
        return jsonify({'error': 'Forbidden: Only verified civil engineers or administrators may record physical measurements.'}), 403

    report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    if not report:
        return jsonify({'error': 'Infrastructure report not found.'}), 404

    data = request.get_json() or {}
    meta = report.get('metadata') or {}
    def_class = meta.get('defect_class') or report.get('defect_class') or 'Pothole'

    p_rec, p_fhwa = process_field_measurements(data, current_user, default_defect=def_class)

    now_iso = datetime.now(timezone.utc).isoformat()
    meta['physical_measurements'] = p_rec
    if p_fhwa:
        meta['physical_engineering_assessment'] = p_fhwa

    notebook = meta.get('inspection_notebook') or {}
    notebook['physical_measurements'] = p_rec
    if p_fhwa:
        notebook['physical_engineering_assessment'] = p_fhwa
    notebook['last_updated_at'] = now_iso
    notebook['last_updated_by'] = current_user.get('name', 'Civil Engineer')
    notebook['last_updated_by_id'] = str(current_user.get('_id') or current_user.get('user_id'))
    meta['inspection_notebook'] = notebook

    history = meta.get('status_history', [])
    meas_summary = f"{p_rec['defect_type']} physical measurement recorded"
    if p_fhwa:
        meas_summary += f" [FHWA LTPP: {p_fhwa['category']} severity ({p_fhwa['measured_depth_mm']}mm)]"
    history.append({
        'status': report.get('status'),
        'timestamp': now_iso,
        'updated_by': current_user.get('name', 'Certified Engineer'),
        'user_id': str(current_user.get('_id') or current_user.get('user_id')),
        'note': meas_summary
    })
    meta['status_history'] = history

    db_service.update_one('infrastructure_reports', {'_id': report_id}, {
        'metadata': meta,
        'last_updated_at': now_iso
    })

    return jsonify({
        'message': 'Physical field measurement and engineering assessment recorded successfully.',
        'physical_measurements': p_rec,
        'engineering_assessment': p_fhwa
    }), 201


