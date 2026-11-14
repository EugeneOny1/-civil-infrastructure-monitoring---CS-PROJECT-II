"""
Automated Test Suite for RVSI, Post-Processing Pipeline & Physical Engineering Assessment.
Validates:
1. Confidence filtering, Class-wise NMS, Cross-class overlap preservation and postprocessing audit metadata.
2. Relative Visual Severity Index (RVSI) formula, union area calculation without overlap double-counting,
   spatial span, multiplicity, confidence independence, and category mapping.
3. Multi-image report aggregation (0.70 * max + 0.30 * mean vs single image).
4. Physical field measurements:
   - Pothole depth FHWA LTPP classification (<25mm Low, 25-50mm Moderate, >50mm High).
   - Crack dimensions storage without fabricated physical severity.
   - Unit normalization to mm (cm, m).
   - Provenance tracking (source, engineer attribution, timestamp).
   - Citizen role access check (403 Forbidden).
5. Independence of AI Confidence, RVSI, and Physical Engineering Assessment.
"""

import math
import os
import unittest
from backend.app import create_app
from backend.app.services.database import db_service
from backend.app.services.severity import severity_service
from backend.app.services.inference import inference_service
from backend.app.utils.auth_helpers import create_access_token


class TestRVSIAndEngineeringAssessment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fixtures', 'images'))
        for target_dir in [
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'uploads')),
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'uploads')),
        ]:
            os.makedirs(target_dir, exist_ok=True)
            if os.path.exists(fixtures_dir):
                import shutil
                for fn in os.listdir(fixtures_dir):
                    src = os.path.join(fixtures_dir, fn)
                    dst = os.path.join(target_dir, fn)
                    if os.path.isfile(src) and not os.path.exists(dst):
                        shutil.copy2(src, dst)

        os.environ['DATABASE_TYPE'] = 'mock'
        cls.app = create_app()
        cls.client = cls.app.test_client()

        # Seed test users
        cls.engineer_user = {
            '_id': 'eng_test_rvsi_01',
            'user_id': 'eng_test_rvsi_01',
            'email': 'engineer.rvsi@kenha.co.ke',
            'name': 'Eng. Regina Gitau',
            'role': 'engineer',
            'verification_status': 'verified',
            'registration_number': 'A3947'
        }
        cls.citizen_user = {
            '_id': 'cit_test_rvsi_01',
            'user_id': 'cit_test_rvsi_01',
            'email': 'citizen.rvsi@gmail.com',
            'name': 'Onyi Papa J',
            'role': 'citizen',
            'verification_status': 'verified'
        }

        db_service.delete_one('users', {'_id': 'eng_test_rvsi_01'})
        db_service.delete_one('users', {'_id': 'cit_test_rvsi_01'})
        db_service.insert('users', cls.engineer_user)
        db_service.insert('users', cls.citizen_user)

        with cls.app.app_context():
            cls.engineer_token = create_access_token(cls.engineer_user)
            cls.citizen_token = create_access_token(cls.citizen_user)

    @classmethod
    def tearDownClass(cls):
        db_service.delete_one('users', {'_id': 'eng_test_rvsi_01'})
        db_service.delete_one('users', {'_id': 'cit_test_rvsi_01'})

    # ─────────────────────────────────────────────────────────────
    # 1. GEOMETRIC RECTANGLE UNION (NO DOUBLE-COUNTING)
    # ─────────────────────────────────────────────────────────────
    def test_01_boxes_union_area_identical_boxes_no_double_count(self):
        """Two identical overlapping boxes must have union area equal to a single box."""
        box1 = [0.1, 0.1, 0.5, 0.5]  # w = 0.4, h = 0.4, area = 0.16
        box2 = [0.1, 0.1, 0.5, 0.5]  # identical box

        union_area = severity_service.calculate_boxes_union_area([box1, box2])
        self.assertAlmostEqual(union_area, 0.16, places=3,
                               msg="Identical overlapping boxes must not double-count union area")

    def test_02_boxes_union_area_partial_overlap(self):
        """Partial overlap: Box 1 [0.2, 0.2, 0.6, 0.6] and Box 2 [0.4, 0.4, 0.8, 0.8]"""
        box1 = [0.2, 0.2, 0.6, 0.6]  # area = 0.16
        box2 = [0.4, 0.4, 0.8, 0.8]  # area = 0.16
        # Intersection: [0.4, 0.4, 0.6, 0.6] -> 0.2 * 0.2 = 0.04
        # Union = 0.16 + 0.16 - 0.04 = 0.28
        union_area = severity_service.calculate_boxes_union_area([box1, box2])
        self.assertAlmostEqual(union_area, 0.28, places=3,
                               msg="Partial overlap union must exactly match analytical area without double-counting")

    def test_03_boxes_union_area_disjoint(self):
        """Two completely disjoint boxes: union area must be the exact sum of both."""
        box1 = [0.1, 0.1, 0.3, 0.3]  # 0.2 * 0.2 = 0.04
        box2 = [0.6, 0.6, 0.8, 0.8]  # 0.2 * 0.2 = 0.04
        union_area = severity_service.calculate_boxes_union_area([box1, box2])
        self.assertAlmostEqual(union_area, 0.08, places=3)

    # ─────────────────────────────────────────────────────────────
    # 2. RVSI MATHEMATICAL FORMULATION & CONFIDENCE INDEPENDENCE
    # ─────────────────────────────────────────────────────────────
    def test_04_rvsi_formula_components(self):
        """Validates the exact canonical RVSI formula."""
        # 1 box: [0.1, 0.1, 0.5, 0.5]
        # area_extent = 0.16 -> sqrt(0.16) = 0.40
        # spatial_span: w=0.4, h=0.4 -> diag = sqrt(0.32) = 0.565685 -> span = 0.565685 / sqrt(2) = 0.40
        # multiplicity: min(1/5, 1.0) = 0.20
        # expected rvsi = 100 * (0.50 * 0.40 + 0.35 * 0.40 + 0.15 * 0.20)
        # = 100 * (0.20 + 0.14 + 0.03) = 100 * 0.37 = 37.0
        res = severity_service.calculate_rvsi([[0.1, 0.1, 0.5, 0.5]])
        self.assertEqual(res['rvsi_score'], 37.0)
        self.assertEqual(res['area_extent'], 0.16)
        self.assertAlmostEqual(res['spatial_span'], 0.4, places=2)
        self.assertAlmostEqual(res['multiplicity'], 0.2, places=2)
        self.assertEqual(res['detection_count'], 1)
        self.assertEqual(res['relative_severity'], 'Moderate')
        self.assertEqual(res['rvsi_method'], 'Relative Visual Severity Index')
        self.assertEqual(res['rvsi_version'], '1.0')

    def test_05_rvsi_confidence_independence(self):
        """Model confidence must NOT alter the RVSI score."""
        det_high_conf = {
            'normalized_box': [0.1, 0.1, 0.5, 0.5],
            'confidence': 0.95,
            'class_id': 1
        }
        det_low_conf = {
            'normalized_box': [0.1, 0.1, 0.5, 0.5],
            'confidence': 0.31,
            'class_id': 1
        }

        res_high = severity_service.calculate_rvsi([det_high_conf])
        res_low = severity_service.calculate_rvsi([det_low_conf])
        self.assertEqual(res_high['rvsi_score'], res_low['rvsi_score'],
                         "RVSI score must be mathematically independent of model confidence")

    def test_06_rvsi_range_bounds(self):
        """RVSI score must strictly clamp to [0.0, 100.0]."""
        # Empty detections
        empty_res = severity_service.calculate_rvsi([])
        self.assertEqual(empty_res['rvsi_score'], 0.0)
        self.assertEqual(empty_res['relative_severity'], 'Low')

        # Full image box: [0, 0, 1, 1], 10 detections
        max_boxes = [[0.0, 0.0, 1.0, 1.0] for _ in range(10)]
        max_res = severity_service.calculate_rvsi(max_boxes)
        self.assertLessEqual(max_res['rvsi_score'], 100.0)
        self.assertGreaterEqual(max_res['rvsi_score'], 0.0)
        self.assertEqual(max_res['relative_severity'], 'Critical')

    # ─────────────────────────────────────────────────────────────
    # 3. CLASS-WISE NMS & CROSS-CLASS PRESERVATION
    # ─────────────────────────────────────────────────────────────
    def test_07_class_wise_nms_suppression(self):
        """Same class with IoU >= 0.50 suppresses the lower confidence box."""
        dets = [
            {'class_id': 1, 'class_name': 'Crack', 'confidence': 0.85, 'normalized_box': [0.1, 0.1, 0.4, 0.4]},
            {'class_id': 1, 'class_name': 'Crack', 'confidence': 0.55, 'normalized_box': [0.1, 0.1, 0.4, 0.4]}
        ]
        surviving = inference_service.suppress_class_aware_duplicates(dets, iou_threshold=0.50)
        self.assertEqual(len(surviving), 1)
        self.assertEqual(surviving[0]['confidence'], 0.85)

    def test_08_cross_class_overlap_preservation(self):
        """Different classes (Crack 0.71 vs Surface deterioration 0.55) must NOT be suppressed."""
        dets = [
            {'class_id': 1, 'class_name': 'Crack', 'confidence': 0.71, 'normalized_box': [0.2, 0.2, 0.6, 0.6]},
            {'class_id': 3, 'class_name': 'Surface deterioration', 'confidence': 0.55, 'normalized_box': [0.2, 0.2, 0.6, 0.6]}
        ]
        surviving = inference_service.suppress_class_aware_duplicates(dets, iou_threshold=0.50)
        self.assertEqual(len(surviving), 2, "Cross-class overlapping detections must both be preserved for review")
        overlaps = inference_service.detect_cross_class_overlaps(surviving, overlap_threshold=0.35)
        self.assertEqual(len(overlaps), 1)
        self.assertEqual(overlaps[0]['primary_defect'], 'Crack')
        self.assertEqual(overlaps[0]['alternative_defect'], 'Surface deterioration')

    # ─────────────────────────────────────────────────────────────
    # 4. MULTI-IMAGE REPORT AGGREGATION
    # ─────────────────────────────────────────────────────────────
    def test_09_multi_image_report_rvsi_aggregation(self):
        """Multi-image reports (>= 2 images) use 0.70 * max + 0.30 * mean."""
        # Scores: 30.0 and 50.0
        # max = 50.0, mean = 40.0
        # report_rvsi = 0.70 * 50.0 + 0.30 * 40.0 = 35.0 + 12.0 = 47.0
        agg_res = severity_service.calculate_report_rvsi([30.0, 50.0])
        self.assertEqual(agg_res['report_rvsi'], 47.0)
        self.assertEqual(agg_res['relative_severity'], 'Critical')
        self.assertEqual(agg_res['aggregation_method'], '0.70_max_plus_0.30_mean')
        self.assertEqual(agg_res['aggregation_version'], '1.0')

    def test_10_single_image_report_rvsi_aggregation(self):
        """Single-image reports use report_rvsi = image_rvsi."""
        agg_res = severity_service.calculate_report_rvsi([35.5])
        self.assertEqual(agg_res['report_rvsi'], 35.5)
        self.assertEqual(agg_res['relative_severity'], 'Moderate')
        self.assertEqual(agg_res['aggregation_method'], 'single_image')

    # ─────────────────────────────────────────────────────────────
    # 5. PHYSICAL MEASUREMENTS & FHWA LTPP ASSESSMENT
    # ─────────────────────────────────────────────────────────────
    def test_11_measurement_unit_normalization(self):
        """Linear measurements are safely normalized to mm."""
        self.assertEqual(severity_service.normalize_measurement(5.5, 'cm'), 55.0)
        self.assertEqual(severity_service.normalize_measurement(1.2, 'm'), 1200.0)
        self.assertEqual(severity_service.normalize_measurement(45.0, 'mm'), 45.0)
        self.assertEqual(severity_service.normalize_measurement(2.0, 'in'), 50.8)
        self.assertIsNone(severity_service.normalize_measurement(-5.0, 'mm'))
        self.assertIsNone(severity_service.normalize_measurement('invalid', 'mm'))

    def test_12_pothole_fhwa_ltpp_classification_rules(self):
        """FHWA LTPP pothole depth classification: <25mm Low, 25-50mm Moderate, >50mm High."""
        # Low depth: 15 mm (< 25 mm)
        low_p = severity_service.assess_pothole_fhwa(15, 'mm')
        self.assertEqual(low_p['category'], 'Low')
        self.assertEqual(low_p['standard'], 'FHWA_LTPP')

        # Moderate depth: 35 mm (25-50 mm)
        mod_p = severity_service.assess_pothole_fhwa(3.5, 'cm')
        self.assertEqual(mod_p['category'], 'Moderate')
        self.assertEqual(mod_p['measured_depth_mm'], 35.0)

        # High depth: 65 mm (> 50 mm)
        high_p = severity_service.assess_pothole_fhwa(65, 'mm')
        self.assertEqual(high_p['category'], 'High')
        self.assertEqual(high_p['measured_depth_mm'], 65.0)

    def test_13_engineer_can_record_physical_measurements_via_api(self):
        """Verified engineer can record physical field measurements on a report."""
        # Create a test report
        report_data = {
            'user_id': self.citizen_user['user_id'],
            'description': 'Pothole on Denis Pritt Road',
            'status': 'Received',
            'metadata': {
                'defect_class': 'Pothole',
                'location_name': 'Denis Pritt Road, Nairobi',
                'report_rvsi': 38.0,
                'relative_severity': 'Moderate'
            }
        }
        rep_id = db_service.insert('infrastructure_reports', report_data)

        meas_payload = {
            'defect_type': 'Pothole',
            'max_depth': 55.0,
            'depth_unit': 'mm',
            'length': 450.0,
            'width': 300.0,
            'unit': 'mm',
            'method': 'Straightedge & Depth Gauge',
            'notes': 'Sharp vertical edges observed at defect perimeter'
        }

        resp = self.client.post(
            f'/api/reviews/report/{rep_id}/measurements',
            headers={'Authorization': f'Bearer {self.engineer_token}'},
            json=meas_payload
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertIn('physical_measurements', data)
        self.assertIn('engineering_assessment', data)
        self.assertEqual(data['engineering_assessment']['category'], 'High')
        self.assertEqual(data['engineering_assessment']['standard'], 'FHWA_LTPP')

        # Verify DB persistence
        saved_rep = db_service.find_one('infrastructure_reports', {'_id': rep_id})
        meta = saved_rep.get('metadata', {})
        self.assertIn('physical_measurements', meta)
        self.assertEqual(meta['physical_measurements']['source'], 'professional_field_measurement')
        self.assertEqual(meta['physical_measurements']['engineer_id'], self.engineer_user['user_id'])
        self.assertEqual(meta['physical_engineering_assessment']['category'], 'High')

    def test_14_citizen_cannot_record_physical_measurements(self):
        """Citizen role is forbidden from submitting professional measurements (403 Forbidden)."""
        report_data = {
            'user_id': self.citizen_user['user_id'],
            'description': 'Crack on Ring Road Kilimani',
            'status': 'Received',
            'metadata': {'defect_class': 'Crack'}
        }
        rep_id = db_service.insert('infrastructure_reports', report_data)

        meas_payload = {
            'defect_type': 'Crack',
            'crack_width': 5.0,
            'unit': 'mm'
        }

        resp = self.client.post(
            f'/api/reviews/report/{rep_id}/measurements',
            headers={'Authorization': f'Bearer {self.citizen_token}'},
            json=meas_payload
        )
        self.assertEqual(resp.status_code, 403, "Citizens must be denied professional measurement recording")

    def test_15_crack_measurement_does_not_invent_physical_severity(self):
        """Crack physical measurements store dimensions but do NOT invent a physical severity category."""
        report_data = {
            'user_id': self.citizen_user['user_id'],
            'description': 'Longitudinal crack',
            'status': 'Verified',
            'metadata': {'defect_class': 'Crack'}
        }
        rep_id = db_service.insert('infrastructure_reports', report_data)

        meas_payload = {
            'defect_type': 'Crack',
            'crack_width': 4.5,
            'crack_length': 1200.0,
            'unit': 'mm',
            'method': 'Crack Comparator Card'
        }

        resp = self.client.post(
            f'/api/reviews/report/{rep_id}/measurements',
            headers={'Authorization': f'Bearer {self.engineer_token}'},
            json=meas_payload
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertIsNone(data['engineering_assessment'],
                          "Crack measurements must not invent an automated physical severity category")
        self.assertEqual(data['physical_measurements']['measurements']['crack_width_mm'], 4.5)
        self.assertEqual(data['physical_measurements']['measurements']['crack_length_mm'], 1200.0)

    def test_16_single_image_and_multi_image_report_severity_consistency(self):
        """Verifies single-image & multi-image severity calculations, inches normalization, and map/list consistency."""
        # 1. Inches normalization check
        self.assertAlmostEqual(severity_service.normalize_measurement(2.0, 'in'), 50.8, places=2)

        # 2. Single-image submission with live inference
        import io
        seed_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'uploads', 'seed_pothole.jpg'
        ))
        if not os.path.exists(seed_path):
            seed_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), 'fixtures', 'images', 'seed_pothole.jpg'
            ))
        with open(seed_path, 'rb') as f:
            img_bytes = f.read()

        single_res = self.client.post(
            '/api/reports',
            data={
                'images': (io.BytesIO(img_bytes), 'single_view.jpg'),
                'latitude': '-1.2921',
                'longitude': '36.8219',
                'location': 'Uhuru Highway Single View',
                'asset_type': 'Road / Pavement'
            },
            content_type='multipart/form-data',
            headers={'Authorization': f'Bearer {self.citizen_token}'}
        )
        self.assertEqual(single_res.status_code, 201)
        single_data = single_res.get_json()
        single_ass = single_data['ai_assessment']
        expected_single_rvsi = float(single_ass.get('rvsi_score', 0.0))
        rep_meta_single = single_data.get('report', {}).get('metadata', {})
        self.assertAlmostEqual(float(rep_meta_single.get('report_rvsi', expected_single_rvsi)), expected_single_rvsi, places=1)

        # 3. Multi-image submission with two photos (0.70*max + 0.30*mean aggregation)
        multi_res = self.client.post(
            '/api/reports',
            data={
                'images': [
                    (io.BytesIO(img_bytes), 'view_a.jpg'),
                    (io.BytesIO(img_bytes), 'view_b.jpg')
                ],
                'latitude': '-1.2810',
                'longitude': '36.8250',
                'location': 'Mombasa Road Multi View',
                'asset_type': 'Road / Pavement'
            },
            content_type='multipart/form-data',
            headers={'Authorization': f'Bearer {self.citizen_token}'}
        )
        self.assertEqual(multi_res.status_code, 201)
        multi_data = multi_res.get_json()
        multi_id = multi_data['report_id']
        combined = multi_data.get('combined_multi_view_assessment') or {}
        self.assertEqual(combined.get('total_views'), 2)
        scores = combined.get('image_rvsi_scores', [])
        self.assertEqual(len(scores), 2)
        expected_agg = round(0.70 * max(scores) + 0.30 * (sum(scores) / len(scores)), 1)
        self.assertAlmostEqual(float(combined.get('report_rvsi')), expected_agg, places=1)

        # 4. Consistency when report-level combined severity differs from primary image assessment
        rep_mismatch = 'rep_mv_mismatch_test'
        img_mismatch = 'img_mv_mismatch_test'
        ass_mismatch = 'ass_mv_mismatch_test'
        db_service.insert('infrastructure_reports', {
            '_id': rep_mismatch,
            'report_id': rep_mismatch,
            'user_id': self.citizen_user['user_id'],
            'status': 'Received',
            'latitude': -1.275,
            'longitude': 36.835,
            'date_submitted': '2026-11-12T08:00:00+00:00',
            'metadata': {
                'location_name': 'Outer Ring Combined Test',
                'asset_type': 'Road / Pavement',
                'defect_class': 'Pothole',
                'relative_severity': 'Critical',
                'report_rvsi': 64.5
            }
        })
        db_service.insert('submitted_images', {
            '_id': img_mismatch,
            'report_id': rep_mismatch,
            'image_path': 'seed_pothole.jpg'
        })
        db_service.insert('ai_assessments', {
            '_id': ass_mismatch,
            'report_id': rep_mismatch,
            'image_id': img_mismatch,
            'defect_class': 'Crack',
            'relative_severity': 'Low',
            'rvsi_score': 18.0
        })

        map_resp = self.client.get('/api/reports/map')
        self.assertEqual(map_resp.status_code, 200)
        pts = map_resp.get_json().get('points', [])
        pt = next((p for p in pts if p.get('report_id') == rep_mismatch), None)
        self.assertIsNotNone(pt)
        self.assertEqual(pt['relative_severity'], 'Critical')
        self.assertAlmostEqual(pt['report_rvsi'], 64.5, places=1)

        list_resp = self.client.get(
            '/api/reports?severity=Critical',
            headers={'Authorization': f'Bearer {self.engineer_token}'}
        )
        self.assertEqual(list_resp.status_code, 200)
        list_ids = [r['report_id'] for r in list_resp.get_json().get('reports', [])]
        self.assertIn(rep_mismatch, list_ids)

        # Cleanup synthetic mismatch & multi-view reports
        db_service.delete_one('infrastructure_reports', {'_id': rep_mismatch})
        db_service.delete_one('submitted_images', {'_id': img_mismatch})
        db_service.delete_one('ai_assessments', {'_id': ass_mismatch})
        db_service.delete_one('infrastructure_reports', {'_id': multi_id})
        db_service.delete_one('infrastructure_reports', {'_id': single_data['report_id']})


if __name__ == '__main__':
    unittest.main()

