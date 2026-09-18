import os
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from werkzeug.utils import secure_filename
from ..models.report import InfrastructureReport, SubmittedImage
from ..models.assessment import AIAssessment
from ..models.asset import InfrastructureAsset
from ..services.db import db_service
from ..services.ai_service import ai_model
from ..utils.auth_helpers import get_current_user
from ..utils.file_helpers import allowed_file, save_uploaded_image

reports_bp = Blueprint('reports', __name__, url_prefix='/api/reports')

@reports_bp.route('', methods=['POST'])
def submit_report():
    """
    FR-02 & FR-03: Image upload, automated SSD-MobileNetV2 defect detection,
    FR-04 relative severity evaluation, and database record persistence.
    """
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided in upload.'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected image file.'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file format. Supported: PNG, JPG, JPEG, WEBP.'}), 400

    # Retrieve form metadata
    location = request.form.get('location', '').strip() or 'Uhuru Highway / Nyayo Corridor'
    asset_type = request.form.get('asset_type', 'Road / Pavement').strip()
    description = request.form.get('description', '').strip()
    user = get_current_user()
    user_id = user.get('_id') if user else 'anonymous_reporter'

    # Save uploaded image
    unique_filename, dest_path, orig_name, file_size = save_uploaded_image(file)

    # Invoke Computer Vision SSD-MobileNetV2 inference
    try:
        detection_result = ai_model.detect_defects(dest_path)
    except Exception as e:
        return jsonify({'error': f'Defect analysis failed: {str(e)}'}), 500

    # Link or associate with an Infrastructure Asset
    matched_asset = db_service.find_one('infrastructure_assets', {'location': location})
    if not matched_asset:
        # Create asset entry
        asset_obj = InfrastructureAsset(
            asset_type=asset_type,
            location=location,
            description=f"Monitored asset near {location}",
            current_condition='Critical' if detection_result['relative_severity'] == 'Critical' else 'Poor'
        )
        asset_id = db_service.insert('infrastructure_assets', asset_obj.to_dict())
    else:
        asset_id = matched_asset['_id']

    # Create InfrastructureReport
    report = InfrastructureReport(
        user_id=user_id,
        asset_id=asset_id,
        description=description or f"Reported {detection_result['defect_class']} distress.",
        status=InfrastructureReport.STATUS_PENDING,
        metadata={
            'location_name': location,
            'asset_type': asset_type,
            'priority': detection_result['relative_severity']
        }
    )
    report_id = db_service.insert('infrastructure_reports', report.to_dict())
    report.report_id = report_id

    # Create SubmittedImage
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

    # Return full assessment payload matching Figure 4.6 Wireframe
    return jsonify({
        'message': 'Report and defect analysis submitted successfully.',
        'report_id': report_id,
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
            'action_index': detection_result['action_index'],
            'sla_hours': detection_result['sla_hours'],
            'detections': detection_result['detections']
        }
    }), 201

@reports_bp.route('', methods=['GET'])
def list_reports():
    """
    FR-05 & FR-07: List infrastructure reports with optional filters
    (severity, status, asset_type).
    """
    severity_filter = request.args.get('severity')
    status_filter = request.args.get('status')
    
    reports = db_service.find('infrastructure_reports', sort_key='date_submitted', reverse=True)
    
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

        # Fetch asset info
        asset = db_service.find_one('infrastructure_assets', {'_id': rep.get('asset_id')})

        # Fetch review if completed
        review = None
        if assessment:
            review = db_service.find_one('professional_reviews', {'assessment_id': assessment['_id']})

        enriched_item = {
            'report_id': report_id,
            'user_id': rep.get('user_id'),
            'description': rep.get('description'),
            'status': rep.get('status'),
            'date_submitted': rep.get('date_submitted'),
            'metadata': rep.get('metadata', {}),
            'asset': asset or {
                'location': rep.get('metadata', {}).get('location_name', 'General Infrastructure'),
                'asset_type': rep.get('metadata', {}).get('asset_type', 'Road / Pavement')
            },
            'image': image_info,
            'assessment': assessment,
            'review': review
        }

        # Apply filtering
        if severity_filter and assessment and assessment.get('relative_severity') != severity_filter:
            continue
        if status_filter and rep.get('status') != status_filter:
            continue

        enriched_reports.append(enriched_item)

    return jsonify({'reports': enriched_reports, 'count': len(enriched_reports)})

@reports_bp.route('/<report_id>', methods=['GET'])
def get_report_detail(report_id):
    """Retrieves full details for a single defect report."""
    report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    if not report:
        return jsonify({'error': 'Report not found.'}), 404

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
    })

@reports_bp.route('/my', methods=['GET'])
def get_my_reports():
    """FR-08: Citizen Tracking Module - retrieves submissions by the active user."""
    user = get_current_user()
    user_id = user.get('_id') if user else 'usr_cit_01'
    
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
    return jsonify({'my_reports': results, 'count': len(results)})

@reports_bp.route('/images/<filename>', methods=['GET'])
def serve_image(filename):
    """Serves uploaded inspection photographs for canvas bounding box rendering."""
    upload_folder = current_app.config['UPLOAD_FOLDER']
    if not os.path.exists(os.path.join(upload_folder, filename)):
        # Fallback to demo placeholder if custom file not physically on disk
        from PIL import Image, ImageDraw
        os.makedirs(upload_folder, exist_ok=True)
        demo_path = os.path.join(upload_folder, filename)
        img = Image.new('RGB', (800, 600), color=(40, 44, 52))
        d = ImageDraw.Draw(img)
        d.text((250, 280), f"InfraVision Inspection Image\n{filename}", fill=(220, 220, 220))
        img.save(demo_path)

    return send_from_directory(upload_folder, filename)
