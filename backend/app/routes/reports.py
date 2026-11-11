import os
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app, send_from_directory, make_response
from ..models.report import InfrastructureReport, SubmittedImage
from ..models.assessment import AIAssessment
from ..models.asset import InfrastructureAsset
from ..services.database import db_service
from ..services.inference import inference_service
from ..services.severity import severity_service
from ..services.validation import validation_service
from ..services.storage import storage_service
from ..utils.auth_helpers import get_current_user, login_required
from ..utils.file_helpers import allowed_file, save_uploaded_image
from .reviews import get_default_notebook_template

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

    # Building-specific storeys / floors validation
    building_floors = None
    building_floors_mode = None
    if 'building' in asset_type.lower():
        raw_floors_mode = request.form.get('building_floors_mode', '').strip()
        raw_floors = request.form.get('building_floors')
        if raw_floors_mode == 'not_sure':
            building_floors_mode = 'not_sure'
            building_floors = None
        elif raw_floors is not None and str(raw_floors).strip() != '':
            try:
                floors_val = int(raw_floors)
                if floors_val <= 0:
                    return jsonify({'error': 'Number of building floors must be a positive whole number greater than 0.'}), 400
                building_floors = floors_val
                building_floors_mode = 'known'
            except (ValueError, TypeError):
                return jsonify({'error': 'Number of building floors must be a valid positive integer.'}), 400
        elif raw_floors_mode:
            building_floors_mode = raw_floors_mode
    
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

    # Multi-Image Mode: 'same_defect' (default) vs 'multi_defect' (batch submission)
    multi_image_mode = request.form.get('multi_image_mode')
    if len(uploaded_files) > 1 and not multi_image_mode:
        multi_image_mode = 'same_defect'

    current_year = datetime.now(timezone.utc).year

    # ─────────────────────────────────────────────────────────────
    # CASE A: DIFFERENT DEFECTS / OBSERVATIONS MODE (BATCH SUBMISSION)
    # ─────────────────────────────────────────────────────────────
    if multi_image_mode == 'multi_defect' and len(uploaded_files) > 1:
        batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        batch_results = []

        for idx, file in enumerate(uploaded_files):
            try:
                unique_filename, dest_path, orig_name, file_size = save_uploaded_image(file)
            except ValueError as val_err:
                return jsonify({'error': str(val_err)}), 400
            except Exception as e:
                return jsonify({'error': f'Failed to process image upload: {str(e)}'}), 500

            # Execute single-image SSD-MobileNetV2 inference
            try:
                det_res = inference_service.detect_defects(dest_path)
            except Exception as e:
                current_app.logger.error(f"[Inference Error] Failed executing SavedModel inference on {unique_filename}: {e}")
                return jsonify({'error': 'Automated defect analysis service failed. Please contact system administrator.'}), 500

            # Extract observation-specific location & optional note
            obs_location = (request.form.get(f'location_{idx}') or request.form.get(f'obs_location_{idx}') or location).strip()
            obs_notes = (request.form.get(f'note_{idx}') or request.form.get(f'description_{idx}') or request.form.get(f'obs_notes_{idx}') or description).strip()

            raw_obs_lat = request.form.get(f'latitude_{idx}') or request.form.get(f'obs_lat_{idx}') or raw_lat
            raw_obs_lng = request.form.get(f'longitude_{idx}') or request.form.get(f'obs_lng_{idx}') or raw_lng
            obs_lat, obs_lng = None, None
            try:
                if raw_obs_lat is not None and str(raw_obs_lat).strip() != '':
                    obs_lat = float(raw_obs_lat)
                if raw_obs_lng is not None and str(raw_obs_lng).strip() != '':
                    obs_lng = float(raw_obs_lng)
            except (ValueError, TypeError):
                obs_lat, obs_lng = None, None

            # Associate with Infrastructure Asset record
            matched_asset = db_service.find_one('infrastructure_assets', {'location': obs_location})
            if not matched_asset:
                asset_obj = InfrastructureAsset(
                    asset_type=asset_type,
                    location=obs_location,
                    description=f"Monitored asset at {obs_location}",
                    current_condition='Critical' if det_res.get('relative_severity') == 'Critical' else 'Poor'
                )
                obs_asset_id = db_service.insert('infrastructure_assets', asset_obj.to_dict())
            else:
                obs_asset_id = matched_asset['_id']
                if obs_lat is None and 'coordinates' in matched_asset:
                    obs_lat = matched_asset['coordinates'].get('lat')
                    obs_lng = matched_asset['coordinates'].get('lng')

            obs_defect_class = det_res.get('defect_class', 'None Detected')
            obs_severity = det_res.get('relative_severity', 'Low')
            obs_confidence = float(det_res.get('confidence_score') or 0.0)
            obs_rvsi = float(det_res.get('rvsi_score', 0.0))

            # Validation
            obs_validation = validation_service.validate_report(
                asset_type, obs_location, det_res
            )

            # Persist independent report record
            obs_report = InfrastructureReport(
                user_id=user_id,
                asset_id=obs_asset_id,
                description=obs_notes or f"Observed {obs_defect_class} defect on {asset_type}.",
                status=InfrastructureReport.STATUS_RECEIVED,
                latitude=obs_lat,
                longitude=obs_lng,
                metadata={
                    'submitted_by_id': str(user_id),
                    'submitted_by_name': current_user.get('name', 'Reporter'),
                    'submitted_by_role': current_user.get('role', 'citizen'),
                    'location_name': obs_location,
                    'asset_type': asset_type,
                    'defect_class': obs_defect_class,
                    'detected_classes': det_res.get('detected_classes', [obs_defect_class]),
                    'confidence': obs_confidence,
                    'relative_severity': obs_severity,
                    'severity': obs_severity,
                    'report_rvsi': obs_rvsi,
                    'rvsi_score': obs_rvsi,
                    'image_rvsi_scores': [obs_rvsi],
                    'aggregation_method': 'single_image',
                    'aggregation_version': severity_service.AGGREGATION_VERSION,
                    'rvsi_method': det_res.get('rvsi_method', severity_service.RVSI_METHOD_NAME),
                    'rvsi_version': det_res.get('rvsi_version', severity_service.RVSI_VERSION),
                    'severity_threshold_source': det_res.get('severity_threshold_source', severity_service.DEFAULT_RVSI_THRESHOLD_SOURCE),
                    'postprocessing_version': det_res.get('postprocessing_version', severity_service.POSTPROCESSING_VERSION),
                    'raw_detection_count': det_res.get('raw_detection_count', len(det_res.get('detections', []))),
                    'cleaned_detection_count': det_res.get('cleaned_detection_count', len(det_res.get('detections', []))),
                    'image_count': 1,
                    'multi_image_mode': 'multi_defect',
                    'submission_batch_id': batch_id,
                    'batch_index': idx + 1,
                    'batch_total': len(uploaded_files),
                    'is_unusual': obs_validation['is_unusual'],
                    'requires_engineer_review': obs_validation.get('requires_engineer_review', True),
                    'validation_status': obs_validation.get('validation_status', 'valid'),
                    'validation_message': obs_validation.get('validation_message', ''),
                    'flags': obs_validation['flags'],
                    'flag_reasons': obs_validation['flag_reasons'],
                    'advisory_notes': obs_validation['advisory_notes'],
                    'priority': obs_validation['priority'],
                    'building_floors': building_floors,
                    'building_floors_mode': building_floors_mode,
                    'latitude': obs_lat,
                    'longitude': obs_lng,
                    'status_history': [
                        {
                            'status': InfrastructureReport.STATUS_RECEIVED,
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'updated_by': 'system',
                            'note': f"Observation #{idx + 1} of batch {batch_id} registered into defect monitoring pipeline."
                        }
                    ]
                }
            )
            obs_rep_id = db_service.insert('infrastructure_reports', obs_report.to_dict())
            obs_report.report_id = obs_rep_id

            short_ref = f"REP-{current_year}-{str(obs_rep_id)[-4:].upper()}"
            obs_report.metadata['display_id'] = short_ref
            db_service.update_one('infrastructure_reports', {'_id': obs_rep_id}, {'metadata.display_id': short_ref, 'display_id': short_ref})

            # Save SubmittedImage and AIAssessment
            sub_img = SubmittedImage(
                report_id=obs_rep_id,
                image_path=unique_filename,
                original_filename=orig_name,
                file_size=file_size,
                dimensions=det_res.get('image_dimensions', {'width': 300, 'height': 300})
            )
            img_id = db_service.insert('submitted_images', sub_img.to_dict())

            ai_ass = AIAssessment(
                image_id=img_id,
                defect_class=obs_defect_class,
                confidence_score=obs_confidence,
                bounding_box=det_res.get('bounding_box', [0.0, 0.0, 0.0, 0.0]),
                relative_severity=obs_severity,
                detections=det_res.get('detections', []),
                model_name=det_res.get('model_name', 'SSD-MobileNetV2'),
                model_version=det_res.get('model_version'),
                class_id=det_res.get('class_id'),
                relative_area=det_res.get('relative_area', 0.0),
                area_percentage=det_res.get('area_percentage', 0.0),
                bounding_box_pixels=det_res.get('bounding_box_pixels'),
                rvsi_score=obs_rvsi,
                rvsi=det_res.get('rvsi', {}),
                rvsi_method=det_res.get('rvsi_method', severity_service.RVSI_METHOD_NAME),
                rvsi_version=det_res.get('rvsi_version', severity_service.RVSI_VERSION),
                postprocessing_version=det_res.get('postprocessing_version', severity_service.POSTPROCESSING_VERSION),
                validation_status='valid',
                validation_message=''
            )
            ass_id = db_service.insert('ai_assessments', ai_ass.to_dict())

            batch_results.append({
                'report_id': obs_rep_id,
                'display_id': short_ref,
                'observation_index': idx + 1,
                'location': obs_location,
                'defect_class': obs_defect_class,
                'relative_severity': obs_severity,
                'confidence': obs_confidence,
                'image_url': f"/api/reports/images/{unique_filename}",
                'report': obs_report.to_dict(),
                'ai_assessment': ai_ass.to_dict()
            })

        batch_resp = make_response(jsonify({
            'mode': 'batch',
            'submission_batch_id': batch_id,
            'message': f"{len(batch_results)} infrastructure observations submitted successfully.",
            'total_submitted': len(batch_results),
            'observations': batch_results,
            'reports': batch_results
        }), 201)
        batch_resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return batch_resp

    # ─────────────────────────────────────────────────────────────
    # CASE B: SAME-DEFECT MULTI-VIEW SUBMISSION (OR SINGLE IMAGE)
    # ─────────────────────────────────────────────────────────────
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

    # Multi-Image Evidence Aggregation (over independent single-image SSD-MobileNetV2 inferences):
    # 1. Detected defect classes union across all images (after model confidence filtering & duplicate suppression)
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

    # 2. Overall Visual Severity & Multi-Image RVSI Evidence Aggregation:
    # Single-image: report_rvsi = image_rvsi
    # Multi-image (>= 2 images): report_rvsi = 0.70 * max(image_rvsi_scores) + 0.30 * mean(image_rvsi_scores)
    image_rvsi_scores = [float(item['detection'].get('rvsi_score', 0.0)) for item in processed_images]
    report_rvsi_res = severity_service.calculate_report_rvsi(image_rvsi_scores)
    report_rvsi = report_rvsi_res['report_rvsi']
    overall_visual_severity = report_rvsi_res['relative_severity']

    # 3. Confidence: highest confidence score across detections
    highest_confidence = 0.0
    for item in processed_images:
        c = float(item['detection'].get('confidence_score') or 0.0)
        if c > highest_confidence:
            highest_confidence = c

    # 4. Construct Transparent Combined Multi-View Assessment
    class_assessments = []
    for cls in report_detected_classes:
        if cls == 'None Detected':
            continue
        detected_in_views = 0
        strongest_conf = 0.0
        strongest_img_idx = 1
        strongest_img_fn = ''

        for v_idx, item in enumerate(processed_images):
            det = item['detection']
            item_classes = det.get('detected_classes') or []
            item_primary = det.get('defect_class')
            item_dets = det.get('detections') or []

            has_class = (
                item_primary == cls or
                cls in item_classes or
                any(d.get('class_name') == cls or d.get('defect_class') == cls for d in item_dets)
            )
            if has_class:
                detected_in_views += 1

            for d in item_dets:
                if d.get('class_name') == cls or d.get('defect_class') == cls:
                    c_val = float(d.get('confidence') or d.get('confidence_score') or 0.0)
                    if c_val > strongest_conf:
                        strongest_conf = c_val
                        strongest_img_idx = v_idx + 1
                        strongest_img_fn = item['unique_filename']

        if strongest_conf == 0.0:
            for v_idx, item in enumerate(processed_images):
                if item['detection'].get('defect_class') == cls:
                    c_val = float(item['detection'].get('confidence_score') or 0.0)
                    if c_val > strongest_conf:
                        strongest_conf = c_val
                        strongest_img_idx = v_idx + 1
                        strongest_img_fn = item['unique_filename']

        class_assessments.append({
            'defect_class': cls,
            'views_detected': detected_in_views,
            'total_views': len(processed_images),
            'view_support': f"{detected_in_views}/{len(processed_images)}",
            'view_support_text': f"Detected in {detected_in_views} of {len(processed_images)} views",
            'strongest_confidence': round(strongest_conf, 4),
            'strongest_confidence_pct': round(strongest_conf * 100, 1),
            'strongest_image_index': strongest_img_idx,
            'strongest_image_filename': strongest_img_fn
        })

    combined_multi_view_assessment = {
        'label': 'Combined Multi-View Assessment',
        'architecture_note': 'Application-level evidence aggregation over independent single-image SSD-MobileNetV2 detections.',
        'mode': 'same_defect',
        'total_views': len(processed_images),
        'combined_visual_severity': overall_visual_severity,
        'report_rvsi': report_rvsi,
        'image_rvsi_scores': report_rvsi_res['image_rvsi_scores'],
        'aggregation_method': report_rvsi_res['aggregation_method'],
        'aggregation_version': report_rvsi_res['aggregation_version'],
        'rvsi_method': severity_service.RVSI_METHOD_NAME,
        'rvsi_version': severity_service.RVSI_VERSION,
        'combined_classes': [c for c in report_detected_classes if c != 'None Detected'],
        'class_assessments': class_assessments,
        'per_view_summary': [
            {
                'view_index': idx + 1,
                'filename': item['unique_filename'],
                'defect_class': item['detection'].get('defect_class', 'None Detected'),
                'detected_classes': item['detection'].get('detected_classes', []),
                'relative_severity': item['detection'].get('relative_severity', 'Low'),
                'rvsi_score': item['detection'].get('rvsi_score', 0.0),
                'confidence': float(item['detection'].get('confidence_score') or 0.0),
                'detections_count': len(item['detection'].get('detections', []))
            }
            for idx, item in enumerate(processed_images)
        ]
    }

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
            'severity': overall_visual_severity,
            'report_rvsi': report_rvsi,
            'rvsi_score': report_rvsi,
            'image_rvsi_scores': report_rvsi_res['image_rvsi_scores'],
            'aggregation_method': report_rvsi_res['aggregation_method'],
            'aggregation_version': report_rvsi_res['aggregation_version'],
            'rvsi_method': severity_service.RVSI_METHOD_NAME,
            'rvsi_version': severity_service.RVSI_VERSION,
            'severity_threshold_source': severity_service.DEFAULT_RVSI_THRESHOLD_SOURCE,
            'postprocessing_version': severity_service.POSTPROCESSING_VERSION,
            'image_count': len(processed_images),
            'multi_image_mode': multi_image_mode,
            'image_relationship': 'Multiple views of the same defect' if multi_image_mode == 'same_defect' else ('Different defect observations' if multi_image_mode == 'multi_defect' else 'Single image'),
            'combined_multi_view_assessment': combined_multi_view_assessment,
            'is_unusual': validation_result['is_unusual'],
            'requires_engineer_review': validation_result.get('requires_engineer_review', True),
            'validation_status': validation_result.get('validation_status', 'valid'),
            'validation_message': validation_result.get('validation_message', ''),
            'flags': validation_result['flags'],
            'flag_reasons': validation_result['flag_reasons'],
            'advisory_notes': validation_result['advisory_notes'],
            'priority': validation_result['priority'],
            'building_floors': building_floors,
            'building_floors_mode': building_floors_mode,
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

    # Short stable human-readable display case reference (e.g. REP-2026-0142)
    display_id = f"REP-{current_year}-{str(report_id)[-4:].upper()}"
    report.metadata['display_id'] = display_id
    db_service.update_one('infrastructure_reports', {'_id': report_id}, {
        'metadata.display_id': display_id,
        'metadata.combined_multi_view_assessment': combined_multi_view_assessment,
        'display_id': display_id
    })

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
            rvsi_score=det.get('rvsi_score', 0.0),
            rvsi=det.get('rvsi', {}),
            rvsi_method=det.get('rvsi_method', severity_service.RVSI_METHOD_NAME),
            rvsi_version=det.get('rvsi_version', severity_service.RVSI_VERSION),
            postprocessing_version=det.get('postprocessing_version', severity_service.POSTPROCESSING_VERSION),
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

    resp = make_response(jsonify({
        'message': response_message,
        'report_id': report_id,
        'display_id': display_id,
        'status': report.status,
        'report': report.to_dict(),
        'image': primary_image,
        'images': image_records,
        'ai_assessment': primary_assessment,
        'ai_assessments': assessment_records,
        'combined_multi_view_assessment': combined_multi_view_assessment,
        'detected_classes': report_detected_classes,
        'overall_visual_severity': overall_visual_severity,
        'validation': validation_result
    }), 201)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


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
            'rvsi_score': detection_result.get('rvsi_score', 0.0),
            'area_extent': detection_result.get('area_extent', 0.0),
            'spatial_span': detection_result.get('spatial_span', 0.0),
            'multiplicity': detection_result.get('multiplicity', 0.0),
            'rvsi': detection_result.get('rvsi', {}),
            'rvsi_method': detection_result.get('rvsi_method', severity_service.RVSI_METHOD_NAME),
            'rvsi_version': detection_result.get('rvsi_version', severity_service.RVSI_VERSION),
            'postprocessing_version': detection_result.get('postprocessing_version', severity_service.POSTPROCESSING_VERSION),
            'relative_area': detection_result.get('relative_area', 0.0),
            'area_percentage': detection_result.get('area_percentage', 0.0),
            'bounding_box': detection_result['bounding_box'],
            'bounding_box_pixels': detection_result.get('bounding_box_pixels'),
            'detections': detection_result['detections'],
            'cross_class_overlaps': detection_result.get('cross_class_overlaps', []),
            'raw_detection_count': detection_result.get('raw_detection_count', 0),
            'cleaned_detection_count': detection_result.get('cleaned_detection_count', 0),
            'score_threshold': detection_result.get('score_threshold', 0.30),
            'nms_iou_threshold': detection_result.get('nms_iou_threshold', 0.50),
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
    casework_filter = request.args.get('filter') or request.args.get('casework_filter')

    if casework_filter:
        if casework_filter == 'awaiting_review':
            query['status'] = InfrastructureReport.STATUS_RECEIVED
        elif casework_filter == 'my_reviews':
            query['status'] = InfrastructureReport.STATUS_UNDER_REVIEW
            query['$or'] = [
                {'metadata.assigned_engineer_id': user_id},
                {'metadata.reviewer_id': user_id}
            ]
        elif casework_filter == 'my_verified':
            query['status'] = InfrastructureReport.STATUS_VERIFIED
            query['$or'] = [
                {'metadata.assigned_engineer_id': user_id},
                {'metadata.reviewer_id': user_id}
            ]
        elif casework_filter == 'resolved':
            query['status'] = InfrastructureReport.STATUS_RESOLVED
    elif status_filter:
        query['status'] = InfrastructureReport.normalize_lifecycle_status(status_filter)
    elif exclude_status and exclude_status.lower() != 'none':
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

        display_id = rep.get('display_id') or rep.get('metadata', {}).get('display_id') or f"REP-{datetime.now(timezone.utc).year}-{str(report_id)[-4:].upper()}"
        meta = rep.get('metadata', {})
        enriched_reports.append({
            'report_id': report_id,
            'display_id': display_id,
            'user_id': rep.get('user_id'),
            'description': rep.get('description'),
            'status': rep.get('status'),
            'date_submitted': rep.get('date_submitted'),
            'metadata': meta,
            'assigned_engineer_id': meta.get('assigned_engineer_id') or meta.get('reviewer_id'),
            'assigned_engineer_name': meta.get('assigned_engineer_name') or meta.get('reviewed_by'),
            'inspection_notebook': meta.get('inspection_notebook', {}),
            'combined_multi_view_assessment': meta.get('combined_multi_view_assessment'),
            'asset': asset or {
                'location': meta.get('location_name', 'Monitored Infrastructure'),
                'asset_type': meta.get('asset_type', 'Road / Pavement')
            },
            'image': image_info,
            'assessment': assessment,
            'review': review
        })

    resp = make_response(jsonify({'reports': enriched_reports, 'count': len(enriched_reports)}), 200)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@reports_bp.route('/<report_id>', methods=['GET'])
