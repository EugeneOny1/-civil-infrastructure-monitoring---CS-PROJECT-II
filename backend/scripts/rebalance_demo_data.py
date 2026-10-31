"""
InfraVision Demo Dataset Rebalancing Script
-------------------------------------------
Rebalances demonstration and seeded defect reports across Nairobi corridors with
representative severities (Low, Medium, Critical), clusters, and verified evidence images.
PRESERVES all legitimate real user submissions.
"""

import sys
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from app.services.database import db_service
from app.models.report import InfrastructureReport

def run_rebalancing():
    app = create_app('development')
    db = db_service.db

    print("=== InfraVision Demo Data Rebalancing ===")
    
    # 1. Identify and preserve legitimate real user submissions
    all_reports = list(db['infrastructure_reports'].find({}))
    print(f"Total reports found in DB: {len(all_reports)}")

    legitimate_reports = []
    synthetic_reports = []

    for r in all_reports:
        uid = str(r.get('user_id', ''))
        # Genuine user submissions have citizen user IDs, real submitter accounts
        if uid != 'usr_eng_test_author':
            legitimate_reports.append(r)
        else:
            synthetic_reports.append(r)

    print(f"Legitimate citizen user submissions to preserve: {len(legitimate_reports)}")
    for lr in legitimate_reports:
        print(f"  - Preserved: {lr.get('_id')} (User: {lr.get('user_id')}, Loc: {lr.get('location') or lr.get('metadata', {}).get('location_name')})")

    print(f"Synthetic test author records to rebalance: {len(synthetic_reports)}")

    # Clean up old synthetic test records and their child records
    synth_ids = [r['_id'] for r in synthetic_reports]
    if synth_ids:
        # Find any submitted_images or assessments tied to these synth IDs
        old_images = list(db['submitted_images'].find({'report_id': {'$in': synth_ids}}))
        old_image_ids = [img['_id'] for img in old_images]
        if old_image_ids:
            db['ai_assessments'].delete_many({'image_id': {'$in': old_image_ids}})
            db['submitted_images'].delete_many({'_id': {'$in': old_image_ids}})
        db['professional_reviews'].delete_many({'report_id': {'$in': synth_ids}})
        db['infrastructure_reports'].delete_many({'_id': {'$in': synth_ids}})
        print(f"Purged {len(synth_ids)} obsolete synthetic records.")

    now_utc = datetime.now(timezone.utc)
    one_day_ago = (now_utc - timedelta(days=1)).isoformat()
    two_days_ago = (now_utc - timedelta(days=2)).isoformat()
    three_days_ago = (now_utc - timedelta(days=3)).isoformat()
    four_days_ago = (now_utc - timedelta(days=4)).isoformat()

    # 2. Define Curated Demonstration Dataset Across Nairobi Corridors
    # Plausible coordinates, balanced severities, isolated and cluster formations
    demo_definitions = [
        # --- A. UHURU HIGHWAY CRITICAL HOTSPOT CLUSTER (Score: (3+3+3+2)/4 = 2.75 -> RED) ---
        {
            'id': 'REP-DEMO-UHURU-01',
            'location': 'Uhuru Highway (Nyayo Stadium Section)',
            'asset_type': 'Highway / Pavement',
            'lat': -1.2940, 'lng': 36.8190,
            'defect_class': 'Pothole',
            'severity': 'Critical',
            'status': 'Received',
            'confidence': 0.88,
            'area_pct': 18.5,
            'box': [0.32, 0.22, 0.82, 0.78],
            'image_file': 'seed_pothole.jpg',
            'desc': 'Severe pothole crater across southbound lane causing vehicle diversion.',
            'created_at': one_day_ago,
            'next_action': 'Continue monitoring'
        },
        {
            'id': 'REP-DEMO-UHURU-02',
            'location': 'Uhuru Highway (Haile Selassie Roundabout)',
            'asset_type': 'Highway / Pavement',
            'lat': -1.2935, 'lng': 36.8195,
            'defect_class': 'Pothole',
            'severity': 'Critical',
            'status': 'Under Review',
            'confidence': 0.85,
            'area_pct': 16.8,
            'box': [0.32, 0.22, 0.82, 0.78],
            'image_file': 'seed_pothole.jpg',
            'desc': 'Deep asphalt depression in middle lane with exposed sub-base rock.',
            'created_at': two_days_ago,
            'next_action': 'On-site inspection recommended'
        },
        {
            'id': 'REP-DEMO-UHURU-03',
            'location': 'Uhuru Highway (Processional Way Junction)',
            'asset_type': 'Highway / Pavement',
            'lat': -1.2945, 'lng': 36.8185,
            'defect_class': 'Pothole',
            'severity': 'Critical',
            'status': 'Received',
            'confidence': 0.91,
            'area_pct': 21.2,
            'box': [0.32, 0.22, 0.82, 0.78],
            'image_file': 'seed_pothole.jpg',
            'desc': 'Major structural pavement breach requiring emergency cold patching.',
            'created_at': three_days_ago,
            'next_action': 'Continue monitoring'
        },
        {
            'id': 'REP-DEMO-UHURU-04',
            'location': 'Uhuru Highway (Kenyatta Avenue Flyover Approach)',
            'asset_type': 'Highway / Overpass',
            'lat': -1.2930, 'lng': 36.8200,
            'defect_class': 'Crack',
            'severity': 'Medium',
            'status': 'Under Review',
            'confidence': 0.79,
            'area_pct': 9.4,
            'box': [0.25, 0.20, 0.85, 0.75],
            'image_file': 'seed_crack.jpg',
            'desc': 'Transverse and block cracking adjacent to expansion joint.',
            'created_at': four_days_ago,
            'next_action': 'On-site inspection recommended'
        },

        # --- B. CBD / KENYATTA AVENUE MODERATE AMBER CLUSTER (Score: (2+1+2)/3 = 1.67 -> AMBER) ---
        {
            'id': 'REP-DEMO-CBD-01',
            'location': 'Kenyatta Avenue / GPO Roundabout',
            'asset_type': 'Road / Pavement',
            'lat': -1.2850, 'lng': 36.8205,
            'defect_class': 'Crack',
            'severity': 'Medium',
            'status': 'Received',
            'confidence': 0.82,
            'area_pct': 11.2,
            'box': [0.25, 0.20, 0.85, 0.75],
            'image_file': 'seed_crack.jpg',
            'desc': 'Longitudinal pavement crack extending 4 metres along bus terminal lane.',
            'created_at': two_days_ago,
            'next_action': 'Continue monitoring'
        },
        {
            'id': 'REP-DEMO-CBD-02',
            'location': 'Kenyatta Avenue / Wabera Street Junction',
            'asset_type': 'Road / Pavement',
            'lat': -1.2852, 'lng': 36.8212,
            'defect_class': 'Surface Deterioration',
            'severity': 'Low',
            'status': 'Received',
            'confidence': 0.76,
            'area_pct': 4.3,
            'box': [0.20, 0.15, 0.85, 0.85],
            'image_file': 'seed_surface.jpg',
            'desc': 'Bitumen ravelling and surface aggregate stripping on pedestrian crossing.',
            'created_at': three_days_ago,
            'next_action': 'Continue monitoring'
        },
        {
            'id': 'REP-DEMO-CBD-03',
            'location': 'Kenyatta Avenue / Muindi Mbingu Crossing',
            'asset_type': 'Road / Pavement',
            'lat': -1.2848, 'lng': 36.8200,
            'defect_class': 'Pothole',
            'severity': 'Medium',
            'status': 'Under Review',
            'confidence': 0.84,
            'area_pct': 12.0,
            'box': [0.32, 0.22, 0.82, 0.78],
            'image_file': 'seed_pothole.jpg',
            'desc': 'Shallow pothole forming around utility manhole collar.',
            'created_at': one_day_ago,
            'next_action': 'On-site inspection recommended'
        },

        # --- C. LANGATA / OLE SANGALE LOW SEVERITY GREEN CLUSTER (Score: (1+1+1)/3 = 1.00 -> GREEN) ---
        {
            'id': 'REP-DEMO-LANGATA-01',
            'location': 'Ole Sangale Road (Strathmore University Gate B)',
            'asset_type': 'Road / Pavement',
            'lat': -1.3090, 'lng': 36.8115,
            'defect_class': 'Crack',
            'severity': 'Low',
            'status': 'Received',
            'confidence': 0.78,
            'area_pct': 3.8,
            'box': [0.25, 0.20, 0.85, 0.75],
            'image_file': 'seed_crack.jpg',
            'desc': 'Hairline shrinkage cracks on newly paved campus access asphalt.',
            'created_at': two_days_ago,
            'next_action': 'Continue monitoring'
        },
        {
            'id': 'REP-DEMO-LANGATA-02',
            'location': 'Ole Sangale Road / KWS Headquarters Approach',
            'asset_type': 'Road / Pavement',
            'lat': -1.3095, 'lng': 36.8120,
            'defect_class': 'Crack',
            'severity': 'Low',
            'status': 'Received',
            'confidence': 0.74,
            'area_pct': 4.1,
            'box': [0.25, 0.20, 0.85, 0.75],
            'image_file': 'seed_crack.jpg',
            'desc': 'Minor edge cracking on drainage kerb line.',
            'created_at': three_days_ago,
            'next_action': 'Continue monitoring'
        },
        {
            'id': 'REP-DEMO-LANGATA-03',
            'location': 'Ole Sangale Road / Madaraka Estate Culvert',
            'asset_type': 'Bridge / Culvert',
            'lat': -1.3085, 'lng': 36.8110,
            'defect_class': 'Surface Deterioration',
            'severity': 'Low',
            'status': 'Verified',
            'confidence': 0.77,
            'area_pct': 4.8,
            'box': [0.20, 0.15, 0.85, 0.85],
            'image_file': 'seed_surface.jpg',
            'desc': 'Weathering and micro-fissures on headwall culvert concrete face.',
            'created_at': four_days_ago,
            'reviewed_by': 'Eng. P. Njuguna, PE (EBK B4512)',
            'review_notes': 'Superficial spalling verified; routine monitoring advised for monsoon season.',
            'next_action': 'Routine maintenance plan'
        },

        # --- D. ISOLATED CORRIDOR MONITORED POINTS ---
        {
            'id': 'REP-DEMO-WESTLANDS-01',
            'location': 'Waiyaki Way / Chiromo Interchange',
            'asset_type': 'Highway / Overpass',
            'lat': -1.2640, 'lng': 36.8040,
            'defect_class': 'Pothole',
            'severity': 'Medium',
            'status': 'Under Review',
            'confidence': 0.81,
            'area_pct': 10.5,
            'box': [0.32, 0.22, 0.82, 0.78],
            'image_file': 'seed_pothole.jpg',
            'desc': 'Pothole on expressway ramp merge lane.',
            'created_at': two_days_ago,
            'next_action': 'On-site inspection recommended'
        },
        {
            'id': 'REP-DEMO-NGONG-01',
            'location': 'Ngong Road / City Mortuary Roundabout',
            'asset_type': 'Road / Pavement',
            'lat': -1.2995, 'lng': 36.7865,
            'defect_class': 'Surface Deterioration',
            'severity': 'Medium',
            'status': 'Received',
            'confidence': 0.79,
            'area_pct': 8.9,
            'box': [0.20, 0.15, 0.85, 0.85],
            'image_file': 'seed_surface.jpg',
            'desc': 'Asphalt bleeding and rutting in high-braking bus bay.',
            'created_at': one_day_ago,
            'next_action': 'Continue monitoring'
        },
        {
            'id': 'REP-DEMO-SOUTHB-01',
            'location': 'South B / Kapiti Road',
            'asset_type': 'Road / Pavement',
            'lat': -1.3125, 'lng': 36.8360,
            'defect_class': 'Crack',
            'severity': 'Low',
            'status': 'Received',
            'confidence': 0.75,
            'area_pct': 4.2,
            'box': [0.25, 0.20, 0.85, 0.75],
            'image_file': 'seed_crack.jpg',
            'desc': 'Longitudinal settlement crack along service lane shoulder.',
            'created_at': three_days_ago,
            'next_action': 'Continue monitoring'
        },
        {
            'id': 'REP-DEMO-INDUS-01',
            'location': 'Industrial Area / Commercial Street',
            'asset_type': 'Road / Pavement',
            'lat': -1.3055, 'lng': 36.8510,
            'defect_class': 'Pothole',
            'severity': 'Critical',
            'status': 'Received',
            'confidence': 0.92,
            'area_pct': 19.8,
            'box': [0.32, 0.22, 0.82, 0.78],
            'image_file': 'seed_pothole.jpg',
            'desc': 'Extensive structural cratering with heavy goods vehicle axle hazard.',
            'created_at': one_day_ago,
            'next_action': 'Continue monitoring'
        },

        # --- E. RESOLVED CASES (Demonstrating completed workflow & read-only review) ---
        {
            'id': 'REP-DEMO-RESOLVED-01',
            'location': 'Haile Selassie Avenue (CBD South)',
            'asset_type': 'Road / Pavement',
            'lat': -1.2905, 'lng': 36.8252,
            'defect_class': 'Pothole',
            'severity': 'Medium',
            'status': 'Resolved',
            'confidence': 0.86,
            'area_pct': 13.5,
            'box': [0.32, 0.22, 0.82, 0.78],
            'image_file': 'seed_pothole.jpg',
            'desc': 'Completed asphalt reinstatement and seal coating after water main repair.',
            'created_at': four_days_ago,
            'is_resolved': True,
            'reviewed_by': 'Eng. J. Kamau, PE (EBK A1429)',
            'review_notes': 'Hot-mix asphalt patch verified, compacted to 98% Marshall density and reopened to traffic.',
            'next_action': 'No further action required at this stage'
        },
        {
            'id': 'REP-DEMO-RESOLVED-02',
            'location': 'Ring Road Westlands / Parklands Junction',
            'asset_type': 'Road / Pavement',
            'lat': -1.2660, 'lng': 36.8010,
            'defect_class': 'Crack',
            'severity': 'Low',
            'status': 'Resolved',
            'confidence': 0.77,
            'area_pct': 3.9,
            'box': [0.25, 0.20, 0.85, 0.75],
            'image_file': 'seed_crack.jpg',
            'desc': 'Elastomeric bitumen crack sealant applied along reflective crack joints.',
            'created_at': four_days_ago,
            'is_resolved': True,
            'reviewed_by': 'Eng. A. Omondi, PE (EBK B3891)',
            'review_notes': 'Bituminous joint sealant confirmed cured with zero water ingress risk.',
            'next_action': 'No further action required at this stage'
        }
    ]

    print(f"\nSeeding {len(demo_definitions)} curated demonstration records...")

    for item in demo_definitions:
        rep_id = item['id']
        image_id = f"img_demo_{rep_id.lower().replace('-', '_')}"
        assessment_id = f"ass_demo_{rep_id.lower().replace('-', '_')}"
        review_id = f"rev_demo_{rep_id.lower().replace('-', '_')}"

        # 1. Infrastructure Asset
        asset_rec = {
            '_id': f"asset_demo_{rep_id.lower().replace('-', '_')}",
            'asset_type': item['asset_type'],
            'location': item['location'],
            'description': f"Monitored civil asset along {item['location']}",
            'coordinates': {'lat': item['lat'], 'lng': item['lng']},
            'current_condition': 'Critical' if item['severity'] == 'Critical' else ('Poor' if item['severity'] == 'Medium' else 'Fair'),
            'created_at': item['created_at']
        }
        db['infrastructure_assets'].update_one({'_id': asset_rec['_id']}, {'$set': asset_rec}, upsert=True)

        # 2. Submitted Image Record pointing to valid file
        image_rec = {
            '_id': image_id,
            'report_id': rep_id,
            'image_path': item['image_file'],
            'original_filename': item['image_file'],
            'file_size': 145000,
            'dimensions': {'width': 640, 'height': 480},
            'upload_date': item['created_at']
        }
        db['submitted_images'].update_one({'_id': image_id}, {'$set': image_rec}, upsert=True)

        # 3. AI Assessment Record (internally consistent with defect class and severity)
        det_box = item['box']
        detection_entry = {
            'class_id': 1 if item['defect_class'] == 'Crack' else (2 if item['defect_class'] == 'Pothole' else 3),
            'class_name': item['defect_class'],
            'confidence': item['confidence'],
            'confidence_score': item['confidence'],
            'relative_severity': item['severity'],
            'severity': item['severity'],
            'bounding_box': det_box,
            'normalized_box': det_box,
            'bounding_box_pixels': [int(det_box[0]*480), int(det_box[1]*640), int(det_box[2]*480), int(det_box[3]*640)],
            'area_percentage': item['area_pct'],
            'relative_area': item['area_pct'] / 100.0,
            'validation_status': 'valid'
        }

        assessment_rec = {
            '_id': assessment_id,
            'image_id': image_id,
            'report_id': rep_id,
            'defect_class': item['defect_class'],
            'detected_classes': [item['defect_class']],
            'relative_severity': item['severity'],
            'severity': item['severity'],
            'confidence_score': item['confidence'],
            'area_percentage': item['area_pct'],
            'relative_area': item['area_pct'] / 100.0,
            'bounding_box': det_box,
            'detections': [detection_entry],
            'model_version': 'ssd_mobilenet_v2_lr00625_step8000_v2',
            'inference_timestamp': item['created_at'],
            'validation_status': 'valid',
            'validation_message': f"Defect matches expected profile for {item['asset_type']}."
        }
        db['ai_assessments'].update_one({'_id': assessment_id}, {'$set': assessment_rec}, upsert=True)

        # 4. Status history and review metadata
        status = item['status']
        history = [
            {
                'status': InfrastructureReport.STATUS_RECEIVED,
                'timestamp': item['created_at'],
                'updated_by': 'Citizen Reporter',
                'note': 'Report submitted via mobile field inspection.'
            }
        ]

        meta = {
            'location_name': item['location'],
            'asset_type': item['asset_type'],
            'defect_class': item['defect_class'],
            'relative_severity': item['severity'],
            'latitude': item['lat'],
            'longitude': item['lng'],
            'submitted_by_name': 'Jane Muthoni (Citizen)',
            'submitted_by_role': 'citizen',
            'requires_engineer_review': status in ['Received', 'Under Review'],
            'is_seed': True
        }

        if status in ['Under Review', 'Verified', 'Resolved']:
            history.append({
                'status': InfrastructureReport.STATUS_UNDER_REVIEW,
                'timestamp': item['created_at'],
                'updated_by': 'Eng. P. Njuguna (EBK B4512)',
                'note': 'Site inspection scheduled and review in progress.'
            })

        if status in ['Verified', 'Resolved']:
            history.append({
                'status': InfrastructureReport.STATUS_VERIFIED,
                'timestamp': item['created_at'],
                'updated_by': item.get('reviewed_by', 'Eng. P. Njuguna, PE'),
                'note': item.get('review_notes', 'Confirmed automated defect assessment and severity extent.')
            })
            meta['engineer_decision'] = 'Confirmed'
            meta['engineer_notes'] = item.get('review_notes', 'Assessment confirmed by certified engineer.')
            meta['reviewed_by'] = item.get('reviewed_by', 'Eng. P. Njuguna, PE')
            meta['reviewed_at'] = item['created_at']
            meta['next_action'] = item.get('next_action', 'Routine maintenance plan')

            if status == 'Verified':
                rev_doc = {
                    '_id': review_id,
                    'report_id': rep_id,
                    'assessment_id': assessment_id,
                    'reviewer_id': 'usr_eng_njuguna',
                    'reviewer_name': item.get('reviewed_by', 'Eng. P. Njuguna, PE (EBK B4512)'),
                    'decision': 'Confirmed',
                    'comments': item.get('review_notes', 'Verified structural defect. Maintenance recommended.'),
                    'next_action': meta['next_action'],
                    'review_date': item['created_at']
                }
                db['professional_reviews'].update_one({'_id': review_id}, {'$set': rev_doc}, upsert=True)

        if status == 'Resolved':
            meta['next_action'] = item.get('next_action', 'No further action required at this stage')
            history.append({
                'status': InfrastructureReport.STATUS_RESOLVED,
                'timestamp': now_utc.isoformat(),
                'updated_by': item.get('reviewed_by', 'Eng. P. Njuguna, PE'),
                'note': 'Civil infrastructure repair completed and verified. Defect ticket closed.'
            })
            # Create professional review record for resolved case
            rev_doc = {
                '_id': review_id,
                'report_id': rep_id,
                'assessment_id': assessment_id,
                'reviewer_id': 'usr_eng_kamau',
                'reviewer_name': item.get('reviewed_by', 'Eng. J. Kamau, PE'),
                'decision': 'Confirmed',
                'comments': item.get('review_notes', 'Repairs completed and validated.'),
                'next_action': meta['next_action'],
                'review_date': item['created_at']
            }
            db['professional_reviews'].update_one({'_id': review_id}, {'$set': rev_doc}, upsert=True)

        meta['status_history'] = history

        report_rec = {
            '_id': rep_id,
            'report_id': rep_id,
            'user_id': 'usr_demo_citizen',
            'asset_id': asset_rec['_id'],
            'description': item['desc'],
            'status': status,
            'date_submitted': item['created_at'],
            'latitude': item['lat'],
            'longitude': item['lng'],
            'images': [item['image_file']],
            'metadata': meta,
            'is_seed': True
        }
        db['infrastructure_reports'].update_one({'_id': rep_id}, {'$set': report_rec}, upsert=True)
        print(f"  + Seeded: {rep_id} [{item['severity']} - {item['defect_class']}] at {item['location']} (Status: {status})")

    # 5. Final audit of active dataset
    final_reports = list(db['infrastructure_reports'].find({}))
    sev_counts = {'Low': 0, 'Medium': 0, 'Critical': 0}
    status_counts = {}

    for r in final_reports:
        # Check assessment or metadata
        img = db['submitted_images'].find_one({'report_id': r['_id']})
        ass = db['ai_assessments'].find_one({'image_id': img['_id']}) if img else None
        sev = (ass.get('relative_severity') if ass else None) or r.get('metadata', {}).get('relative_severity', 'Low')
        st = r.get('status', 'Received')

        sev_counts[sev] = sev_counts.get(sev, 0) + 1
        status_counts[st] = status_counts.get(st, 0) + 1

    print("\n=== Dataset Audit Complete ===")
    print(f"Total Active Reports in Database: {len(final_reports)}")
    print(f"Severity Breakdown: {sev_counts}")
    print(f"Status Breakdown: {status_counts}")
    print("Seed records explicitly tagged with is_seed: True.")
    print("All legitimate user submissions were preserved untouched.")

if __name__ == '__main__':
    run_rebalancing()
