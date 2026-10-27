import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from ..models.report import InfrastructureReport, SubmittedImage
from ..models.assessment import AIAssessment
from ..models.asset import InfrastructureAsset
from ..services.database import db_service
from ..services.inference import inference_service
from ..services.validation import validation_service
from ..utils.auth_helpers import get_current_user, login_required
from ..utils.file_helpers import allowed_file, save_uploaded_image

reports_bp = Blueprint('reports', __name__, url_prefix='/api/reports')


@reports_bp.route('', methods=['POST'])
@login_required
def submit_report(current_user):
    """
    FR-02 & FR-03: Defect report submission workflow.
    Validates uploaded photograph, executes SSD-MobileNetV2 defect detection,
    performs backend integrity validation (flagging unusual combinations like Building + Pothole),
    evaluates FR-04 relative visual severity, and persists records into MongoDB.
    """
    uploaded_files = []
    if 'images' in request.files:
        uploaded_files = request.files.getlist('images')
    elif 'images[]' in request.files:
        uploaded_files = request.files.getlist('images[]')
    elif 'image' in request.files:
        uploaded_files = request.files.getlist('image')

    uploaded_files = [f for f in uploaded_files if f and f.filename != '']

    if not uploaded_files:
        return jsonify({'error': 'At least one infrastructure photograph is required.'}), 400

    if len(uploaded_files) > 3:
        return jsonify({'error': 'A maximum of 3 photographs may be submitted per defect report.'}), 400

    for f in uploaded_files:
        if not allowed_file(f.filename):
            return jsonify({'error': f'Invalid file format for {f.filename}. Permitted formats: PNG, JPG, JPEG, WEBP.'}), 400

    # Retrieve form metadata
    location = request.form.get('location', '').strip()
    asset_type = request.form.get('asset_type', 'Road / Pavement').strip()
    description = request.form.get('description', '').strip()
    
    # Retrieve optional geographic coordinates
    raw_lat = request.form.get('latitude')
    raw_lng = request.form.get('longitude')
    latitude = None
    longitude = None
    try:
        if raw_lat is not None and str(raw_lat).strip() != '':
            latitude = float(raw_lat)
        if raw_lng is not None and str(raw_lng).strip() != '':
            longitude = float(raw_lng)
    except (ValueError, TypeError):
        latitude = None
        longitude = None

    # Input integrity validation
    inputs_valid, input_errors = validation_service.validate_submission_inputs(asset_type, location, description)
    if not inputs_valid:
        return jsonify({'error': ' ; '.join(input_errors)}), 400

    user_id = str(current_user.get('_id') or current_user.get('user_id'))

    # Run independent inference on each submitted photograph
    processed_images = []
    for file in uploaded_files:
        try:
            unique_filename, dest_path, orig_name, file_size = save_uploaded_image(file)
        except ValueError as val_err:
            return jsonify({'error': str(val_err)}), 400
        except Exception as e:
            return jsonify({'error': f'Failed to process image upload: {str(e)}'}), 500

        try:
            det_res = inference_service.detect_defects(dest_path)
        except Exception as e:
            current_app.logger.error(f"[Inference Error] Failed executing SavedModel inference on {unique_filename}: {e}")
            return jsonify({'error': 'Automated defect analysis service failed. Please contact system administrator.'}), 500

        processed_images.append({
            'unique_filename': unique_filename,
            'dest_path': dest_path,
            'orig_name': orig_name,
            'file_size': file_size,
            'detection': det_res
        })

    # Multi-Image Aggregation:
    # 1. Detected defect classes union across all images
    aggregated_classes_set = set()
    all_detections_flat = []

    for item in processed_images:
        det = item['detection']
        classes = det.get('detected_classes') or []
        primary = det.get('defect_class')
        if primary and primary != 'None Detected':
            aggregated_classes_set.add(primary)
        for c in classes:
            if c and c != 'None Detected':
                aggregated_classes_set.add(c)
        all_detections_flat.extend(det.get('detections', []))

    if not aggregated_classes_set:
        report_detected_classes = ['None Detected']
        primary_defect_class = 'None Detected'
    else:
        report_detected_classes = sorted(list(aggregated_classes_set))
        primary_defect_class = report_detected_classes[0]

    # 2. Overall Visual Severity: highest credible Visual Severity observed across submitted images
    # Critical (3) > Medium / Moderate (2) > Low (1)
    SEV_WEIGHTS = {'critical': 3, 'moderate': 2, 'medium': 2, 'low': 1}
    highest_sev_rank = 1
    overall_visual_severity = 'Low'

    for item in processed_images:
        s = item['detection'].get('relative_severity', 'Low')
        rank = SEV_WEIGHTS.get(s.lower(), 1)
        if rank > highest_sev_rank:
            highest_sev_rank = rank
            overall_visual_severity = 'Critical' if rank == 3 else ('Medium' if rank == 2 else 'Low')

    # 3. Confidence: highest confidence score across detections
    highest_confidence = 0.0
    for item in processed_images:
        c = float(item['detection'].get('confidence_score') or 0.0)
        if c > highest_confidence:
            highest_confidence = c

    # Associate with Infrastructure Asset record
    matched_asset = db_service.find_one('infrastructure_assets', {'location': location})
    if not matched_asset:
        asset_obj = InfrastructureAsset(
            asset_type=asset_type,
            location=location,
            description=f"Monitored asset at {location}",
            current_condition='Critical' if overall_visual_severity == 'Critical' else 'Poor'
        )
        asset_id = db_service.insert('infrastructure_assets', asset_obj.to_dict())
    else:
        asset_id = matched_asset['_id']
        if latitude is None and 'coordinates' in matched_asset:
            latitude = matched_asset['coordinates'].get('lat')
            longitude = matched_asset['coordinates'].get('lng')

    # Location-based priority clustering signal (~50m radius)
    nearby_metrics = validation_service.calculate_location_proximity_metrics(
        latitude, longitude, current_user_id=user_id, radius_meters=50.0
    )

    aggregated_detection_summary = {
        'defect_class': primary_defect_class,
        'detected_classes': report_detected_classes,
        'relative_severity': overall_visual_severity,
        'confidence_score': highest_confidence,
        'detections': all_detections_flat,
        'model_name': processed_images[0]['detection'].get('model_name', 'SSD-MobileNetV2'),
        'model_version': processed_images[0]['detection'].get('model_version'),
        'image_dimensions': processed_images[0]['detection'].get('image_dimensions', {'width': 300, 'height': 300})
    }

    # Backend domain integrity validation across combined defect findings
    validation_result = validation_service.validate_report(
        asset_type, location, aggregated_detection_summary, nearby_metrics=nearby_metrics
    )

    initial_status = InfrastructureReport.STATUS_RECEIVED

    # Persist report in MongoDB
    report = InfrastructureReport(
        user_id=user_id,
        asset_id=asset_id,
        description=description or f"Observed {primary_defect_class} defect on {asset_type}.",
        status=initial_status,
        latitude=latitude,
        longitude=longitude,
        metadata={
            'submitted_by_id': str(user_id),
            'submitted_by_name': current_user.get('name', 'Reporter'),
            'submitted_by_role': current_user.get('role', 'citizen'),
            'location_name': location,
            'asset_type': asset_type,
            'defect_class': primary_defect_class,
            'detected_classes': report_detected_classes,
            'confidence': highest_confidence,
            'relative_severity': overall_visual_severity,
            'image_count': len(processed_images),
            'is_unusual': validation_result['is_unusual'],
            'requires_engineer_review': validation_result.get('requires_engineer_review', True),
            'validation_status': validation_result.get('validation_status', 'valid'),
            'validation_message': validation_result.get('validation_message', ''),
            'flags': validation_result['flags'],
            'flag_reasons': validation_result['flag_reasons'],
            'advisory_notes': validation_result['advisory_notes'],
            'priority': validation_result['priority'],
            'nearby_report_count': validation_result.get('nearby_report_count', 0),
            'nearby_unresolved_count': validation_result.get('nearby_unresolved_count', 0),
            'is_location_cluster': validation_result.get('is_location_cluster', False),
            'location_priority_signal': 'Cluster Elevated' if validation_result.get('is_location_cluster') else 'Standard',
            'model_version': aggregated_detection_summary.get('model_version'),
            'latitude': latitude,
            'longitude': longitude,
            'status_history': [
                {
                    'status': initial_status,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'updated_by': 'system',
                    'note': f"Report received with {len(processed_images)} photo evidence item(s) and registered in defect monitoring pipeline."
                }
            ]
        }
    )
    report_id = db_service.insert('infrastructure_reports', report.to_dict())
    report.report_id = report_id

    # Persist individual SubmittedImage and AIAssessment records
    image_records = []
    assessment_records = []

    for item in processed_images:
        det = item['detection']
        sub_img = SubmittedImage(
            report_id=report_id,
            image_path=item['unique_filename'],
            original_filename=item['orig_name'],
            file_size=item['file_size'],
            dimensions=det.get('image_dimensions', {'width': 300, 'height': 300})
        )
        img_id = db_service.insert('submitted_images', sub_img.to_dict())
        sub_img.image_id = img_id

        ai_ass = AIAssessment(
            image_id=img_id,
            defect_class=det.get('defect_class', 'None Detected'),
            confidence_score=det.get('confidence_score', 0.0),
            bounding_box=det.get('bounding_box', [0.0, 0.0, 0.0, 0.0]),
            relative_severity=det.get('relative_severity', 'Low'),
            detections=det.get('detections', []),
            model_name=det.get('model_name', 'SSD-MobileNetV2'),
            model_version=det.get('model_version'),
            class_id=det.get('class_id'),
            relative_area=det.get('relative_area', 0.0),
            area_percentage=det.get('area_percentage', 0.0),
            bounding_box_pixels=det.get('bounding_box_pixels'),
            validation_status='valid',
            validation_message=''
        )
        ass_id = db_service.insert('ai_assessments', ai_ass.to_dict())
        ai_ass.assessment_id = ass_id

        image_records.append({
            'image_id': img_id,
            'filename': item['unique_filename'],
            'url': f"/api/reports/images/{item['unique_filename']}",
            'original_filename': item['orig_name'],
            'dimensions': det.get('image_dimensions', {'width': 300, 'height': 300})
        })
        assessment_records.append({
            **ai_ass.to_dict(),
            'image_url': f"/api/reports/images/{item['unique_filename']}"
        })

    # Human-readable response message
    if validation_result['is_unusual']:
        response_message = (
            'Report recorded. Note: An unusual defect-infrastructure combination was detected and flagged for certified engineer review.'
        )
    elif not all_detections_flat:
        response_message = (
            'Report recorded. No structural defects were detected exceeding the confidence threshold.'
        )
    else:
        response_message = f"Infrastructure defect report with {len(processed_images)} photograph(s) submitted and analyzed successfully."

    primary_image = image_records[0]
    primary_assessment = assessment_records[0]

    return jsonify({
        'message': response_message,
        'report_id': report_id,
        'status': report.status,
        'report': report.to_dict(),
        'image': primary_image,
        'images': image_records,
        'ai_assessment': primary_assessment,
        'ai_assessments': assessment_records,
        'detected_classes': report_detected_classes,
        'overall_visual_severity': overall_visual_severity,
        'validation': validation_result
    }), 201