@login_required
def get_report_detail(current_user, report_id):
    """Retrieves full details for a single defect report."""
    report = db_service.find_one('infrastructure_reports', {'_id': report_id})
    if not report:
        report = db_service.find_one('infrastructure_reports', {'report_id': report_id})
    if not report:
        return jsonify({'error': 'Report not found.'}), 404

    # Authorization: citizen may only access their own report
    user_role = current_user.get('role', 'citizen')
    user_id = str(current_user.get('_id') or current_user.get('user_id'))
    owner_id = str(report.get('user_id') or report.get('metadata', {}).get('submitted_by_id') or '')
    if user_role == 'citizen' and owner_id != user_id:
        return jsonify({'error': 'Forbidden: Access denied to this report.'}), 403

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
                clean_leg = os.path.basename(str(legacy_img.get('image_path', '')).replace('\\', '/'))
                primary_image = {
                    'image_id': legacy_img['_id'],
                    'url': f"/api/reports/images/{clean_leg}",
                    'filename': clean_leg,
                    'original_filename': legacy_img.get('original_filename', ''),
                    'file_size': legacy_img.get('file_size', 0),
                    'dimensions': legacy_img.get('dimensions', {})
                }
                image_list = [primary_image]
        elif legacy_image_path:
            clean_leg = os.path.basename(str(legacy_image_path).replace('\\', '/'))
            primary_image = {
                'image_id': 'legacy',
                'url': f"/api/reports/images/{clean_leg}",
                'filename': clean_leg,
                'original_filename': clean_leg,
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

    display_id = report.get('display_id') or meta.get('display_id') or f"REP-{datetime.now(timezone.utc).year}-{str(report_id)[-4:].upper()}"

    resp = make_response(jsonify({
        'report': report,
        'report_id': report_id,
        'display_id': display_id,
        'combined_multi_view_assessment': meta.get('combined_multi_view_assessment'),
        'submitter': submitter_info,
        'asset': asset,
        'image': primary_image,
        'images': image_list,
        'assessment': primary_assessment,
        'assessments': assessment_list,
        'review': review
    }), 200)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


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
    retention_days = 7
    try:
        raw_ret = request.args.get('retention_days')
        if raw_ret is not None:
            retention_days = int(raw_ret)
    except (ValueError, TypeError):
        retention_days = 7

    query = {}
    if status_filter:
        query['status'] = InfrastructureReport.normalize_lifecycle_status(status_filter)

    reports = db_service.find('infrastructure_reports', query, sort_key='date_submitted', reverse=True)

    now_utc = datetime.now(timezone.utc)
    map_points = []
    for rep in reports:
        meta = rep.get('metadata', {})
        rep_status = InfrastructureReport.normalize_lifecycle_status(rep.get('status'))

        # Section 10: Operational map retention window (default 7 days)
        # Resolved reports older than retention_days are excluded from default operational map
        # unless explicit status filter specifies Resolved.
        if rep_status == InfrastructureReport.STATUS_RESOLVED and (not status_filter or status_filter.lower() != 'resolved'):
            res_date_str = meta.get('resolved_at') or rep.get('last_updated_at') or rep.get('date_submitted')
            if res_date_str:
                try:
                    clean_d = res_date_str.replace('Z', '+00:00')
                    if '+' in clean_d[10:] or '-' in clean_d[10:]:
                        res_dt = datetime.fromisoformat(clean_d)
                    else:
                        res_dt = datetime.fromisoformat(clean_d).replace(tzinfo=timezone.utc)
                    if (now_utc - res_dt).total_seconds() > retention_days * 86400:
                        continue
                except Exception:
                    pass

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

        display_id = meta.get('display_id') or rep.get('display_id') or f"REP-{datetime.now(timezone.utc).year}-{str(rep['_id'])[-4:].upper()}"
        user_sub = str(user.get('_id') or user.get('user_id')) if user else ''
        rep_user_id = str(rep.get('user_id') or meta.get('submitted_by_id') or '')
        is_owner = bool(user_sub and rep_user_id and user_sub == rep_user_id)

        rep_rvsi = meta.get('report_rvsi') or meta.get('rvsi_score') or (assessment.get('rvsi_score') if assessment else None) or 0.0

        point = {
            'report_id': rep['_id'],
            'display_id': display_id,
            'is_owner': is_owner,
            'latitude': float(lat),
            'longitude': float(lng),
            'location_name': meta.get('location_name', 'Monitored Infrastructure'),
            'asset_type': asset_t,
            'defect_class': defect_c,
            'detected_classes': meta.get('detected_classes', [defect_c]),
            'relative_severity': rel_sev,
            'report_rvsi': float(rep_rvsi),
            'rvsi_score': float(rep_rvsi),
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

    # Retrieve active Safety Advisories (deactivated once report is Resolved)
    active_advisories = []
    raw_advisories = db_service.find('safety_advisories', {'status': {'$ne': 'inactive'}})
    for adv in raw_advisories:
        rep = db_service.find_one('infrastructure_reports', {'_id': adv.get('report_id')})
        rep_status = rep.get('status') if rep else 'Under Review'
        # Once report is Resolved, advisory is inactive (no permanent active hazard marker)
        if rep_status == 'Resolved':
            continue

        lat = adv.get('latitude') or (rep.get('latitude') if rep else None)
        lng = adv.get('longitude') or (rep.get('longitude') if rep else None)
        if lat is not None and lng is not None:
            active_advisories.append({
                'advisory_id': adv.get('advisory_id', str(adv.get('_id'))),
                'report_id': adv.get('report_id'),
                'display_id': (rep.get('metadata', {}).get('display_id') if rep else None) or f"REP-{adv.get('report_id', '')[-4:].upper()}",
                'category': adv.get('category', 'Safety Advisory'),
                'note': adv.get('professional_note', ''),
                'location_name': adv.get('location_name', 'Monitored Infrastructure'),
                'latitude': float(lat),
                'longitude': float(lng),
                'issued_by': 'Verified Civil Infrastructure Engineer',  # Privacy: zero citizen or reviewer PII exposed
                'issued_at': adv.get('issued_at'),
                'status': 'active',
                'related_status': rep_status
            })

    resp = make_response(jsonify({
        'points': map_points,
        'count': len(map_points),
        'safety_advisories': active_advisories,
        'advisories': active_advisories,
        'advisories_count': len(active_advisories),
        'mode': 'privileged' if is_privileged else 'public'
    }), 200)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@reports_bp.route('/safety-advisories/active', methods=['GET'])
def get_active_safety_advisories():
    """Returns active Safety Advisories for map presentation and navigation."""
    raw_advisories = db_service.find('safety_advisories', {'status': {'$ne': 'inactive'}})
    active_list = []
    for adv in raw_advisories:
        rep = db_service.find_one('infrastructure_reports', {'_id': adv.get('report_id')})
        rep_status = rep.get('status') if rep else 'Under Review'
        if rep_status == 'Resolved':
            continue

        lat = adv.get('latitude') or (rep.get('latitude') if rep else None)
        lng = adv.get('longitude') or (rep.get('longitude') if rep else None)
        if lat is not None and lng is not None:
            active_list.append({
                'advisory_id': adv.get('advisory_id', str(adv.get('_id'))),
                'report_id': adv.get('report_id'),
                'display_id': (rep.get('metadata', {}).get('display_id') if rep else None) or f"REP-{adv.get('report_id', '')[-4:].upper()}",
                'category': adv.get('category', 'Safety Advisory'),
                'note': adv.get('professional_note', ''),
                'location_name': adv.get('location_name', 'Monitored Infrastructure'),
                'latitude': float(lat),
                'longitude': float(lng),
                'issued_by': 'Verified Civil Infrastructure Engineer',
                'issued_at': adv.get('issued_at'),
                'status': 'active',
                'related_status': rep_status
            })

    resp = make_response(jsonify({'advisories': active_list, 'count': len(active_list)}), 200)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@reports_bp.route('/<report_id>/status', methods=['PUT', 'PATCH'])
@login_required
def update_report_status(current_user, report_id):
    """
    FR-06 & Lifecycle Management: Allows authorized Civil Engineers and Administrators
    to transition reports through the canonical lifecycle:
    Received -> Verified -> Under Review -> Resolved
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

    # Section 26: Forward-only lifecycle in ordinary engineer operations
    if current_status == InfrastructureReport.STATUS_RESOLVED and user_role != 'admin':
        return jsonify({'error': 'This defect report is resolved and in read-only mode.'}), 400

    if user_role != 'admin' and not InfrastructureReport.can_transition(current_status, target_status):
        return jsonify({
            'error': f"Invalid status transition from '{current_status}' to '{target_status}'. Permitted forward lifecycle: Received -> Verified -> Under Review -> Resolved."
        }), 400

    user_id_str = str(current_user.get('_id') or current_user.get('user_id'))
    meta = report.get('metadata', {})
    now_iso = datetime.now(timezone.utc).isoformat()

    # Resolution Guard: strict checks when transitioning to Resolved
    if target_status == InfrastructureReport.STATUS_RESOLVED:
        # 1. Lead engineer authorization check:
        current_lead = meta.get('current_lead_engineer') or {}
        lead_id = str(current_lead.get('user_id') or meta.get('assigned_engineer_id') or '')
        if user_role != 'admin' and lead_id and lead_id != user_id_str:
            lead_name = current_lead.get('name') or meta.get('assigned_engineer_name', 'Assigned Lead Engineer')
            return jsonify({
                'error': f"Only the assigned Lead Engineer ({lead_name}) or an administrator can resolve this case."
            }), 403

        # 2. Inspection Objectives Check:
        notebook = meta.get('inspection_notebook') or report.get('inspection_notebook') or {}
        checklist = notebook.get('checklist') or []
        if not checklist:
            # If no notebook was persisted yet, load default template to ensure objectives are verified
            checklist = get_default_notebook_template(report.get('asset_type') or meta.get('asset_type')).get('checklist', [])
            notebook['checklist'] = checklist
            meta['inspection_notebook'] = notebook

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

        # 3. Final closure summary check:
        if not notes and not notebook.get('summary_notes') and not notebook.get('note_cards'):
            return jsonify({
                'error': 'Cannot resolve case: A professional closure summary or engineering resolution note is required.'
            }), 400

    # Engineer Ownership & Accountability (Canonical: Received -> Verified -> Under Review -> Resolved)
    if target_status in (InfrastructureReport.STATUS_VERIFIED, InfrastructureReport.STATUS_UNDER_REVIEW):
        if not meta.get('original_verifying_engineer'):
            meta['original_verifying_engineer'] = {
                'user_id': user_id_str,
                'name': current_user.get('name', 'Certified Engineer'),
                'email': current_user.get('email', ''),
                'verified_at': now_iso
            }
        if not meta.get('current_lead_engineer'):
            meta['current_lead_engineer'] = {
                'user_id': user_id_str,
                'name': current_user.get('name', 'Certified Engineer'),
                'email': current_user.get('email', ''),
                'assigned_at': now_iso
            }
        meta['lead_engineer'] = meta['current_lead_engineer']
        if not meta.get('inspection_notebook') or not meta['inspection_notebook'].get('checklist'):
            meta['inspection_notebook'] = get_default_notebook_template(report.get('asset_type') or meta.get('asset_type'))
        meta['assigned_engineer_id'] = user_id_str
        meta['assigned_engineer_name'] = current_user.get('name', 'Certified Engineer')
        meta['assigned_engineer_email'] = current_user.get('email', '')
        meta['assigned_at'] = now_iso
        meta['requires_engineer_review'] = False

    history = meta.get('status_history', [])
    history.append({
        'status': target_status,
        'timestamp': now_iso,
        'updated_by': current_user.get('name', 'Certified Engineer'),
        'user_id': user_id_str,
        'notes': notes or f"Status transitioned to {target_status}."
    })
    meta['status_history'] = history

    # Automatically mark associated safety advisory inactive when report is Resolved
    if target_status == InfrastructureReport.STATUS_RESOLVED:
        meta['resolved_at'] = now_iso
        db_service.update_many('safety_advisories', {'report_id': report_id}, {
            'status': 'inactive',
            'closed_at': now_iso,
            'closed_reason': 'Report Resolved'
        })
        if 'safety_advisory' in meta and isinstance(meta['safety_advisory'], dict):
            meta['safety_advisory']['status'] = 'inactive'
            meta['safety_advisory']['closed_at'] = now_iso

        # Dispatch citizen notification on resolution
        submitter_id = str(report.get('user_id') or meta.get('submitted_by_id') or '')
        if submitter_id:
            from ..services.notification_service import notification_service
            feedback_str = f" Note: {notes}" if notes else ""
            msg = f"Your infrastructure defect report has been professionally resolved.{feedback_str}"
            notification_service.create_notification(submitter_id, report_id, 'resolved', 'Report Resolved', msg)

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
    strictly rejects directory traversal attempts, and resolves across local storage
    and Google Cloud Storage (GCS).
    """
    return storage_service.serve_file(filename)
