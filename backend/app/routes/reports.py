import os
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from ..models.report import InfrastructureReport, SubmittedImage
from ..models.assessment import AIAssessment
from ..models.asset import InfrastructureAsset
from ..services.database import db_service
from ..services.inference import inference_service
from ..utils.auth_helpers import get_current_user, login_required
from ..utils.file_helpers import allowed_file, save_uploaded_image

reports_bp = Blueprint('reports', __name__, url_prefix='/api/reports')

@reports_bp.route('', methods=['POST'])
@login_required
def submit_report(current_user):
    """
    FR-02 & FR-03: Defect report submission workflow.
    Validates uploaded photograph, executes SSD-MobileNetV2 defect detection,
    evaluates FR-04 relative visual severity, and persists records.
    """
    if 'image' not in request.files:
        return jsonify({'error': 'An infrastructure photograph is required.'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No image file selected.'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file format. Permitted formats: PNG, JPG, JPEG, WEBP.'}), 400

    # Retrieve form metadata
    location = request.form.get('location', '').strip()
    asset_type = request.form.get('asset_type', 'Road / Pavement').strip()
    description = request.form.get('description', '').strip()

    if not location:
        return jsonify({'error': 'Defect location is required.'}), 400

    user_id = str(current_user.get('_id') or current_user.get('user_id'))

    # Save uploaded image safely
    try:
        unique_filename, dest_path, orig_name, file_size = save_uploaded_image(file)
    except ValueError as val_err:
        return jsonify({'error': str(val_err)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to process image upload: {str(e)}'}), 500

    # Execute Computer Vision SSD-MobileNetV2 defect detection
    try:
        detection_result = inference_service.detect_defects(dest_path)
    except Exception as e:
        return jsonify({'error': f'Automated defect analysis failed: {str(e)}'}), 500

    # Associate with Infrastructure Asset record
    matched_asset = db_service.find_one('infrastructure_assets', {'location': location})
    if not matched_asset:
        asset_obj = InfrastructureAsset(
            asset_type=asset_type,
            location=location,
            description=f"Monitored asset at {location}",
            current_condition='Critical' if detection_result['relative_severity'] == 'Critical' else 'Poor'
        )
        asset_id = db_service.insert('infrastructure_assets', asset_obj.to_dict())
    else:
        asset_id = matched_asset['_id']

    # Create InfrastructureReport
    report = InfrastructureReport(
        user_id=user_id,
        asset_id=asset_id,
        description=description or f"Observed {detection_result['defect_class']} defect.",
        status=InfrastructureReport.STATUS_PENDING,
        metadata={
            'location_name': location,
            'asset_type': asset_type,
            'relative_severity': detection_result['relative_severity']
        }
    )
    report_id = db_service.insert('infrastructure_reports', report.to_dict())
    report.report_id = report_id

    # Create SubmittedImage record
    submitted_img = SubmittedImage(
        report_id=report_id,
        image_path=unique_filename,
        original_filename=orig_name,
        file_size=file_size,
        dimensions=detection_result['image_dimensions']
    )
    image_id = db_service.insert('submitted_images', submitted_img.to_dict())
    submitted_img.image_id = image_id

    # Create AIAssessment record
    ai_assessment = AIAssessment(
        image_id=image_id,
        defect_class=detection_result['defect_class'],
        confidence_score=detection_result['confidence_score'],
        bounding_box=detection_result['bounding_box'],
        relative_severity=detection_result['relative_severity'],
        detections=detection_result['detections'],
        model_name=detection_result['model_name']
    )
    assessment_id = db_service.insert('ai_assessments', ai_assessment.to_dict())
    ai_assessment.assessment_id = assessment_id

    return jsonify({
        'message': 'Infrastructure defect report submitted and analyzed successfully.',
        'report_id': report_id,
        'status': report.status,
        'report': report.to_dict(),
        'image': {
            'image_id': image_id,
            'filename': unique_filename,
            'url': f"/api/reports/images/{unique_filename}",
            'dimensions': detection_result['image_dimensions']
        },
        'ai_assessment': {
            'assessment_id': assessment_id,
            'model_name': detection_result['model_name'],
            'model_version': detection_result['model_version'],
            'defect_class': detection_result['defect_class'],
            'confidence_score': detection_result['confidence_score'],
            'confidence_percentage': round(detection_result['confidence_score'] * 100, 1),
            'relative_severity': detection_result['relative_severity'],
            'area_percentage': detection_result['area_percentage'],
            'bounding_box': detection_result['bounding_box'],
            'detections': detection_result['detections'],
            'disclaimer': detection_result['disclaimer']
        }
    }), 201

@reports_bp.route('', methods=['GET'])
@login_required
def list_reports(current_user):
    """
    FR-05 & FR-07: List infrastructure reports.
    Role-scoped: Citizens receive only their submissions; Engineers/Admins view the full queue.
    """
    user_role = current_user.get('role', 'citizen')
    user_id = str(current_user.get('_id') or current_user.get('user_id'))

    query = {}
    if user_role == 'citizen':
        query['user_id'] = user_id

    severity_filter = request.args.get('severity')
    status_filter = request.args.get('status')
    defect_class_filter = request.args.get('defect_class')

    if status_filter:
        query['status'] = status_filter

    reports = db_service.find('infrastructure_reports', query, sort_key='date_submitted', reverse=True)

    enriched_reports = []
    for rep in reports:
        report_id = rep['_id']
        image = db_service.find_one('submitted_images', {'report_id': report_id})
        assessment = None
        if image:
            assessment = db_service.find_one('ai_assessments', {'image_id': image['_id']})
            image_info = {
                'image_id': image['_id'],
                'filename': image['image_path'],
                'url': f"/api/reports/images/{image['image_path']}",
                'dimensions': image.get('dimensions', {})
            }
        else:
            image_info = None

        asset = db_service.find_one('infrastructure_assets', {'_id': rep.get('asset_id')})
        review = None
        if assessment:
            review = db_service.find_one('professional_reviews', {'assessment_id': assessment['_id']})

        # Apply client filters on assessment fields
        if severity_filter and assessment and assessment.get('relative_severity') != severity_filter:
            continue
        if defect_class_filter and assessment and assessment.get('defect_class') != defect_class_filter:
            continue

        enriched_reports.append({
            'report_id': report_id,
            'user_id': rep.get('user_id'),
            'description': rep.get('description'),
            'status': rep.get('status'),
            'date_submitted': rep.get('date_submitted'),
            'metadata': rep.get('metadata', {}),
            'asset': asset or {
                'location': rep.get('metadata', {}).get('location_name', 'Monitored Infrastructure'),
                'asset_type': rep.get('metadata', {}).get('asset_type', 'Road / Pavement')
            },
            'image': image_info,
            'assessment': assessment,
            'review': review
        })

    return jsonify({'reports': enriched_reports, 'count': len(enriched_reports)}), 200

@reports_bp.route('/<report_id>', methods=['GET'])
@login_required
def get_report_detail(current_user, report_id):
    """Retrieves full details for a single defect report."""
    report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    if not report:
        return jsonify({'error': 'Report not found.'}), 404

    # Authorization: citizen may only access their own report
    user_role = current_user.get('role', 'citizen')
    user_id = str(current_user.get('_id') or current_user.get('user_id'))
    if user_role == 'citizen' and str(report.get('user_id')) != user_id:
        return jsonify({'error': 'Access denied to this report.'}), 403

    image = db_service.find_one('submitted_images', {'report_id': report_id})
    assessment = None
    if image:
        assessment = db_service.find_one('ai_assessments', {'image_id': image['_id']})

    asset = db_service.find_one('infrastructure_assets', {'_id': report.get('asset_id')})
    review = None
    if assessment:
        review = db_service.find_one('professional_reviews', {'assessment_id': assessment['_id']})

    return jsonify({
        'report': report,
        'asset': asset,
        'image': {
            'image_id': image['_id'],
            'url': f"/api/reports/images/{image['image_path']}",
            'filename': image['image_path']
        } if image else None,
        'assessment': assessment,
        'review': review
    }), 200

@reports_bp.route('/images/<filename>', methods=['GET'])
def serve_image(filename):
    """Serves uploaded defect photographs for display and bounding-box rendering."""
    upload_folder = current_app.config['UPLOAD_FOLDER']
    file_path = os.path.join(upload_folder, filename)
    if not os.path.exists(file_path):
        from PIL import Image, ImageDraw
        os.makedirs(upload_folder, exist_ok=True)
        img = Image.new('RGB', (800, 600), color=(30, 36, 48))
        d = ImageDraw.Draw(img)
        d.text((260, 280), f"Civil Infrastructure Image\n{filename}", fill=(200, 200, 200))
        img.save(file_path)

    return send_from_directory(upload_folder, filename)