@reports_bp.route('/analyze', methods=['POST'])
@login_required
def analyze_image_preview(current_user):
    """
    Dedicated AI image analysis endpoint.
    Executes SSD-MobileNetV2 SavedModel inference and infrastructure pairing validation
    without creating persistent report records.
    """
    if 'image' not in request.files:
        return jsonify({'error': 'An infrastructure photograph is required.'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No image file selected.'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file format. Permitted formats: PNG, JPG, JPEG, WEBP.'}), 400

    asset_type = request.form.get('asset_type', 'Road / Pavement').strip()
    location = request.form.get('location', '').strip()

    try:
        unique_filename, dest_path, orig_name, file_size = save_uploaded_image(file)
    except ValueError as val_err:
        return jsonify({'error': str(val_err)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to process image upload: {str(e)}'}), 500

    try:
        detection_result = inference_service.detect_defects(dest_path)
    except Exception as e:
        current_app.logger.error(f"[Inference Error] Failed executing SavedModel inference: {e}")
        return jsonify({'error': 'Automated defect analysis service failed. Please contact system administrator.'}), 500

    validation_result = validation_service.validate_report(asset_type, location, detection_result)

    return jsonify({
        'image': {
            'filename': unique_filename,
            'url': f"/api/reports/images/{unique_filename}",
            'dimensions': detection_result['image_dimensions']
        },
        'ai_assessment': {
            'model_name': detection_result['model_name'],
            'model_version': detection_result['model_version'],
            'class_id': detection_result.get('class_id'),
            'class_name': detection_result.get('class_name'),
            'defect_class': detection_result['defect_class'],
            'confidence': detection_result['confidence'],
            'confidence_score': detection_result['confidence_score'],
            'confidence_percentage': round(detection_result['confidence_score'] * 100, 1),
            'relative_severity': detection_result['relative_severity'],
            'severity': detection_result['severity'],
            'relative_area': detection_result.get('relative_area', 0.0),
            'area_percentage': detection_result.get('area_percentage', 0.0),
            'bounding_box': detection_result['bounding_box'],
            'bounding_box_pixels': detection_result.get('bounding_box_pixels'),
            'detections': detection_result['detections'],
            'validation_status': validation_result['validation_status'],
            'validation_message': validation_result['validation_message'],
            'disclaimer': detection_result.get('disclaimer')
        },
        'validation': validation_result
    }), 200


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
    exclude_status = request.args.get('exclude_status')

    if status_filter:
        query['status'] = InfrastructureReport.normalize_lifecycle_status(status_filter)
    elif exclude_status:
        query['status'] = {'$ne': InfrastructureReport.normalize_lifecycle_status(exclude_status)}

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

    images = db_service.find('submitted_images', {'report_id': report_id})
    image_list = []
    assessment_list = []

    for img in images:
        ass = db_service.find_one('ai_assessments', {'image_id': img['_id']})
        if not ass and len(images) == 1:
            ass = db_service.find_one('ai_assessments', {'report_id': report_id})
        raw_path = img.get('image_path') or img.get('unique_filename') or img.get('filename') or ''
        clean_name = os.path.basename(raw_path.replace('\\', '/'))
        img_dict = {
            'image_id': img['_id'],
            'url': f"/api/reports/images/{clean_name}",
            'filename': clean_name,
            'original_filename': img.get('original_filename', ''),
            'file_size': img.get('file_size', 0),
            'dimensions': img.get('dimensions', {})
        }
        image_list.append(img_dict)
        assessment_list.append(ass if ass else {})

    primary_image = image_list[0] if image_list else None
    primary_assessment = assessment_list[0] if assessment_list else None

    # Legacy report compatibility: check if report or metadata references image directly
    meta = report.get('metadata') or {}
    if not primary_image:
        legacy_image_path = report.get('image_path') or meta.get('image_path')
        legacy_image_id = report.get('image_id') or meta.get('image_id')
        if legacy_image_id:
            legacy_img = db_service.find_one('submitted_images', {'_id': legacy_image_id})
            if legacy_img:
                primary_image = {
                    'image_id': legacy_img['_id'],
                    'url': f"/api/reports/images/{legacy_img['image_path']}",
                    'filename': legacy_img['image_path'],
                    'original_filename': legacy_img.get('original_filename', ''),
                    'file_size': legacy_img.get('file_size', 0),
                    'dimensions': legacy_img.get('dimensions', {})
                }
                image_list = [primary_image]
        elif legacy_image_path:
            primary_image = {
                'image_id': 'legacy',
                'url': f"/api/reports/images/{legacy_image_path}",
                'filename': legacy_image_path,
                'original_filename': legacy_image_path,
                'file_size': 0,
                'dimensions': {}
            }
            image_list = [primary_image]

    if not primary_assessment:
        primary_assessment = db_service.find_one('ai_assessments', {'report_id': report_id})
        if primary_assessment and not assessment_list:
            assessment_list = [primary_assessment]

    asset = db_service.find_one('infrastructure_assets', {'_id': report.get('asset_id')})
    review = None
    if primary_assessment:
        review = db_service.find_one('professional_reviews', {'assessment_id': primary_assessment['_id']})

    submitter_user = db_service.find_one('users', {'_id': report.get('user_id')})
    meta = report.get('metadata') or {}
    submitter_info = {
        'user_id': str(report.get('user_id', '')),
        'name': submitter_user.get('name') if submitter_user else (meta.get('submitted_by_name') or 'Field Reporter'),
        'role': submitter_user.get('role') if submitter_user else (meta.get('submitted_by_role') or 'citizen')
    }

    return jsonify({
        'report': report,
        'submitter': submitter_info,
        'asset': asset,
        'image': primary_image,
        'images': image_list,
        'assessment': primary_assessment,
        'assessments': assessment_list,
        'review': review
    }), 200


@reports_bp.route('/map/config', methods=['GET'])
def get_map_config():
    """Returns Infrastructure Map configuration including Nairobi center defaults and Leaflet provider."""
    return jsonify({
        'provider': 'leaflet',
        'tile_layer': 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        'attribution': '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
        'default_center': {
            'lat': -1.286389,
            'lng': 36.817223
        },
        'default_zoom': 12,
        'min_zoom': 5,
        'max_zoom': 19
    }), 200


@reports_bp.route('/map', methods=['GET'])
def get_map_reports():
    """
    FR-09 & Map View: Returns geographic infrastructure defect reports for Google Maps.
    - Accessible to both Citizens and Engineers.
    - Privacy protection: For public/citizen requests, strips out private reporter identities,
      emails, phone numbers, and internal user IDs.
    - Supports filtering by defect_class, status, severity, and asset_type.
    """
    user = get_current_user()
    is_privileged = user and user.get('role') in ['engineer', 'admin']

    severity_filter = request.args.get('severity')
    status_filter = request.args.get('status')
    defect_filter = request.args.get('defect_class')
    asset_filter = request.args.get('asset_type')

    query = {}
    if status_filter:
        query['status'] = InfrastructureReport.normalize_lifecycle_status(status_filter)

    reports = db_service.find('infrastructure_reports', query, sort_key='date_submitted', reverse=True)

    map_points = []
    for rep in reports:
        meta = rep.get('metadata', {})
        lat = rep.get('latitude') or meta.get('latitude')
        lng = rep.get('longitude') or meta.get('longitude')

        # Fallback to asset coordinates if report doesn't have explicit lat/lng
        if lat is None or lng is None:
            asset = db_service.find_one('infrastructure_assets', {'_id': rep.get('asset_id')})
            if asset and 'coordinates' in asset:
                lat = asset['coordinates'].get('lat')
                lng = asset['coordinates'].get('lng')

        # Skip points without valid coordinates
        if lat is None or lng is None:
            continue

        assessment = None
        image = db_service.find_one('submitted_images', {'report_id': rep['_id']})
        if image:
            assessment = db_service.find_one('ai_assessments', {'image_id': image['_id']})

        rel_sev = (assessment.get('relative_severity') if assessment else None) or meta.get('relative_severity', 'Low')
        defect_c = (assessment.get('defect_class') if assessment else None) or meta.get('defect_class', 'Crack')
        asset_t = meta.get('asset_type', 'Road / Pavement')

        # Apply optional filters
        if severity_filter and rel_sev.lower() != severity_filter.lower():
            continue
        if defect_filter and defect_c.lower() != defect_filter.lower():
            continue
        if asset_filter and asset_t.lower() != asset_filter.lower():
            continue

        point = {
            'report_id': rep['_id'],
            'latitude': float(lat),
            'longitude': float(lng),
            'location_name': meta.get('location_name', 'Monitored Infrastructure'),
            'asset_type': asset_t,
            'defect_class': defect_c,
            'detected_classes': meta.get('detected_classes', [defect_c]),
            'relative_severity': rel_sev,
            'status': InfrastructureReport.normalize_lifecycle_status(rep.get('status')),
            'date_submitted': rep.get('date_submitted'),
            'image_url': f"/api/reports/images/{image['image_path']}" if image else None
        }

        # Privacy Protection: Privileged roles get extra audit data; public gets clean defect record
        if is_privileged:
            point['validation_status'] = meta.get('validation_status', 'valid')
            point['requires_engineer_review'] = meta.get('requires_engineer_review', False)
            point['priority'] = meta.get('priority', 'Standard')

        map_points.append(point)

    # Calculate location-based density for each map point (~50m radius)
    for i, p in enumerate(map_points):
        nearby_cnt = 0
        p_lat = p['latitude']
        p_lng = p['longitude']
        for j, other in enumerate(map_points):
            if i == j:
                continue
            dist = validation_service.haversine_distance_meters(p_lat, p_lng, other['latitude'], other['longitude'])
            if dist <= 50.0:
                nearby_cnt += 1
        p['nearby_report_count'] = nearby_cnt

    return jsonify({
        'points': map_points,
        'count': len(map_points),
        'mode': 'privileged' if is_privileged else 'public'
    }), 200


@reports_bp.route('/<report_id>/status', methods=['PUT'])
@login_required
def update_report_status(current_user, report_id):
    """
    FR-06 & Lifecycle Management: Allows authorized Civil Engineers and Administrators
    to transition reports through the canonical lifecycle:
    Received -> Under Review -> Verified -> Resolved
    """
    user_role = current_user.get('role', 'citizen')
    if user_role not in ['engineer', 'admin']:
        return jsonify({'error': 'Only certified civil engineers and administrators may update report lifecycle status.'}), 403

    report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    if not report:
        return jsonify({'error': 'Report not found.'}), 404

    data = request.get_json() or {}
    new_raw_status = data.get('status')
    notes = data.get('notes', '').strip()

    if not new_raw_status:
        return jsonify({'error': 'Target status is required.'}), 400

    target_status = InfrastructureReport.normalize_lifecycle_status(new_raw_status)
    current_status = InfrastructureReport.normalize_lifecycle_status(report.get('status'))

    if not InfrastructureReport.can_transition(current_status, target_status):
        return jsonify({
            'error': f"Invalid status transition from '{current_status}' to '{target_status}'. Permitted forward lifecycle: Received -> Under Review -> Verified -> Resolved."
        }), 400

    now_iso = datetime.utcnow().isoformat()
    meta = report.get('metadata', {})
    history = meta.get('status_history', [])
    history.append({
        'status': target_status,
        'timestamp': now_iso,
        'updated_by': current_user.get('name', 'Certified Engineer'),
        'user_id': str(current_user.get('_id') or current_user.get('user_id')),
        'notes': notes or f"Status transitioned to {target_status}."
    })
    meta['status_history'] = history
    if target_status == InfrastructureReport.STATUS_VERIFIED:
        meta['requires_engineer_review'] = False

    db_service.update_one('infrastructure_reports', {'_id': report_id}, {
        'status': target_status,
        'metadata': meta,
        'last_updated_at': now_iso
    })

    updated_report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    return jsonify({
        'message': f"Report status successfully updated to '{target_status}'.",
        'report': updated_report
    }), 200


@reports_bp.route('/images/<path:filename>', methods=['GET'])
def serve_image(filename):
    """
    Serves uploaded defect photographs for display and bounding-box rendering.
    Supports safe historical path resolution, normalizes legacy directory prefixes,
    and strictly rejects directory traversal attempts.
    """
    # 1. Path Traversal & Security Validation
    if not filename or '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        return jsonify({'error': 'Invalid evidence image path.'}), 400

    # 2. Normalize Legacy Historical Path Prefixes (e.g. backend/uploads/ or uploads/)
    clean_filename = filename.replace('\\', '/')
    for prefix in ('backend/uploads/', 'uploads/'):
        if clean_filename.lower().startswith(prefix):
            clean_filename = clean_filename[len(prefix):]
    
    clean_filename = os.path.basename(clean_filename)
    if not clean_filename:
        return jsonify({'error': 'Invalid evidence image filename.'}), 400

    # 3. Canonical Upload Directory
    canonical_upload_dir = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
    file_path = os.path.join(canonical_upload_dir, clean_filename)

    # 4. Resolve in canonical directory, or fallback to root workspace uploads directory
    if os.path.exists(file_path):
        return send_from_directory(canonical_upload_dir, clean_filename)

    root_uploads_dir = os.path.abspath(os.path.join(canonical_upload_dir, '..', '..', 'uploads'))
    fallback_path = os.path.join(root_uploads_dir, clean_filename)
    if os.path.exists(fallback_path):
        return send_from_directory(root_uploads_dir, clean_filename)

    return jsonify({'error': 'Evidence image unavailable in storage.'}), 404
