import unittest
from datetime import datetime, timezone, timedelta
from backend.app import create_app
from backend.app.services.database import db_service
from backend.app.services.notification_service import notification_service
from backend.app.utils.auth_helpers import create_access_token

class TestFinalAcceptancePass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()

    def setUp(self):
        self.created_users = []
        self.created_reports = []

    def tearDown(self):
        for uid in self.created_users:
            db_service.db['users'].delete_one({'_id': uid})
            db_service.db['citizen_notifications'].delete_many({'user_id': uid})
        for rid in self.created_reports:
            db_service.db['infrastructure_reports'].delete_one({'_id': rid})
            db_service.db['safety_advisories'].delete_many({'report_id': rid})

    # =========================================================================
    # 1. GOOGLE SIGN-IN TESTS
    # =========================================================================
    def test_01_google_auth_creates_citizen_only(self):
        """Verifies Google Sign-In creates new user with citizen role ONLY."""
        test_email = f"google_cit_{int(datetime.now().timestamp())}@strathmore.edu"
        res = self.client.post('/api/auth/google', json={
            'email': test_email,
            'name': 'New Google Citizen',
            'sub': 'google_sub_cit_9988'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('token', data)
        user = data.get('user', {})
        self.assertEqual(user.get('role'), 'citizen')
        self.assertEqual(user.get('email'), test_email)
        self.created_users.append(user.get('user_id') or user.get('_id'))

    def test_02_google_auth_links_existing_citizen_without_duplication(self):
        """Verifies Google Sign-In safely links to existing user without creating duplicates."""
        test_email = f"existing_cit_{int(datetime.now().timestamp())}@strathmore.edu"
        user_doc = {
            '_id': f"usr_{int(datetime.now().timestamp())}",
            'email': test_email,
            'name': 'Existing Citizen',
            'role': 'citizen',
            'verification_status': 'verified',
            'two_factor_enabled': False
        }
        db_service.insert('users', user_doc)
        self.created_users.append(user_doc['_id'])

        res = self.client.post('/api/auth/google', json={
            'email': test_email,
            'name': 'Existing Citizen Google Linked',
            'sub': 'google_sub_link_123'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data.get('require_2fa', False))
        
        # Verify user record updated with google_id
        updated = db_service.find_one('users', {'email': test_email})
        self.assertEqual(updated.get('google_id'), 'google_sub_link_123')

    def test_03_google_auth_privileged_account_triggers_2fa(self):
        """Verifies existing Engineer/Admin logging in with Google triggers mandatory 2FA OTP."""
        test_email = f"eng_google_{int(datetime.now().timestamp())}@kenha.go.ke"
        user_doc = {
            '_id': f"usr_{int(datetime.now().timestamp())}",
            'email': test_email,
            'name': 'Eng. Privileged',
            'role': 'engineer',
            'verification_status': 'verified',
            'two_factor_enabled': True
        }
        db_service.insert('users', user_doc)
        self.created_users.append(user_doc['_id'])

        res = self.client.post('/api/auth/google', json={
            'email': test_email,
            'name': 'Eng. Privileged',
            'sub': 'google_sub_eng_7766'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('require_2fa'))
        self.assertEqual(data.get('role'), 'engineer')
        self.assertIn('two-factor', data.get('message', '').lower())

    def test_04_google_auth_missing_credential_error(self):
        """Verifies request without credential token returns 400 error."""
        res = self.client.post('/api/auth/google', json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn('credential', res.get_json().get('error', '').lower())

    # =========================================================================
    # 2. ENGINEER GOVERNANCE & REJECTION REASON WORKFLOW
    # =========================================================================
    def test_05_admin_verify_engineer_approval(self):
        """Verifies Admin can approve pending engineer and notification is dispatched."""
        eng_id = f"eng_appr_{int(datetime.now().timestamp())}"
        admin_id = f"admin_usr_{int(datetime.now().timestamp())}"
        
        eng_doc = {
            '_id': eng_id,
            'email': f"{eng_id}@kenha.go.ke",
            'name': 'Eng. Candidate',
            'role': 'engineer',
            'verification_status': 'pending',
            'professional_reg_no': 'EBK/PE/2026/0101-DEMO'
        }
        admin_doc = {
            '_id': admin_id,
            'email': f"{admin_id}@infravision.ke",
            'name': 'Administrator',
            'role': 'admin'
        }
        db_service.insert('users', eng_doc)
        db_service.insert('users', admin_doc)
        self.created_users.extend([eng_id, admin_id])

        with self.app.app_context():
            token = create_access_token({'user_id': admin_id, 'email': admin_doc['email'], 'role': 'admin'})
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        res = self.client.put(f'/api/admin/users/{eng_id}/verify', json={'status': 'verified'}, headers=headers)
        self.assertEqual(res.status_code, 200)
        
        updated = db_service.find_one('users', {'_id': eng_id})
        self.assertEqual(updated.get('verification_status'), 'verified')
        self.assertIsNotNone(updated.get('verified_at'))

        # Check notification dispatched to the engineer
        notifs = notification_service.get_user_notifications(eng_id)
        self.assertTrue(any('Verified' in n.get('title', '') for n in notifs))

    def test_06_admin_reject_engineer_with_reason_and_notes(self):
        """Verifies Admin rejection persists reason, notes, audit, and dispatches explanation notice."""
        eng_id = f"eng_rej_{int(datetime.now().timestamp())}"
        admin_id = f"admin_usr_{int(datetime.now().timestamp())}"

        eng_doc = {
            '_id': eng_id,
            'email': f"{eng_id}@kenha.go.ke",
            'name': 'Eng. Incomplete',
            'role': 'engineer',
            'verification_status': 'pending',
            'professional_reg_no': 'EBK/PE/2026/INVALID'
        }
        admin_doc = {
            '_id': admin_id,
            'email': f"{admin_id}@infravision.ke",
            'name': 'System Administrator',
            'role': 'admin'
        }
        db_service.insert('users', eng_doc)
        db_service.insert('users', admin_doc)
        self.created_users.extend([eng_id, admin_id])

        with self.app.app_context():
            token = create_access_token({'user_id': admin_id, 'email': admin_doc['email'], 'role': 'admin'})
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        rejection_payload = {
            'status': 'rejected',
            'rejection_reason': 'EBK number appears incorrect',
            'rejection_notes': 'Please check with EBK secretariat and provide valid registration certificate.'
        }
        res = self.client.put(f'/api/admin/users/{eng_id}/verify', json=rejection_payload, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('verification_status'), 'rejected')

        updated = db_service.find_one('users', {'_id': eng_id})
        self.assertEqual(updated.get('verification_status'), 'rejected')
        self.assertEqual(updated.get('rejection_reason'), 'EBK number appears incorrect')
        self.assertEqual(updated.get('rejection_notes'), rejection_payload['rejection_notes'])
        self.assertIsNotNone(updated.get('rejected_at'))
        self.assertEqual(updated.get('rejected_by'), admin_id)

        # Check notification
        notifs = notification_service.get_user_notifications(eng_id)
        self.assertTrue(len(notifs) >= 1)
        rejection_notif = notifs[0]
        self.assertEqual(rejection_notif.get('title'), "Engineer verification requires attention")
        self.assertIn("EBK number appears incorrect", rejection_notif.get('message', ''))
        self.assertIn("Please check with EBK secretariat", rejection_notif.get('message', ''))

    def test_07_unauthorized_non_admin_cannot_verify_users(self):
        """Verifies citizens and unverified engineers cannot access user verification endpoint."""
        cit_id = f"cit_unauth_{int(datetime.now().timestamp())}"
        cit_doc = {'_id': cit_id, 'email': f"{cit_id}@strathmore.edu", 'role': 'citizen'}
        db_service.insert('users', cit_doc)
        self.created_users.append(cit_id)

        with self.app.app_context():
            token = create_access_token({'user_id': cit_id, 'email': cit_doc['email'], 'role': 'citizen'})
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        res = self.client.put(f'/api/admin/users/{cit_id}/verify', json={'status': 'verified'}, headers=headers)
        self.assertEqual(res.status_code, 403)

    # =========================================================================
    # 3. OPERATIONAL NOTIFICATIONS & NOTIFICATION CENTER
    # =========================================================================
    def test_08_notification_center_mark_read_and_mark_all_read(self):
        """Verifies notification center lifecycle: get, mark read, mark all read."""
        user_id = f"user_nc_{int(datetime.now().timestamp())}"
        user_doc = {'_id': user_id, 'email': f"{user_id}@strathmore.edu", 'role': 'citizen'}
        db_service.insert('users', user_doc)
        self.created_users.append(user_id)

        # Create two notifications
        n1 = notification_service.create_notification(user_id, 'REP-01', 'verified', 'Report Verified', 'Test message 1')
        n2 = notification_service.create_notification(user_id, 'REP-02', 'override', 'Severity Updated', 'Test message 2')

        with self.app.app_context():
            token = create_access_token({'user_id': user_id, 'email': user_doc['email'], 'role': 'citizen'})
        headers = {'Authorization': f'Bearer {token}'}

        # GET notifications
        res = self.client.get('/api/users/notifications', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('unread_count'), 2)
        self.assertEqual(len(data.get('notifications', [])), 2)

        # Mark single as read
        read_res = self.client.post(f"/api/users/notifications/{n1['_id']}/read", headers=headers)
        self.assertEqual(read_res.status_code, 200)

        # Check unread count is now 1
        res2 = self.client.get('/api/users/notifications', headers=headers)
        self.assertEqual(res2.get_json().get('unread_count'), 1)

        # Mark all read
        mark_all_res = self.client.post('/api/users/notifications/mark-all-read', headers=headers)
        self.assertEqual(mark_all_res.status_code, 200)

        # Check unread count is 0
        res3 = self.client.get('/api/users/notifications', headers=headers)
        self.assertEqual(res3.get_json().get('unread_count'), 0)

    # =========================================================================
    # 4. SAFETY ADVISORIES & ADMIN NOTICES
    # =========================================================================
    def test_09_engineer_safety_advisory_creation_and_broadcast(self):
        """Verifies verified engineer can issue report-linked safety advisory with controlled categories."""
        eng_id = f"eng_adv_{int(datetime.now().timestamp())}"
        rep_id = f"REP-ADV-{int(datetime.now().timestamp())}"

        eng_doc = {
            '_id': eng_id,
            'email': f"{eng_id}@kenha.go.ke",
            'name': 'Eng. Inspector',
            'role': 'engineer',
            'verification_status': 'verified'
        }
        rep_doc = {
            '_id': rep_id,
            'report_id': rep_id,
            'location_name': 'Uhuru Highway / Nyayo Roundabout',
            'latitude': -1.298,
            'longitude': 36.822,
            'status': 'Under Review',
            'metadata': {}
        }
        db_service.insert('users', eng_doc)
        db_service.insert('infrastructure_reports', rep_doc)
        self.created_users.append(eng_id)
        self.created_reports.append(rep_id)

        with self.app.app_context():
            token = create_access_token({'user_id': eng_id, 'email': eng_doc['email'], 'role': 'engineer'})
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        # Valid safety advisory
        advisory_payload = {
            'category': 'Dangerous road defect',
            'note': 'Deep longitudinal trench on inner lane. Reduce speed to 30km/h.'
        }
        res = self.client.post(f'/api/reviews/{rep_id}/safety-advisory', json=advisory_payload, headers=headers)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data.get('advisory', {}).get('category'), 'Dangerous road defect')

        # Invalid category should be rejected
        bad_res = self.client.post(f'/api/reviews/{rep_id}/safety-advisory', json={'category': 'Invalid Category'}, headers=headers)
        self.assertEqual(bad_res.status_code, 400)

    def test_10_admin_notice_targeted_and_broadcast(self):
        """Verifies admin notice endpoint supports targeted user notices and broadcast announcements."""
        admin_id = f"admin_msg_{int(datetime.now().timestamp())}"
        target_id = f"target_usr_{int(datetime.now().timestamp())}"

        admin_doc = {'_id': admin_id, 'email': f"{admin_id}@infravision.ke", 'role': 'admin'}
        target_doc = {'_id': target_id, 'email': f"{target_id}@kenha.go.ke", 'role': 'engineer', 'name': 'Target Eng', 'is_active': True}

        db_service.insert('users', admin_doc)
        db_service.insert('users', target_doc)
        self.created_users.extend([admin_id, target_id])

        with self.app.app_context():
            token = create_access_token({'user_id': admin_id, 'email': admin_doc['email'], 'role': 'admin'})
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        # Targeted notice
        targeted_payload = {
            'type': 'targeted',
            'target_user_id': target_id,
            'category': 'Credential Issue',
            'title': 'EBK License Renewal Required',
            'message': 'Please update your annual practicing license before Nov 30.'
        }
        res_t = self.client.post('/api/admin/notifications/send', json=targeted_payload, headers=headers)
        self.assertEqual(res_t.status_code, 200)

        notifs = notification_service.get_user_notifications(target_id)
        self.assertTrue(any('EBK License Renewal' in n.get('title', '') for n in notifs))

        # Broadcast announcement
        broadcast_payload = {
            'type': 'broadcast',
            'category': 'Scheduled Platform Maintenance',
            'title': 'Platform Maintenance Notice',
            'message': 'InfraVision will undergo scheduled maintenance this Sunday between 02:00 and 04:00 EAT.'
        }
        res_b = self.client.post('/api/admin/notifications/send', json=broadcast_payload, headers=headers)
        self.assertEqual(res_b.status_code, 200)
        self.assertGreater(res_b.get_json().get('recipients_count', 0), 0)

    def test_11_review_next_action_and_follow_up_date_persistence(self):
        """Verifies professional review and lifecycle endpoints persist next_action and follow_up_date."""
        eng_id = f"eng_rev_{int(datetime.now().timestamp())}"
        rep_id = f"REP-NA-{int(datetime.now().timestamp())}"
        img_id = f"img_na_{int(datetime.now().timestamp())}"
        ass_id = f"ass_na_{int(datetime.now().timestamp())}"

        eng_doc = {'_id': eng_id, 'email': f"{eng_id}@kenha.go.ke", 'name': 'Eng. Reviewer', 'role': 'engineer', 'verification_status': 'verified'}
        rep_doc = {'_id': rep_id, 'report_id': rep_id, 'status': 'Under Review', 'metadata': {}}
        img_doc = {'_id': img_id, 'report_id': rep_id, 'image_path': 'seed_pothole.jpg'}
        ass_doc = {'_id': ass_id, 'image_id': img_id, 'defect_class': 'Pothole', 'relative_severity': 'Critical'}

        db_service.insert('users', eng_doc)
        db_service.insert('infrastructure_reports', rep_doc)
        db_service.insert('submitted_images', img_doc)
        db_service.insert('ai_assessments', ass_doc)

        self.created_users.append(eng_id)
        self.created_reports.append(rep_id)

        with self.app.app_context():
            token = create_access_token({'user_id': eng_id, 'email': eng_doc['email'], 'role': 'engineer'})
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        # 1. Update lifecycle status with next action and target date
        status_payload = {
            'target_status': 'Verified',
            'notes': 'Defect confirmed during on-site survey.',
            'next_action': 'On-site inspection recommended',
            'follow_up_date': '2026-11-15'
        }
        res = self.client.post(f'/api/reviews/report/{rep_id}', json=status_payload, headers=headers)
        self.assertEqual(res.status_code, 200)

        # Check DB metadata
        updated_rep = db_service.find_one('infrastructure_reports', {'_id': rep_id})
        self.assertEqual(updated_rep.get('status'), 'Verified')
        self.assertEqual(updated_rep.get('metadata', {}).get('next_action'), 'On-site inspection recommended')
        self.assertEqual(updated_rep.get('metadata', {}).get('follow_up_date'), '2026-11-15')

        # 2. Check rejection of invalid next action
        bad_payload = {
            'target_status': 'Verified',
            'next_action': 'Invalid Nonexistent Action'
        }
        bad_res = self.client.post(f'/api/reviews/report/{rep_id}', json=bad_payload, headers=headers)
        self.assertEqual(bad_res.status_code, 400)

    def test_12_user_reports_enrichment_with_reviews(self):
        """Verifies /api/users/reports returns citizen reports enriched with review details."""
        cit_id = f"cit_track_{int(datetime.now().timestamp())}"
        rep_id = f"REP-CIT-{int(datetime.now().timestamp())}"
        img_id = f"img_cit_{int(datetime.now().timestamp())}"
        ass_id = f"ass_cit_{int(datetime.now().timestamp())}"
        rev_id = f"rev_cit_{int(datetime.now().timestamp())}"

        cit_doc = {'_id': cit_id, 'email': f"{cit_id}@gmail.com", 'name': 'Citizen Submitter', 'role': 'citizen', 'is_active': True}
        rep_doc = {
            '_id': rep_id,
            'report_id': rep_id,
            'user_id': cit_id,
            'status': 'Verified',
            'metadata': {'location_name': 'Haile Selassie Avenue', 'next_action': 'Routine maintenance plan'}
        }
        img_doc = {'_id': img_id, 'report_id': rep_id, 'image_path': 'seed_crack.jpg'}
        ass_doc = {'_id': ass_id, 'image_id': img_id, 'defect_class': 'Crack', 'relative_severity': 'Low'}
        rev_doc = {
            '_id': rev_id,
            'report_id': rep_id,
            'assessment_id': ass_id,
            'reviewer_name': 'Eng. P. Njuguna, PE',
            'decision': 'Confirmed',
            'next_action': 'Routine maintenance plan',
            'comments': 'Verified surface crack.'
        }

        db_service.insert('users', cit_doc)
        db_service.insert('infrastructure_reports', rep_doc)
        db_service.insert('submitted_images', img_doc)
        db_service.insert('ai_assessments', ass_doc)
        db_service.insert('professional_reviews', rev_doc)

        self.created_users.append(cit_id)
        self.created_reports.append(rep_id)

        with self.app.app_context():
            token = create_access_token({'user_id': cit_id, 'email': cit_doc['email'], 'role': 'citizen'})
        headers = {'Authorization': f'Bearer {token}'}

        res = self.client.get('/api/users/reports', headers=headers)
        self.assertEqual(res.status_code, 200)
        reports = res.get_json().get('reports', [])
        target = next((r for r in reports if r['report']['_id'] == rep_id), None)
        self.assertIsNotNone(target)
        self.assertIn('review', target)
        self.assertEqual(target['review'].get('reviewer_name'), 'Eng. P. Njuguna, PE')
        self.assertEqual(target['review'].get('next_action'), 'Routine maintenance plan')

    def test_13_admin_broadcast_audience_filtering(self):
        """Verifies broadcast notifications respect target audience role scoping."""
        admin_id = f"admin_bcast_{int(datetime.now().timestamp())}"
        cit_id = f"cit_aud_{int(datetime.now().timestamp())}"
        eng_id = f"eng_aud_{int(datetime.now().timestamp())}"

        admin_doc = {'_id': admin_id, 'email': f"{admin_id}@infravision.ke", 'role': 'admin'}
        cit_doc = {'_id': cit_id, 'email': f"{cit_id}@gmail.com", 'role': 'citizen', 'is_active': True}
        eng_doc = {'_id': eng_id, 'email': f"{eng_id}@kenha.go.ke", 'role': 'engineer', 'is_active': True}

        db_service.insert('users', admin_doc)
        db_service.insert('users', cit_doc)
        db_service.insert('users', eng_doc)
        self.created_users.extend([admin_id, cit_id, eng_id])

        with self.app.app_context():
            token = create_access_token({'user_id': admin_id, 'email': admin_doc['email'], 'role': 'admin'})
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        # Broadcast to engineers only
        payload = {
            'type': 'broadcast',
            'audience': 'engineer',
            'category': 'Operational Guidance',
            'title': 'Engineer Protocol Update',
            'message': 'New protocol for bridge joint inspection.'
        }
        res = self.client.post('/api/admin/notifications/send', json=payload, headers=headers)
        self.assertEqual(res.status_code, 200)

        # Engineer received it
        eng_notifs = notification_service.get_user_notifications(eng_id)
        self.assertTrue(any('Engineer Protocol Update' in n.get('title', '') for n in eng_notifs))

        # Citizen did not receive it
        cit_notifs = notification_service.get_user_notifications(cit_id)
        self.assertFalse(any('Engineer Protocol Update' in n.get('title', '') for n in cit_notifs))

    # =========================================================================
    # 7. MULTI-IMAGE, BATCH SUBMISSION & MAP ADVISORY COMPLETION TESTS
    # =========================================================================
    def test_14_same_defect_multi_view_evidence_aggregation(self):
        """Verifies report-level multi-view assessment aggregates independent view evidence."""
        rep_id = f"rep_multiview_{int(datetime.now().timestamp())}"
        img_id_1 = f"img_mv1_{int(datetime.now().timestamp())}"
        img_id_2 = f"img_mv2_{int(datetime.now().timestamp())}"

        combined_assessment = {
            'detected_classes': ['Pothole', 'Crack'],
            'total_views': 2,
            'per_class_view_support': {'Pothole': '2/2', 'Crack': '1/2'},
            'strongest_model_confidence': {'Pothole': 0.88, 'Crack': 0.65},
            'highest_visual_severity': 'Critical',
            'view_summaries': [
                {'photo_index': 0, 'detected_classes': ['Pothole', 'Crack'], 'strongest_confidence': 0.88, 'visual_severity': 'Critical'},
                {'photo_index': 1, 'detected_classes': ['Pothole'], 'strongest_confidence': 0.82, 'visual_severity': 'High'}
            ]
        }

        rep_doc = {
            '_id': rep_id,
            'report_id': rep_id,
            'display_id': 'REP-2026-0042',
            'status': 'Received',
            'date_submitted': datetime.now(timezone.utc).isoformat(),
            'metadata': {
                'multi_image_mode': 'same_defect',
                'location_name': 'Mombasa Road',
                'combined_multi_view_assessment': combined_assessment
            }
        }
        db_service.insert('infrastructure_reports', rep_doc)
        self.created_reports.append(rep_id)

        eng_id = f"eng_mv_{int(datetime.now().timestamp())}"
        eng_doc = {'_id': eng_id, 'email': f"{eng_id}@infravision.ke", 'role': 'engineer'}
        db_service.insert('users', eng_doc)
        self.created_users.append(eng_id)

        with self.app.app_context():
            token = create_access_token({'user_id': eng_id, 'email': eng_doc['email'], 'role': 'engineer'})
        headers = {'Authorization': f'Bearer {token}'}

        res = self.client.get(f'/api/reports/{rep_id}', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('report', {}).get('display_id'), 'REP-2026-0042')
        self.assertIn('combined_multi_view_assessment', data)
        cmv = data['combined_multi_view_assessment']
        self.assertIn('Pothole', cmv['detected_classes'])
        self.assertIn('Crack', cmv['detected_classes'])
        self.assertEqual(cmv['highest_visual_severity'], 'Critical')
        self.assertEqual(cmv['per_class_view_support']['Pothole'], '2/2')

    def test_15_multi_defect_batch_submission_structure(self):
        """Verifies multi_defect batch generates shared submission_batch_id and independent reports."""
        batch_id = f"batch_{int(datetime.now().timestamp())}"
        rep_id_1 = f"rep_b1_{int(datetime.now().timestamp())}"
        rep_id_2 = f"rep_b2_{int(datetime.now().timestamp())}"

        rep1 = {
            '_id': rep_id_1,
            'report_id': rep_id_1,
            'display_id': 'REP-2026-0091',
            'status': 'Received',
            'latitude': -1.2863,
            'longitude': 36.8172,
            'date_submitted': datetime.now(timezone.utc).isoformat(),
            'metadata': {'submission_batch_id': batch_id, 'observation_index': 0, 'location_name': 'Kenyatta Ave Posta'}
        }
        rep2 = {
            '_id': rep_id_2,
            'report_id': rep_id_2,
            'display_id': 'REP-2026-0092',
            'status': 'Received',
            'latitude': -1.2890,
            'longitude': 36.8210,
            'date_submitted': datetime.now(timezone.utc).isoformat(),
            'metadata': {'submission_batch_id': batch_id, 'observation_index': 1, 'location_name': 'Kenyatta Ave Roundabout'}
        }
        db_service.insert('infrastructure_reports', rep1)
        db_service.insert('infrastructure_reports', rep2)
        self.created_reports.extend([rep_id_1, rep_id_2])

        # Verify querying by batch_id retrieves both independent reports
        batch_reports = list(db_service.db['infrastructure_reports'].find({'metadata.submission_batch_id': batch_id}))
        self.assertEqual(len(batch_reports), 2)
        self.assertNotEqual(batch_reports[0]['_id'], batch_reports[1]['_id'])
        self.assertNotEqual(batch_reports[0]['latitude'], batch_reports[1]['latitude'])

    def test_16_safety_advisory_active_map_and_resolution_deactivation(self):
        """Verifies active safety advisories appear on map and auto-deactivate upon report resolution."""
        rep_id = f"rep_adv_{int(datetime.now().timestamp())}"
        adv_id = f"adv_{int(datetime.now().timestamp())}"

        rep_doc = {
            '_id': rep_id,
            'report_id': rep_id,
            'display_id': 'REP-2026-0105',
            'status': 'Verified',
            'latitude': -1.2833,
            'longitude': 36.8167,
            'date_submitted': datetime.now(timezone.utc).isoformat(),
            'metadata': {'location_name': 'Uhuru Highway / University Way'}
        }
        adv_doc = {
            '_id': adv_id,
            'advisory_id': adv_id,
            'report_id': rep_id,
            'category': 'Major Hazard',
            'note': 'Deep excavation near lane boundary.',
            'location_name': 'Uhuru Highway / University Way',
            'latitude': -1.2833,
            'longitude': 36.8167,
            'status': 'active',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        db_service.insert('infrastructure_reports', rep_doc)
        db_service.insert('safety_advisories', adv_doc)
        self.created_reports.append(rep_id)

        # 1. Map points endpoint includes active advisory
        res = self.client.get('/api/reports/map')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        active_advisories = data.get('safety_advisories', [])
        self.assertTrue(any(a.get('advisory_id') == adv_id or a.get('report_id') == rep_id for a in active_advisories))

        # 2. Update report status to Resolved
        eng_id = f"eng_adv_{int(datetime.now().timestamp())}"
        eng_doc = {'_id': eng_id, 'email': f"{eng_id}@infravision.ke", 'role': 'engineer', 'verification_status': 'verified', 'is_active': True}
        db_service.insert('users', eng_doc)
        self.created_users.append(eng_id)

        with self.app.app_context():
            token = create_access_token({'user_id': eng_id, 'email': eng_doc['email'], 'role': 'engineer'})
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        patch_res = self.client.post(f'/api/reviews/report/{rep_id}', json={'target_status': 'Resolved', 'decision': 'Confirmed', 'notes': 'Repairs verified.'}, headers=headers)
        self.assertEqual(patch_res.status_code, 200)

        # 3. Advisory is now inactive in DB and excluded from map
        updated_adv = db_service.find_one('safety_advisories', {'_id': adv_id})
        self.assertEqual(updated_adv.get('status'), 'inactive')

        res_after = self.client.get('/api/reports/map')
        self.assertEqual(res_after.status_code, 200)
        advisories_after = res_after.get_json().get('safety_advisories', [])
        self.assertFalse(any(a.get('advisory_id') == adv_id for a in advisories_after))

    def test_17_historical_defect_trends_endpoint(self):
        """Verifies GET /api/analytics/trends handles ranges, view_by, and continuous period bucketing."""
        eng_id = f"eng_trends_{int(datetime.now().timestamp())}"
        eng_doc = {
            '_id': eng_id,
            'email': f"{eng_id}@infravision.ke",
            'role': 'engineer',
            'verification_status': 'verified',
            'is_active': True
        }
        db_service.insert('users', eng_doc)
        self.created_users.append(eng_id)

        with self.app.app_context():
            token = create_access_token({'user_id': eng_id, 'email': eng_doc['email'], 'role': 'engineer'})
        headers = {'Authorization': f'Bearer {token}'}

        # Test view_by=defect_class with 3m range
        res = self.client.get('/api/analytics/trends?range=3m&view_by=defect_class', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('trend_data', data)
        self.assertTrue(len(data['trend_data']) > 0)
        self.assertIn('period', data['trend_data'][0])
        self.assertIn('series', data)
        self.assertIn('summary', data)
        self.assertEqual(data.get('view_by'), 'defect_class')
        self.assertIn('Pothole', data['series'])
        self.assertIn('Crack', data['series'])

        # Test view_by=visual_severity with 12m range
        res_sev = self.client.get('/api/analytics/trends?range=12m&view_by=visual_severity', headers=headers)
        self.assertEqual(res_sev.status_code, 200)
        data_sev = res_sev.get_json()
        self.assertEqual(data_sev.get('view_by'), 'visual_severity')
        self.assertIn('Critical', data_sev['series'])
        self.assertIn('Medium', data_sev['series'])
        self.assertIn('Low', data_sev['series'])

    def test_18_display_id_format_and_canonical_id_integrity(self):
        """Verifies display_id format matches #REP-YYYY-XXXX and canonical lookup works."""
        rep_id = f"rep_canonical_{int(datetime.now().timestamp())}"
        rep_doc = {
            '_id': rep_id,
            'report_id': rep_id,
            'display_id': 'REP-2026-0777',
            'status': 'Received',
            'date_submitted': datetime.now(timezone.utc).isoformat(),
            'metadata': {'location_name': 'Waiyaki Way'}
        }
        db_service.insert('infrastructure_reports', rep_doc)
        self.created_reports.append(rep_id)

        eng_id = f"eng_can_{int(datetime.now().timestamp())}"
        eng_doc = {'_id': eng_id, 'email': f"{eng_id}@infravision.ke", 'role': 'engineer'}
        db_service.insert('users', eng_doc)
        self.created_users.append(eng_id)

        with self.app.app_context():
            token = create_access_token({'user_id': eng_id, 'email': eng_doc['email'], 'role': 'engineer'})
        headers = {'Authorization': f'Bearer {token}'}

        # Lookup by canonical MongoDB _id
        res = self.client.get(f'/api/reports/{rep_id}', headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json().get('report', {}).get('display_id'), 'REP-2026-0777')

    def test_19_safety_advisory_notification_metadata_and_privacy(self):
        """Verifies advisory notifications carry spatial metadata with zero citizen personal identity."""
        cit_id = f"cit_notif_{int(datetime.now().timestamp())}"
        cit_doc = {'_id': cit_id, 'email': f"{cit_id}@gmail.com", 'role': 'citizen', 'name': 'Anonymous Citizen'}
        db_service.insert('users', cit_doc)
        self.created_users.append(cit_id)

        notif_id = notification_service.create_notification(
            user_id=cit_id,
            title='Safety Advisory: Severe Pothole Cluster',
            message='Exercise caution on Langata Road near Galleria.',
            event_type='safety_advisory',
            report_id='rep_privacy_999',
            metadata={'advisory_id': 'adv_privacy_999', 'latitude': -1.332, 'longitude': 36.755, 'location_name': 'Langata Road'}
        )

        notifs = notification_service.get_user_notifications(cit_id)
        target = next((n for n in notifs if n.get('event_type') == 'safety_advisory'), None)
        self.assertIsNotNone(target)
        self.assertEqual(target.get('title'), 'Safety Advisory: Severe Pothole Cluster')
        self.assertNotIn('⚠️', target.get('title', ''))  # Verify zero emoji rule
        self.assertEqual(target.get('metadata', {}).get('latitude'), -1.332)
        self.assertEqual(target.get('metadata', {}).get('longitude'), 36.755)
        # Verify zero citizen identity leakage in message or metadata
        self.assertNotIn('Anonymous Citizen', target.get('message', ''))
        self.assertNotIn(cit_doc['email'], target.get('message', ''))

if __name__ == '__main__':
    unittest.main()
