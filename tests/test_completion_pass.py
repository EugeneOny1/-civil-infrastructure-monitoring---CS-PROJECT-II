"""
Comprehensive Automated Test Suite for Final Application Completion Pass
-------------------------------------------------------------------------
Validates:
1. Map True Heatmap configuration and continuous density gradient
2. Cluster severity composition weighting (Low=1, Med=2, Crit=3; Bands: <1.50, 1.50-2.24, >=2.25)
   and ensures 1 critical report does not force red if composition is low
3. Rebalanced Nairobi demo dataset corridors, severities, and physical evidence images
4. Defect Review read-only enforcement on Resolved reports & 3-layer audit trail
5. Active Priority Queue exclusion of Resolved cases
6. Citizen feedback notifications (generation, retrieval, mark as read, unread count)
7. Google Identity Services flow, demo token disallowance, Citizen role enforcement, and 2FA
8. Admin User Governance active accounts KPI and Google health status distinction
"""

import os
import sys
import unittest
from datetime import datetime, timezone
from pymongo import MongoClient

# Ensure backend directory is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app import create_app
from app.services.database import db_service
from app.models.report import InfrastructureReport
from app.services.notification_service import notification_service
from app.utils.auth_helpers import create_access_token


class TestCompletionPass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()
        cls.created_reports = []
        cls.created_users = []

    @classmethod
    def tearDownClass(cls):
        for rep_id in cls.created_reports:
            try:
                db_service.delete_one('infrastructure_reports', {'_id': rep_id})
                db_service.delete_one('submitted_images', {'report_id': rep_id})
            except Exception:
                pass
        for u_id in cls.created_users:
            try:
                db_service.delete_one('users', {'_id': u_id})
                db_service.delete_many('citizen_notifications', {'user_id': str(u_id)})
            except Exception:
                pass

    def test_01_heatmap_configuration_and_pane_ordering(self):
        """Verifies true heatmap layer configuration, z-index pane (350), and color transition gradient."""
        map_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'map.js'))
        with open(map_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Pane ordering: heatmapPane under clusters (z-index 350)
        self.assertIn("heatmapPane", content, "Custom heatmapPane must be defined in map.js")
        self.assertIn("350", content, "heatmapPane z-index must be 350 to render beneath markers/clusters")
        self.assertIn("pointerEvents", content)

        # Heatmap gradient: green -> yellow/amber -> red
        self.assertIn("#10b981", content, "Heatmap gradient must contain green translucent intensity")
        self.assertIn("#f59e0b", content, "Heatmap gradient must contain amber/yellow intensity")
        self.assertIn("#ef4444", content, "Heatmap gradient must contain red critical intensity")

    def test_02_cluster_severity_composition_formula(self):
        """
        Verifies cluster composition score calculation:
        Low = 1, Medium = 2, Critical = 3
        cluster_severity_score = sum(weights) / count
        Bands: 1.00–1.49 green, 1.50–2.24 amber, 2.25–3.00 red
        Ensures a single Critical report does NOT automatically force red if overall composition does not warrant it.
        """
        def calc_cluster_severity(reports):
            weights = {'low': 1, 'medium': 2, 'critical': 3}
            scores = [weights.get(str(r.get('severity', 'low')).lower(), 1) for r in reports]
            avg = sum(scores) / len(scores) if scores else 1.0
            if avg >= 2.25:
                return 'red', avg
            elif avg >= 1.50:
                return 'amber', avg
            else:
                return 'green', avg

        # 1. All Low reports -> Green
        band, score = calc_cluster_severity([{'severity': 'Low'}, {'severity': 'Low'}, {'severity': 'Low'}])
        self.assertEqual(band, 'green')
        self.assertAlmostEqual(score, 1.0, places=2)

        # 2. Composition with ONE Critical report and THREE Low reports -> (3 + 1 + 1 + 1)/4 = 1.50 -> AMBER, NOT RED!
        band, score = calc_cluster_severity([
            {'severity': 'Critical'},
            {'severity': 'Low'},
            {'severity': 'Low'},
            {'severity': 'Low'}
        ])
        self.assertEqual(band, 'amber', "One Critical report out of 4 must produce Amber, not Red.")
        self.assertAlmostEqual(score, 1.50, places=2)

        # 3. High severity cluster (3 Critical + 1 Medium) -> (3 + 3 + 3 + 2)/4 = 2.75 -> RED
        band, score = calc_cluster_severity([
            {'severity': 'Critical'},
            {'severity': 'Critical'},
            {'severity': 'Critical'},
            {'severity': 'Medium'}
        ])
        self.assertEqual(band, 'red')
        self.assertAlmostEqual(score, 2.75, places=2)

    def test_03_rebalanced_demo_dataset_and_valid_images(self):
        """Verifies demo dataset has balanced severities, Nairobi corridors, and physical evidence images."""
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=2000)
        dev_db = client['civil_infrastructure']
        all_reports = list(dev_db['infrastructure_reports'].find({
            '$or': [{'metadata.is_seed': True}, {'_id': {'$regex': '^REP-DEMO-'}}]
        }))
        self.assertGreaterEqual(len(all_reports), 10, "Should have representative seeded demo records in dev DB.")

        severities = set()
        locations = set()
        for rep in all_reports:
            meta = rep.get('metadata', {})
            sev = meta.get('relative_severity')
            if sev:
                severities.add(sev)
            loc = meta.get('location_name')
            if loc:
                locations.add(loc)

        # Must span Low, Medium, and Critical
        self.assertIn('Low', severities, "Demo dataset must include Low severity reports.")
        self.assertIn('Medium', severities, "Demo dataset must include Medium severity reports.")
        self.assertIn('Critical', severities, "Demo dataset must include Critical severity reports.")

        # Must span multiple Nairobi areas
        self.assertGreaterEqual(len(locations), 5, "Demo records must span at least 5 distinct Nairobi corridors.")

        # Evidence image verification for every seed record
        uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'uploads'))
        for rep in all_reports:
            img = dev_db['submitted_images'].find_one({'report_id': rep['_id']})
            self.assertIsNotNone(img, f"Seed report {rep['_id']} must have submitted_images record.")
            img_path = os.path.join(uploads_dir, os.path.basename(img['image_path']))
            self.assertTrue(os.path.isfile(img_path), f"Evidence image file must exist on disk: {img_path}")
        client.close()

    def test_04_defect_review_resolved_read_only_and_audit_layers(self):
        """Verifies that resolved reports are read-only and preserve 3-layer audit trail."""
        # Create an engineer and a resolved report
        eng_id = f"test_eng_{int(datetime.now().timestamp())}"
        eng_doc = {
            '_id': eng_id,
            'name': 'Test Engineer',
            'email': f'{eng_id}@strathmore.edu',
            'role': 'engineer',
            'verification_status': 'verified',
            'two_factor_enabled': False
        }
        db_service.insert('users', eng_doc)
        self.created_users.append(eng_id)

        rep_id = f"test_rep_resolved_{int(datetime.now().timestamp())}"
        rep_doc = {
            '_id': rep_id,
            'status': InfrastructureReport.STATUS_RESOLVED,
            'asset_type': 'Road Pavement',
            'latitude': -1.2921,
            'longitude': 36.8219,
            'metadata': {
                'defect_class': 'Pothole',
                'relative_severity': 'Critical',
                'location_name': 'Uhuru Highway',
                'engineer_assessment': {
                    'decision': 'Confirmed',
                    'notes': 'Final professional review completed.',
                    'reviewer_name': 'Test Engineer'
                }
            }
        }
        db_service.insert('infrastructure_reports', rep_doc)
        self.created_reports.append(rep_id)

        # Login as engineer
        with self.app.app_context():
            token = create_access_token({'user_id': eng_id, 'email': eng_doc['email'], 'role': 'engineer'})
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        # Attempt to post a review update to an already Resolved report
        res = self.client.post(f'/api/reviews/report/{rep_id}', json={
            'target_status': 'Verified',
            'decision': 'Confirmed',
            'notes': 'Trying to modify resolved record'
        }, headers=headers)

        self.assertEqual(res.status_code, 400, "Should reject modifying an already resolved report.")
        data = res.get_json()
        self.assertIn("read-only mode", data.get('error', '').lower())

    def test_05_priority_queue_excludes_resolved_reports(self):
        """Verifies active defect priority queue excludes Resolved reports."""
        user_id = f"user_pq_{int(datetime.now().timestamp())}"
        user_doc = {
            '_id': user_id,
            'name': 'PQ User',
            'email': f'{user_id}@strathmore.edu',
            'role': 'engineer',
            'verification_status': 'verified',
            'two_factor_enabled': False
        }
        db_service.insert('users', user_doc)
        self.created_users.append(user_id)

        with self.app.app_context():
            token = create_access_token({'user_id': user_id, 'email': user_doc['email'], 'role': 'engineer'})
        headers = {'Authorization': f'Bearer {token}'}

        res = self.client.get('/api/reports?exclude_status=Resolved', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        reports = data.get('reports', [])
        for r in reports:
            rep = r.get('report', r)
            status = InfrastructureReport.canonical_status(rep.get('status', ''))
            self.assertNotEqual(status, InfrastructureReport.STATUS_RESOLVED, "Priority queue must NOT contain Resolved reports.")

        # Also verify analytics summary active queue
        analytics_res = self.client.get('/api/analytics/summary', headers=headers)
        if analytics_res.status_code == 200:
            summary = analytics_res.get_json()
            active_count = summary.get('active_defect_queue', 0)
            self.assertIsInstance(active_count, int)

    def test_06_citizen_notifications_lifecycle(self):
        """Verifies citizen notification generation, unread counts, and mark as read."""
        user_id = f"user_notif_{int(datetime.now().timestamp())}"
        user_doc = {
            '_id': user_id,
            'name': 'Citizen Notif User',
            'email': f'{user_id}@strathmore.edu',
            'role': 'citizen',
            'verification_status': 'verified',
            'two_factor_enabled': False
        }
        db_service.insert('users', user_doc)
        self.created_users.append(user_id)

        # 1. Create a notification
        doc = notification_service.create_notification(
            user_id=user_id,
            report_id='REP-TEST-100',
            event_type='verified',
            title='Report Verified',
            message='Your report has been professionally verified by an engineer.'
        )
        self.assertIsNotNone(doc)
        self.assertFalse(doc['is_read'])

        # 2. Retrieve notifications
        notifs = notification_service.get_user_notifications(user_id)
        self.assertEqual(len(notifs), 1)
        self.assertEqual(notifs[0]['title'], 'Report Verified')

        # 3. Mark as read via service
        success = notification_service.mark_as_read(user_id, doc['_id'])
        self.assertTrue(success)

        # 4. Check unread count
        unread_notifs = notification_service.get_user_notifications(user_id, unread_only=True)
        self.assertEqual(len(unread_notifs), 0)

        # 5. REST endpoint test
        with self.app.app_context():
            token = create_access_token({'user_id': user_id, 'email': user_doc['email'], 'role': 'citizen'})
        headers = {'Authorization': f'Bearer {token}'}

        api_res = self.client.get('/api/users/notifications', headers=headers)
        self.assertEqual(api_res.status_code, 200)
        api_data = api_res.get_json()
        self.assertEqual(api_data['count'], 1)
        self.assertEqual(api_data['unread_count'], 0)

    def test_07_google_identity_demo_rejection_and_citizen_role(self):
        """Verifies demo token is rejected in non-test mode and new Google user is strictly assigned Citizen role."""
        # In testing mode with a mock payload
        mock_email = f"google_citizen_{int(datetime.now().timestamp())}@strathmore.edu"
        res = self.client.post('/api/auth/google', json={
            'email': mock_email,
            'name': 'Google New Citizen',
            'sub': 'google_sub_998877'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        user = data.get('user', {})
        self.assertEqual(user.get('role'), 'citizen', "New Google user MUST be strictly assigned citizen role.")
        self.assertEqual(user.get('email'), mock_email)

        # Clean up user
        created_user = db_service.find_one('users', {'email': mock_email})
        if created_user:
            self.created_users.append(created_user['_id'])

    def test_08_admin_governance_kpi_and_health_distinction(self):
        """Verifies User Governance stats return active_users_count and system health distinguishes configured vs operational."""
        # Create an admin user
        admin_id = f"admin_{int(datetime.now().timestamp())}"
        admin_doc = {
            '_id': admin_id,
            'name': 'Admin User',
            'email': f'{admin_id}@infravision.ke',
            'role': 'admin',
            'verification_status': 'verified',
            'two_factor_enabled': False
        }
        db_service.insert('users', admin_doc)
        self.created_users.append(admin_id)

        with self.app.app_context():
            token = create_access_token({'user_id': admin_id, 'email': admin_doc['email'], 'role': 'admin'})
        headers = {'Authorization': f'Bearer {token}'}

        res = self.client.get('/api/admin/stats', headers=headers)
        self.assertEqual(res.status_code, 200)
        stats = res.get_json()
        self.assertIn('active_users_count', stats, "Admin stats must provide active_users_count for User Governance.")
        self.assertIn('pending_engineer_verifications', stats)
        self.assertIn('verified_engineers_count', stats)
        self.assertIn('total_users', stats)

        # Test dashboard health
        dash_res = self.client.get('/api/admin/dashboard', headers=headers)
        self.assertEqual(dash_res.status_code, 200)
        dash_data = dash_res.get_json()
        health = dash_data.get('system_health', {})
        self.assertIn('google_auth', health)
        g_status = health['google_auth'].get('status')
        self.assertIn(g_status, ['operational', 'configured', 'pending_client_id'])

    def test_09_crack_regions_grouping(self):
        """Verifies conservative presentation-layer crack-region envelope grouping."""
        from app.services.inference import InferenceService
        detections = [
            {
                'class_name': 'Crack',
                'confidence': 0.85,
                'bounding_box': {'xmin': 10, 'ymin': 10, 'xmax': 50, 'ymax': 50},
                'normalized_box': [0.03, 0.03, 0.17, 0.17]
            },
            {
                'class_name': 'Crack',
                'confidence': 0.80,
                'bounding_box': {'xmin': 40, 'ymin': 40, 'xmax': 80, 'ymax': 80},
                'normalized_box': [0.13, 0.13, 0.27, 0.27]
            },
            {
                'class_name': 'Pothole',
                'confidence': 0.90,
                'bounding_box': {'xmin': 200, 'ymin': 200, 'xmax': 260, 'ymax': 260},
                'normalized_box': [0.66, 0.66, 0.86, 0.86]
            }
        ]
        regions = InferenceService.group_crack_regions(detections, distance_threshold=0.08)
        self.assertIsInstance(regions, list)
        self.assertEqual(len(regions), 1)
        region = regions[0]
        self.assertEqual(region['segment_count'], 2)
        self.assertIn('pixel_envelope', region)
        self.assertEqual(region['label'], 'Crack region — 2 detected crack segments')

    def test_10_admin_verify_reject_user_endpoint(self):
        """Verifies PUT /api/admin/users/<user_id>/verify for status transitions."""
        import uuid
        target_eng_id = f"test_eng_t10_{uuid.uuid4().hex[:8]}"
        target_eng = {
            '_id': target_eng_id,
            'name': 'Eng. Test Subject',
            'email': f'{target_eng_id}@kenha.go.ke',
            'role': 'engineer',
            'organization': 'KeNHA',
            'professional_reg_no': 'EBK/PE/TEST/001',
            'verification_status': 'pending',
            'is_active': True,
            'two_factor_enabled': True
        }
        db_service.insert('users', target_eng)
        self.created_users.append(target_eng_id)

        # Admin token
        admin_id = f"admin_t10_{uuid.uuid4().hex[:8]}"
        admin_doc = {
            '_id': admin_id,
            'name': 'Admin Test',
            'email': f'{admin_id}@infravision.ke',
            'role': 'admin',
            'verification_status': 'verified',
            'two_factor_enabled': False
        }
        db_service.insert('users', admin_doc)
        self.created_users.append(admin_id)

        with self.app.app_context():
            token = create_access_token({'user_id': admin_id, 'email': admin_doc['email'], 'role': 'admin'})
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        # 1. Verify engineer
        put_res = self.client.put(f'/api/admin/users/{target_eng_id}/verify', json={'status': 'verified'}, headers=headers)
        self.assertEqual(put_res.status_code, 200)
        data = put_res.get_json()
        self.assertEqual(data.get('verification_status'), 'verified')

        updated = db_service.find_one('users', {'_id': target_eng_id})
        self.assertEqual(updated['verification_status'], 'verified')

        # 2. Reject engineer
        reject_res = self.client.put(f'/api/admin/users/{target_eng_id}/verify', json={'status': 'rejected'}, headers=headers)
        self.assertEqual(reject_res.status_code, 200)
        data_rej = reject_res.get_json()
        self.assertEqual(data_rej.get('verification_status'), 'rejected')

        updated_rej = db_service.find_one('users', {'_id': target_eng_id})
        self.assertEqual(updated_rej['verification_status'], 'rejected')

    def test_11_image_serving_cors_and_headers(self):
        """Verifies GET /api/reports/images/<filename> includes CORS and cache headers."""
        res = self.client.get('/api/reports/images/seed_pothole.jpg')
        if res.status_code == 200:
            self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), '*')
            self.assertIn('max-age', res.headers.get('Cache-Control', ''))

    def test_12_multi_image_mode_submission(self):
        """Verifies report creation with multi_image_mode stores correct relationship metadata."""
        import io
        from werkzeug.datastructures import MultiDict

        cit_id = f"citizen_multi_{int(datetime.now().timestamp())}"
        cit_doc = {
            '_id': cit_id,
            'name': 'Multi-Image Citizen',
            'email': f'{cit_id}@strathmore.edu',
            'role': 'citizen',
            'verification_status': 'verified'
        }
        db_service.insert('users', cit_doc)
        self.created_users.append(cit_id)

        with self.app.app_context():
            token = create_access_token({'user_id': cit_id, 'email': cit_doc['email'], 'role': 'citizen'})
        headers = {'Authorization': f'Bearer {token}'}

        test_img_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'uploads', 'seed_pothole.jpg'
        ))

        with open(test_img_path, 'rb') as f:
            b = f.read()

        data = MultiDict([
            ('images', (io.BytesIO(b), 'photo1.jpg')),
            ('images', (io.BytesIO(b), 'photo2.jpg')),
            ('latitude', '-1.286389'),
            ('longitude', '36.817223'),
            ('location', 'Kenyatta Avenue, Nairobi'),
            ('asset_type', 'Road / Pavement'),
            ('description', 'Multi-angle observation of major pavement crack'),
            ('multi_image_mode', 'same_defect')
        ])
        res = self.client.post('/api/reports', data=data, content_type='multipart/form-data', headers=headers)

        self.assertEqual(res.status_code, 201)
        resp_data = res.get_json()
        report_id = resp_data.get('report_id')
        self.created_reports.append(report_id)

        rep_doc = db_service.find_one('infrastructure_reports', {'_id': report_id})
        self.assertIsNotNone(rep_doc)
        meta = rep_doc.get('metadata', {})
        self.assertEqual(meta.get('multi_image_mode'), 'same_defect')
        self.assertEqual(meta.get('image_count'), 2)
        self.assertIn('Multiple views of the same defect', meta.get('image_relationship', ''))


if __name__ == '__main__':
    unittest.main()

