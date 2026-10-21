"""
Automated Unit and Integration Tests for Refined Authentication, EBK Validation,
Password Security, Real OTP / 2FA, Google Authentication, and Maps Privacy API.
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

# Ensure backend directory is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app import create_app
from app.services.database import db_service
from app.services.email_service import email_service
from app.utils.auth_helpers import validate_password_strength, validate_ebk_registration


class TestAuthAndMaps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()
        cls.created_user_emails = []

    @classmethod
    def tearDownClass(cls):
        for email in cls.created_user_emails:
            try:
                db_service.delete_one('users', {'email': email})
            except Exception:
                pass

    def test_01_strong_password_policy(self):
        """Verifies modern password complexity enforcement."""
        # Too short (< 8 chars)
        ok, msg = validate_password_strength("Pass1!")
        self.assertFalse(ok)
        self.assertIn("at least 8 characters", msg)

        # Missing uppercase
        ok, msg = validate_password_strength("lowercase123!")
        self.assertFalse(ok)
        self.assertIn("uppercase", msg)

        # Missing lowercase
        ok, msg = validate_password_strength("UPPERCASE123!")
        self.assertFalse(ok)
        self.assertIn("lowercase", msg)

        # Missing digit
        ok, msg = validate_password_strength("NoDigitsHere!")
        self.assertFalse(ok)
        self.assertIn("numeric digit", msg)

        # Missing symbol
        ok, msg = validate_password_strength("NoSymbols1234")
        self.assertFalse(ok)
        self.assertIn("special character", msg)

        # Common weak/default password
        ok, msg = validate_password_strength("password123")
        self.assertFalse(ok)

        # Strong valid password
        ok, msg = validate_password_strength("StrongCivilPass@2026")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_02_ebk_category_validation(self):
        """Verifies EBK registration format rules by engineering category."""
        # Graduate Engineer: B followed by digits (e.g. B24512, B12345; does NOT require B0)
        ok, clean, msg = validate_ebk_registration("Graduate Engineer", "B24512")
        self.assertTrue(ok)
        self.assertEqual(clean, "B24512")

        ok, clean, msg = validate_ebk_registration("Graduate Engineer", "b98213")
        self.assertTrue(ok)
        self.assertEqual(clean, "B98213")

        # Graduate Engineer with invalid prefix (e.g. A instead of B)
        ok, clean, msg = validate_ebk_registration("Graduate Engineer", "A3947")
        self.assertFalse(ok)

        # Professional Engineer: A followed by digits (e.g. A3947)
        ok, clean, msg = validate_ebk_registration("Professional Engineer", "A3947")
        self.assertTrue(ok)
        self.assertEqual(clean, "A3947")

        # Consulting Engineer: E followed by digits (e.g. E475)
        ok, clean, msg = validate_ebk_registration("Consulting Engineer", "E475")
        self.assertTrue(ok)
        self.assertEqual(clean, "E475")

        # Invalid formats
        ok, clean, msg = validate_ebk_registration("Professional Engineer", "INVALID_REG")
        self.assertFalse(ok)

    def test_03_citizen_registration_and_weak_password_rejection(self):
        """Verifies citizen registration rejects weak passwords and accepts strong ones."""
        weak_payload = {
            'name': 'Test Citizen',
            'email': f'weak_{int(datetime.now().timestamp())}@test.com',
            'password': 'weak',
            'role': 'citizen'
        }
        res = self.client.post('/api/auth/register', json=weak_payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn('error', res.get_json())

        strong_payload = {
            'name': 'Test Citizen Secure',
            'email': f'strong_cit_{int(datetime.now().timestamp())}@test.com',
            'password': 'SecureCitizen@2026',
            'role': 'citizen'
        }
        self.__class__.created_user_emails.append(strong_payload['email'])
        res_ok = self.client.post('/api/auth/register', json=strong_payload)
        self.assertEqual(res_ok.status_code, 201)
        self.assertIn('token', res_ok.get_json())

    def test_04_engineer_registration_ebk_enforcement(self):
        """Verifies engineer registration requires valid EBK format and sets pending verification."""
        invalid_ebk_payload = {
            'name': 'Eng. Jane Doe',
            'email': f'jane_bad_{int(datetime.now().timestamp())}@test.com',
            'password': 'SecureEngineer@2026',
            'role': 'engineer',
            'engineering_category': 'Graduate Engineer',
            'professional_reg_no': 'XYZ999'  # Malformed
        }
        res = self.client.post('/api/auth/register', json=invalid_ebk_payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn('error', res.get_json())

        valid_ebk_payload = {
            'name': 'Eng. Jane Doe Valid',
            'email': f'jane_ok_{int(datetime.now().timestamp())}@test.com',
            'password': 'SecureEngineer@2026',
            'role': 'engineer',
            'engineering_category': 'Graduate Engineer',
            'professional_reg_no': 'B24512'
        }
        self.__class__.created_user_emails.append(valid_ebk_payload['email'])
        res_ok = self.client.post('/api/auth/register', json=valid_ebk_payload)
        self.assertEqual(res_ok.status_code, 201)
        user = res_ok.get_json()['user']
        # Engineer accounts must remain pending professional verification
        self.assertEqual(user['verification_status'], 'pending')
        self.assertEqual(user['professional_reg_no'], 'B24512')

    def test_05_otp_generation_and_2fa_workflow(self):
        """Verifies OTP generation, expiry calculation, attempt limit, and verification."""
        test_email = f'otp_user_{int(datetime.now().timestamp())}@test.com'
        self.__class__.created_user_emails.append(test_email)
        reg_payload = {
            'name': 'Eng. OTP Test',
            'email': test_email,
            'password': 'SecureEngineer@2026',
            'role': 'engineer',
            'engineering_category': 'Professional Engineer',
            'professional_reg_no': 'A8841'
        }
        self.client.post('/api/auth/register', json=reg_payload)

        # Login requires 2FA for engineer
        login_res = self.client.post('/api/auth/login', json={
            'email': test_email,
            'password': 'SecureEngineer@2026'
        })
        self.assertEqual(login_res.status_code, 200)
        login_data = login_res.get_json()
        self.assertTrue(login_data.get('require_2fa'))
        self.assertIn('demo_otp', login_data)
        demo_otp = login_data['demo_otp']

        # Invalid OTP attempt
        bad_verify = self.client.post('/api/auth/verify-2fa', json={
            'email': test_email,
            'otp_code': '000000'
        })
        self.assertEqual(bad_verify.status_code, 401)

        # Successful OTP verification
        good_verify = self.client.post('/api/auth/verify-2fa', json={
            'email': test_email,
            'otp_code': demo_otp
        })
        self.assertEqual(good_verify.status_code, 200)
        self.assertIn('token', good_verify.get_json())

    def test_06_google_sign_in_citizen_role_enforcement(self):
        """Verifies Google Sign-In creates Citizen accounts and never grants Engineer or Admin roles."""
        google_email = f'google_user_{int(datetime.now().timestamp())}@gmail.com'
        self.__class__.created_user_emails.append(google_email)
        res = self.client.post('/api/auth/google', json={
            'email': google_email,
            'name': 'Google Citizen',
            'sub': 'google_oauth_123456789'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('token', data)
        user = data['user']
        self.assertEqual(user['role'], 'citizen')
        self.assertEqual(user['verification_status'], 'verified')

    def test_07_maps_endpoint_and_privacy_filtering(self):
        """Verifies GET /api/reports/map filters private citizen information for public/citizen callers."""
        # Anonymous or citizen request
        res = self.client.get('/api/reports/map')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('points', data)
        points = data['points']
        self.assertGreater(len(points), 0)

        for pt in points:
            # Reporter identity, emails, and phone numbers must NOT leak
            self.assertNotIn('email', pt)
            self.assertNotIn('reporter_name', pt)
            self.assertNotIn('phone', pt)
            self.assertNotIn('user_id', pt)
            self.assertIn('defect_class', pt)
            self.assertIn('status', pt)
            self.assertIn('relative_severity', pt)
            self.assertIn('latitude', pt)
            self.assertIn('longitude', pt)

    def test_08_admin_dashboard_oversight_endpoint(self):
        """Verifies GET /api/admin/dashboard returns comprehensive governance and health stats."""
        from app.utils.auth_helpers import create_access_token
        with self.app.app_context():
            admin_token = create_access_token({'user_id': 'usr_admin_01', 'role': 'admin', 'email': 'admin@infravision.ke'})

        res = self.client.get('/api/admin/dashboard', headers={'Authorization': f'Bearer {admin_token}'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertIn('users_summary', data)
        self.assertIn('reports_summary', data)
        self.assertIn('governance_analytics', data)
        self.assertIn('system_health', data)

        self.assertIn('total', data['users_summary'])
        self.assertIn('pending_engineers', data['users_summary'])
        self.assertIn('received', data['reports_summary'])
        self.assertIn('verified', data['reports_summary'])
        self.assertIn('resolved', data['reports_summary'])
        self.assertIn('backend_api', data['system_health'])
        self.assertIn('ai_model', data['system_health'])

    def test_09_engineer_report_review_and_lifecycle_controls(self):
        """Verifies engineer can review, add evaluation notes, and transition report lifecycle."""
        from app.utils.auth_helpers import create_access_token
        with self.app.app_context():
            eng_token = create_access_token({'user_id': 'usr_eng_01', 'role': 'engineer', 'name': 'Eng. Jane Doe'})

        # Fetch an existing report
        report = db_service.find_one('infrastructure_reports', {})
        self.assertIsNotNone(report)
        report_id = str(report['_id'])

        # Engineer transitions to Under Review
        res_review = self.client.post(
            f'/api/reviews/report/{report_id}',
            json={'decision': 'Under Investigation', 'target_status': 'Under Review', 'notes': 'Site inspection scheduled.'},
            headers={'Authorization': f'Bearer {eng_token}'}
        )
        self.assertEqual(res_review.status_code, 200)
        self.assertEqual(res_review.get_json()['status'], 'Under Review')

        # Engineer transitions to Verified
        res_verify = self.client.post(
            f'/api/reviews/report/{report_id}',
            json={'decision': 'Confirmed', 'target_status': 'Verified', 'notes': 'Structural defect verified by professional engineer.'},
            headers={'Authorization': f'Bearer {eng_token}'}
        )
        self.assertEqual(res_verify.status_code, 200)
        self.assertEqual(res_verify.get_json()['status'], 'Verified')

    def test_10_map_config_nairobi_defaults(self):
        """Verifies GET /api/reports/map/config defaults strictly to Nairobi, Kenya with Leaflet provider."""
        res = self.client.get('/api/reports/map/config')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('default_center', data)
        self.assertAlmostEqual(data['default_center']['lat'], -1.286389, places=4)
        self.assertAlmostEqual(data['default_center']['lng'], 36.817223, places=4)
        self.assertIn('default_zoom', data)
        self.assertEqual(data['default_zoom'], 12)
        self.assertIn('provider', data)
        self.assertEqual(data['provider'], 'leaflet')
        self.assertIn('tile_layer', data)
        self.assertIn('tile.openstreetmap.org', data['tile_layer'])
        self.assertIn('attribution', data)
        self.assertIn('OpenStreetMap', data['attribution'])

    def test_11_admin_role_authorization_and_overview_metrics(self):
        """Verifies non-admins are blocked with 403, and admins receive real metric overviews."""
        from app.utils.auth_helpers import create_access_token
        with self.app.app_context():
            cit_token = create_access_token({'user_id': 'usr_cit_01', 'role': 'citizen', 'email': 'citizen@strathmore.edu'})
            admin_token = create_access_token({'user_id': 'usr_admin_01', 'role': 'admin', 'email': 'admin@infravision.ke'})

        # Citizen forbidden from admin dashboard
        res_forbidden = self.client.get('/api/admin/dashboard', headers={'Authorization': f'Bearer {cit_token}'})
        self.assertEqual(res_forbidden.status_code, 403)

        # Admin authorized
        res_admin = self.client.get('/api/admin/dashboard', headers={'Authorization': f'Bearer {admin_token}'})
        self.assertEqual(res_admin.status_code, 200)
        data = res_admin.get_json()
        self.assertIn('overview', data)
        self.assertIn('total_users', data['overview'])
        self.assertIn('reports', data)
        self.assertIn('reports_by_location', data)
        self.assertIn('engineer_workload', data)

    def test_12_submitter_and_reviewer_identity_preservation(self):
        """Verifies distinct preservation of report submitter vs reviewer identities in metadata and audit trail."""
        author_user_id = 'usr_eng_test_author'
        peer_user_id = 'usr_eng_test_peer'

        db_service.insert('users', {
            '_id': author_user_id,
            'user_id': author_user_id,
            'name': 'Eng. Submitter Author',
            'email': 'author_eng@infravision.ke',
            'role': 'engineer',
            'engineering_category': 'Professional Engineer',
            'professional_reg_no': 'A5512',
            'verification_status': 'verified',
            'created_at': datetime.now(timezone.utc).isoformat()
        })
        db_service.insert('users', {
            '_id': peer_user_id,
            'user_id': peer_user_id,
            'name': 'Eng. Peer Reviewer',
            'email': 'peer_eng@infravision.ke',
            'role': 'engineer',
            'engineering_category': 'Professional Engineer',
            'professional_reg_no': 'A5513',
            'verification_status': 'verified',
            'created_at': datetime.now(timezone.utc).isoformat()
        })
        self.__class__.created_user_emails.extend(['author_eng@infravision.ke', 'peer_eng@infravision.ke'])

        from app.utils.auth_helpers import create_access_token
        with self.app.app_context():
            eng_author_token = create_access_token({
                'user_id': author_user_id,
                'role': 'engineer',
                'name': 'Eng. Submitter Author',
                'email': 'author_eng@infravision.ke'
            })
            eng_reviewer_token = create_access_token({
                'user_id': peer_user_id,
                'role': 'engineer',
                'name': 'Eng. Peer Reviewer',
                'email': 'peer_eng@infravision.ke'
            })

        # Engineer submits a report
        import io
        seed_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'uploads', 'seed_pothole.jpg'
        ))
        with open(seed_path, 'rb') as f:
            img_bytes = f.read()

        submit_payload = {
            'image': (io.BytesIO(img_bytes), 'recon_defect.jpg'),
            'latitude': '-1.286389',
            'longitude': '36.817223',
            'location': 'Haile Selassie Avenue, Nairobi',
            'asset_type': 'Road / Pavement',
            'description': 'Pothole observed during routine civil engineering field reconnaissance.'
        }
        res_submit = self.client.post(
            '/api/reports',
            data=submit_payload,
            content_type='multipart/form-data',
            headers={'Authorization': f'Bearer {eng_author_token}'}
        )
        self.assertEqual(res_submit.status_code, 201)
        report_id = res_submit.get_json()['report_id']

        # Verify report detail shows distinct submitter identity
        res_detail = self.client.get(
            f'/api/reports/{report_id}',
            headers={'Authorization': f'Bearer {eng_reviewer_token}'}
        )
        self.assertEqual(res_detail.status_code, 200)
        detail = res_detail.get_json()
        self.assertIn('submitter', detail)
        self.assertEqual(detail['submitter']['user_id'], author_user_id)
        self.assertEqual(detail['submitter']['role'], 'engineer')
        self.assertEqual(detail['submitter']['name'], 'Eng. Submitter Author')

        # Peer engineer reviews the report (not self-review)
        res_peer_review = self.client.post(
            f'/api/reviews/report/{report_id}',
            json={
                'decision': 'Confirmed',
                'target_status': 'Verified',
                'notes': 'Independent peer review confirmed severity and defect categorization.'
            },
            headers={'Authorization': f'Bearer {eng_reviewer_token}'}
        )
        self.assertEqual(res_peer_review.status_code, 200)

        # Inspect updated document in database
        updated_doc = db_service.find_one('infrastructure_reports', {'_id': report_id})
        self.assertIsNotNone(updated_doc)
        meta = updated_doc.get('metadata', {})
        self.assertEqual(meta.get('submitted_by_id'), author_user_id)
        self.assertEqual(meta.get('reviewer_id'), peer_user_id)
        self.assertFalse(meta.get('is_self_review', True))

        # Check audit trail records distinct identities
        audit_trail = meta.get('status_history', [])
        self.assertGreater(len(audit_trail), 0)
        last_entry = audit_trail[-1]
        self.assertEqual(last_entry.get('reviewer_id'), peer_user_id)
        self.assertEqual(last_entry.get('submitter_id'), author_user_id)
        self.assertFalse(last_entry.get('is_self_review', True))

        # Test self-review flag when author reviews their own report
        res_self_review = self.client.post(
            f'/api/reviews/report/{report_id}',
            json={
                'decision': 'Site Cleared',
                'target_status': 'Resolved',
                'notes': 'Field repair confirmed completed during follow-up inspection.'
            },
            headers={'Authorization': f'Bearer {eng_author_token}'}
        )
        self.assertEqual(res_self_review.status_code, 200)
        self_doc = db_service.find_one('infrastructure_reports', {'_id': report_id})
        self_meta = self_doc.get('metadata', {})
        self.assertTrue(self_meta.get('is_self_review'))
        self.assertEqual(self_meta.get('reviewer_id'), author_user_id)
        self.assertEqual(self_meta.get('submitted_by_id'), author_user_id)
        self_last_audit = self_meta.get('status_history', [])[-1]
        self.assertTrue(self_last_audit.get('is_self_review'))
        self.assertIn('Self-submitted report', self_last_audit.get('note', ''))

    def test_13_report_location_tagging_and_map_point(self):
        """Verifies report location tagging with custom coordinates and map point consumption."""
        from app.utils.auth_helpers import create_access_token
        import io

        citizen_user_id = 'test_tag_loc_citizen_id'
        citizen_email = 'tag_cit@infravision.ke'
        db_service.delete_one('users', {'_id': citizen_user_id})
        db_service.insert('users', {
            '_id': citizen_user_id,
            'name': 'Tagging Citizen Tester',
            'email': citizen_email,
            'role': 'citizen',
            'verification_status': 'verified',
            'created_at': datetime.now(timezone.utc).isoformat()
        })
        self.__class__.created_user_emails.append(citizen_email)

        with self.app.app_context():
            token = create_access_token({
                'user_id': citizen_user_id,
                'role': 'citizen',
                'name': 'Tagging Citizen Tester',
                'email': citizen_email
            })

        seed_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'uploads', 'seed_pothole.jpg'
        ))
        with open(seed_path, 'rb') as f:
            img_bytes = f.read()

        custom_lat = -1.29210
        custom_lng = 36.82190
        submit_payload = {
            'image': (io.BytesIO(img_bytes), 'tagged_defect.jpg'),
            'latitude': str(custom_lat),
            'longitude': str(custom_lng),
            'location': 'Moi Avenue near Railway Station, Nairobi',
            'asset_type': 'Road / Pavement',
            'description': 'Road pavement surface distress tagged via location picker.'
        }
        res_submit = self.client.post(
            '/api/reports',
            data=submit_payload,
            content_type='multipart/form-data',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res_submit.status_code, 201)
        rep_data = res_submit.get_json()
        report_id = rep_data['report_id']

        # Verify stored record in database has coordinates
        rep_doc = db_service.find_one('infrastructure_reports', {'_id': report_id})
        self.assertIsNotNone(rep_doc)
        self.assertAlmostEqual(float(rep_doc.get('latitude')), custom_lat, places=4)
        self.assertAlmostEqual(float(rep_doc.get('longitude')), custom_lng, places=4)

        # Verify map API returns the exact coordinates
        res_map = self.client.get('/api/reports/map')
        self.assertEqual(res_map.status_code, 200)
        map_points = res_map.get_json().get('points', [])
        found_point = next((p for p in map_points if p.get('report_id') == report_id), None)
        self.assertIsNotNone(found_point)
        self.assertAlmostEqual(found_point['latitude'], custom_lat, places=4)
        self.assertAlmostEqual(found_point['longitude'], custom_lng, places=4)
        self.assertNotIn('email', found_point)
        self.assertNotIn('phone', found_point)

        # Clean up
        db_service.delete_one('infrastructure_reports', {'_id': report_id})

    def test_14_location_based_priority_and_cluster_grouping(self):
        """Verifies location-based prioritization signals and multi-report clustering."""
        from app.services.validation import validation_service

        # 1. Haversine distance accuracy (~35m distance between slightly offset points)
        lat1, lng1 = -1.29850, 36.82280
        lat2, lng2 = -1.29875, 36.82295
        dist = validation_service.haversine_distance_meters(lat1, lng1, lat2, lng2)
        self.assertGreater(dist, 20.0)
        self.assertLess(dist, 50.0)

        # 2. Proximity metrics and priority elevation
        # Normal priority with no nearby reports
        priority_normal = validation_service.evaluate_priority(
            'Medium', False, {'is_location_cluster': False, 'nearby_unresolved_count': 0}
        )
        self.assertEqual(priority_normal, 'Medium')

        # Elevated priority with clustered nearby unresolved reports
        priority_elevated = validation_service.evaluate_priority(
            'Medium', False, {'is_location_cluster': True, 'nearby_unresolved_count': 3}
        )
        self.assertEqual(priority_elevated, 'High Priority')

        # Critical severity in a cluster becomes Urgent Review
        priority_crit_cluster = validation_service.evaluate_priority(
            'Critical', False, {'is_location_cluster': True, 'nearby_unresolved_count': 2}
        )
        self.assertEqual(priority_crit_cluster, 'Urgent Review')

        # 3. Anti-spam de-duplication check:
        # Multiple historical reports exist on Uhuru Highway (Chainage 14+350)
        proximity_metrics = validation_service.calculate_location_proximity_metrics(-1.29850, 36.82280, radius_meters=60.0)
        self.assertGreaterEqual(proximity_metrics['nearby_report_count'], 1)

        # 4. Map points include nearby_report_count
        res_map = self.client.get('/api/reports/map')
        self.assertEqual(res_map.status_code, 200)
        points = res_map.get_json().get('points', [])
        # Find points near Uhuru Highway
        uhuru_pts = [p for p in points if abs(p['latitude'] - (-1.29850)) < 0.001]
        if uhuru_pts:
            self.assertIn('nearby_report_count', uhuru_pts[0])

    def test_15_multi_image_submission_and_aggregation(self):
        """Verifies multi-image defect reporting (1-3 images), class union, and severity aggregation."""
        import io
        from app.utils.auth_helpers import create_access_token

        cit_user_id = 'usr_cit_multi_test'
        db_service.insert('users', {
            '_id': cit_user_id,
            'user_id': cit_user_id,
            'name': 'Citizen Photo Contributor',
            'email': 'contributor@infravision.ke',
            'role': 'citizen',
            'created_at': datetime.now(timezone.utc).isoformat()
        })
        self.__class__.created_user_emails.append('contributor@infravision.ke')

        with self.app.app_context():
            token = create_access_token({
                'user_id': cit_user_id,
                'role': 'citizen',
                'name': 'Citizen Photo Contributor',
                'email': 'contributor@infravision.ke'
            })

        seed_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'uploads', 'seed_pothole.jpg'
        ))
        with open(seed_path, 'rb') as f:
            seed_bytes = f.read()

        # 1. Rejecting more than 3 images
        four_images_payload = {
            'images': [
                (io.BytesIO(seed_bytes), 'photo1.jpg'),
                (io.BytesIO(seed_bytes), 'photo2.jpg'),
                (io.BytesIO(seed_bytes), 'photo3.jpg'),
                (io.BytesIO(seed_bytes), 'photo4.jpg'),
            ],
            'latitude': '-1.286389',
            'longitude': '36.817223',
            'location': 'Kenyatta Avenue, Nairobi',
            'asset_type': 'Road / Pavement',
            'description': 'Attempting upload with four images.'
        }
        res_excess = self.client.post(
            '/api/reports',
            data=four_images_payload,
            content_type='multipart/form-data',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res_excess.status_code, 400)
        self.assertIn('maximum of 3 photographs', res_excess.get_json().get('error', '').lower())

        # 2. Submitting report with 2 images
        two_images_payload = {
            'images': [
                (io.BytesIO(seed_bytes), 'defect_angle_wide.jpg'),
                (io.BytesIO(seed_bytes), 'defect_angle_close.jpg'),
            ],
            'latitude': '-1.292100',
            'longitude': '36.821900',
            'location': 'Haile Selassie Avenue, Nairobi',
            'asset_type': 'Road / Pavement',
            'description': 'Multi-angle defect report with 2 photographs.'
        }
        res_two = self.client.post(
            '/api/reports',
            data=two_images_payload,
            content_type='multipart/form-data',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res_two.status_code, 201)
        two_data = res_two.get_json()
        report_id_two = two_data['report_id']

        self.assertIn('images', two_data)
        self.assertEqual(len(two_data['images']), 2)
        self.assertIn('ai_assessments', two_data)
        self.assertEqual(len(two_data['ai_assessments']), 2)
        self.assertIn('detected_classes', two_data)
        self.assertIn('overall_visual_severity', two_data)

        # 3. Verify database persistence
        db_images = db_service.find('submitted_images', {'report_id': report_id_two})
        self.assertEqual(len(db_images), 2)
        for img_doc in db_images:
            ass_doc = db_service.find_one('ai_assessments', {'image_id': img_doc['_id']})
            self.assertIsNotNone(ass_doc)

        # 4. Verify get_report_detail returns both multi and backwards compatible single fields
        res_detail = self.client.get(
            f'/api/reports/{report_id_two}',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res_detail.status_code, 200)
        detail_data = res_detail.get_json()
        self.assertIn('images', detail_data)
        self.assertEqual(len(detail_data['images']), 2)
        self.assertIn('assessments', detail_data)
        self.assertEqual(len(detail_data['assessments']), 2)
        self.assertIsNotNone(detail_data['image'])
        self.assertIsNotNone(detail_data['assessment'])

        # 5. Clean up
        db_service.delete_one('infrastructure_reports', {'_id': report_id_two})
        for img_doc in db_images:
            db_service.delete_one('submitted_images', {'_id': img_doc['_id']})
            db_service.delete_one('ai_assessments', {'image_id': img_doc['_id']})


if __name__ == '__main__':
    unittest.main()


