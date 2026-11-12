"""
Test suite for InfraVision Final Lifecycle, Engineer Workflow, Collaboration,
Resolution Guard, Geographic Hierarchy, and Building Reporting.
"""

import os
import io
import unittest
from backend.app import create_app
from backend.app.services.database import db_service
from backend.app.utils.auth_helpers import create_access_token
from backend.app.services.geography_service import geography_service


from PIL import Image


def get_test_image():
    buf = io.BytesIO()
    img = Image.new('RGB', (100, 100), color=(128, 128, 128))
    img.save(buf, format='JPEG')
    buf.seek(0)
    return buf


class TestFinalLifecycleAndWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['TESTING'] = 'True'
        cls.app = create_app('testing')
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()

        # Set up Lead Engineer
        cls.engineer_user = db_service.find_one('users', {'email': 'regina@kenha.co.ke'})
        if not cls.engineer_user:
            cls.engineer_user = {
                'email': 'regina@kenha.co.ke',
                'name': 'Eng. Regina',
                'role': 'engineer',
                'is_verified': True,
                'verification_status': 'verified'
            }
            res_id = db_service.insert('users', cls.engineer_user)
            cls.engineer_user['_id'] = res_id
        else:
            db_service.update_one('users', {'_id': cls.engineer_user['_id']}, {'verification_status': 'verified'})
            cls.engineer_user['verification_status'] = 'verified'

        # Set up Collaborating Engineer
        cls.collaborator_user = db_service.find_one('users', {'email': 'daniel.mwangi@kenha.co.ke'})
        if not cls.collaborator_user:
            cls.collaborator_user = {
                'email': 'daniel.mwangi@kenha.co.ke',
                'name': 'Eng. Daniel Mwangi',
                'role': 'engineer',
                'is_verified': True,
                'verification_status': 'verified',
                'engineering_category': 'Structural Engineer'
            }
            res_id = db_service.insert('users', cls.collaborator_user)
            cls.collaborator_user['_id'] = res_id
        else:
            db_service.update_one('users', {'_id': cls.collaborator_user['_id']}, {'verification_status': 'verified'})
            cls.collaborator_user['verification_status'] = 'verified'

        # Set up Admin
        cls.admin_user = db_service.find_one('users', {'role': 'admin'})
        if not cls.admin_user:
            cls.admin_user = {
                'email': 'admin@infravision.ke',
                'name': 'System Administrator',
                'role': 'admin',
                'is_verified': True,
                'verification_status': 'verified'
            }
            res_id = db_service.insert('users', cls.admin_user)
            cls.admin_user['_id'] = res_id
        else:
            db_service.update_one('users', {'_id': cls.admin_user['_id']}, {'verification_status': 'verified'})
            cls.admin_user['verification_status'] = 'verified'

        with cls.app.app_context():
            cls.engineer_token = create_access_token(cls.engineer_user)
            cls.admin_token = create_access_token(cls.admin_user)

    def test_01_geography_service_and_hierarchy_api(self):
        """Verify GeographyService loads 47 counties and cascading hierarchy API works."""
        counties = geography_service.get_all_counties()
        self.assertEqual(len(counties), 47, f"Expected 47 Kenya counties, found {len(counties)}")

        # Check hierarchy API for all counties
        res = self.client.get('/api/analytics/geography/hierarchy', headers={
            'Authorization': f"Bearer {self.engineer_token}"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('total_counties'), 47)
        c_list = data.get('counties', [])
        county_names = [c['name'] for c in c_list]
        self.assertIn('Nairobi', county_names)
        self.assertIn('Mombasa', county_names)
        self.assertIn('Kisumu', county_names)

        # Check cascading hierarchy for Nairobi
        res_nairobi = self.client.get('/api/analytics/geography/hierarchy?county=Nairobi', headers={
            'Authorization': f"Bearer {self.engineer_token}"
        })
        self.assertEqual(res_nairobi.status_code, 200)
        nairobi_data = res_nairobi.get_json()
        self.assertEqual(nairobi_data.get('county'), 'Nairobi')
        self.assertTrue(len(nairobi_data.get('constituencies', [])) > 0)
        self.assertTrue(len(nairobi_data.get('wards', [])) > 0)

    def test_02_analytics_kpi_operational_accuracy(self):
        """Verify operational KPIs: active_defect_queue counts Received, critical_received is accurate."""
        res = self.client.get('/api/analytics/summary', headers={
            'Authorization': f"Bearer {self.engineer_token}"
        })
        self.assertEqual(res.status_code, 200)
        summary = res.get_json()

        # active_defect_queue must be an integer count of Received reports
        self.assertIn('active_defect_queue', summary)
        self.assertIsInstance(summary['active_defect_queue'], int)

        # critical_received_count must reflect Received reports with severity Critical (real count, NOT historical 45)
        self.assertIn('critical_received_count', summary)
        self.assertLessEqual(summary['critical_received_count'], summary['active_defect_queue'])

        # my_lead_cases must exist
        self.assertIn('my_lead_cases', summary)
        self.assertIsInstance(summary['my_lead_cases'], int)

    def test_03_building_report_floors_validation(self):
        """Verify submission requires positive integer for building floors when asset is Building."""
        citizen_user = db_service.find_one('users', {'role': 'citizen'}) or self.engineer_user
        with self.app.app_context():
            token = create_access_token(citizen_user)

        # Negative floors should fail
        res_bad = self.client.post('/api/reports', data={
            'asset_type': 'Building',
            'latitude': '-1.286389',
            'longitude': '36.817223',
            'location': 'Test Building Tower',
            'building_floors': '-3',
            'images': (get_test_image(), 'test_crack.jpg')
        }, content_type='multipart/form-data', headers={'Authorization': f"Bearer {token}"})

        self.assertEqual(res_bad.status_code, 400)
        data_bad = res_bad.get_json()
        self.assertIn('positive whole number', data_bad.get('error', '').lower())

        # Valid floors should succeed
        res_good = self.client.post('/api/reports', data={
            'asset_type': 'Building',
            'latitude': '-1.286389',
            'longitude': '36.817223',
            'location': 'Test Building Tower',
            'building_floors': '7',
            'images': (get_test_image(), 'test_crack.jpg')
        }, content_type='multipart/form-data', headers={'Authorization': f"Bearer {token}"})

        self.assertIn(res_good.status_code, (200, 201))
        rep_data = res_good.get_json().get('report', {})
        self.assertEqual(rep_data.get('metadata', {}).get('building_floors'), 7)

    def test_04_canonical_lifecycle_and_resolution_guard(self):
        """
        Test the canonical lifecycle transitions:
        Received -> Verified -> Under Review -> Resolved
        And verify that Resolution Guard blocks premature resolution.
        """
        eng_id = str(self.engineer_user.get('_id') or self.engineer_user.get('user_id'))

        # 1. Create a fresh test report in 'Received' status
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        test_report = {
            'description': 'Pavement distress test case for lifecycle verification',
            'status': 'Received',
            'date_submitted': now_iso,
            'asset_type': 'Road / Pavement',
            'location_name': 'Waiyaki Way Test Section',
            'latitude': -1.2650,
            'longitude': 36.8050,
            'metadata': {
                'asset_type': 'Road / Pavement',
                'relative_severity': 'Critical',
                'defect_class': 'Pothole'
            }
        }
        report_id = db_service.insert('infrastructure_reports', test_report)

        try:
            # 2. Cannot skip straight from Received to Resolved
            res_skip = self.client.patch(f'/api/reports/{report_id}/status', json={
                'status': 'Resolved',
                'reason': 'Premature skip'
            }, headers={'Authorization': f"Bearer {self.engineer_token}"})
            self.assertEqual(res_skip.status_code, 400)

            # 3. Transition Received -> Verified (via Engineer review or status update)
            res_verify = self.client.patch(f'/api/reports/{report_id}/status', json={
                'status': 'Verified',
                'reason': 'Defect confirmed by accredited engineer'
            }, headers={'Authorization': f"Bearer {self.engineer_token}"})
            self.assertEqual(res_verify.status_code, 200)
            self.assertEqual(res_verify.get_json()['report']['status'], 'Verified')

            # Check lead engineer was assigned
            rep_verified = db_service.find_one('infrastructure_reports', {'_id': report_id})
            lead_info = rep_verified['metadata'].get('current_lead_engineer') or rep_verified['metadata'].get('lead_engineer')
            self.assertIsNotNone(lead_info)
            self.assertEqual(lead_info['user_id'], eng_id)

            # 4. Transition Verified -> Under Review (Start Inspection)
            res_start = self.client.patch(f'/api/reports/{report_id}/status', json={
                'status': 'Under Review',
                'reason': 'Detailed field inspection initiated'
            }, headers={'Authorization': f"Bearer {self.engineer_token}"})
            self.assertEqual(res_start.status_code, 200)
            self.assertEqual(res_start.get_json()['report']['status'], 'Under Review')

            # 5. Attempt to Resolve without completing Inspection Notebook checklist (Resolution Guard should BLOCK)
            res_premature_resolve = self.client.patch(f'/api/reports/{report_id}/status', json={
                'status': 'Resolved',
                'reason': 'Trying to resolve without checklist completion'
            }, headers={'Authorization': f"Bearer {self.engineer_token}"})
            self.assertEqual(res_premature_resolve.status_code, 400)
            err_msg = res_premature_resolve.get_json().get('error', '').lower()
            self.assertTrue('cannot resolve' in err_msg or 'checklist' in err_msg or 'pending' in err_msg)

            # 6. Complete all objectives or justify with N/A reason
            rep_under_rev = db_service.find_one('infrastructure_reports', {'_id': report_id})
            notebook = rep_under_rev['metadata'].get('inspection_notebook', {})
            checklist = notebook.get('checklist', [])
            self.assertTrue(len(checklist) > 0, "Inspection notebook checklist template should be initialized")

            # Mark all items as completed except one marked N/A with rationale
            for i, item in enumerate(checklist):
                if i == len(checklist) - 1:
                    item['status'] = 'not_applicable'
                    item['is_na'] = True
                    item['na_reason'] = 'Site is dry; subterranean drainage not present on this corridor'
                    item['completed'] = False
                else:
                    item['status'] = 'completed'
                    item['completed'] = True
                    item['completed_by'] = 'Eng. Regina'
                    item['completed_at'] = now_iso

            # Save completed notebook
            res_save_nb = self.client.post(f'/api/reviews/report/{report_id}/inspection-notebook', json={
                'checklist': checklist,
                'note_cards': [{
                    'category': 'Observation',
                    'text': 'Pothole depth 14cm; requires immediate hot-mix asphalt patching.',
                    'author': 'Eng. Regina'
                }]
            }, headers={'Authorization': f"Bearer {self.engineer_token}"})
            self.assertEqual(res_save_nb.status_code, 200)

            # 7. Now resolve with proper summary note (Resolution Guard should PASS)
            res_resolve = self.client.patch(f'/api/reports/{report_id}/status', json={
                'status': 'Resolved',
                'reason': 'Hot-mix asphalt patch completed and compacted to standard. Quality checked by Lead Engineer.'
            }, headers={'Authorization': f"Bearer {self.engineer_token}"})
            self.assertEqual(res_resolve.status_code, 200)
            self.assertEqual(res_resolve.get_json()['report']['status'], 'Resolved')

        finally:
            # Cleanup test report
            db_service.delete_one('infrastructure_reports', {'_id': report_id})

    def test_05_engineer_collaboration_and_lead_transfer(self):
        """
        Test available engineers listing, inviting collaborators, and transferring Lead Engineer.
        """
        eng_id = str(self.engineer_user.get('_id') or self.engineer_user.get('user_id'))

        # Create active test case in 'Under Review'
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        test_report = {
            'description': 'Collaboration test case',
            'status': 'Under Review',
            'date_submitted': now_iso,
            'asset_type': 'Road / Pavement',
            'metadata': {
                'lead_engineer': {
                    'user_id': eng_id,
                    'name': self.engineer_user.get('name', 'Eng. Regina'),
                    'email': self.engineer_user.get('email', 'regina@kenha.co.ke')
                },
                'current_lead_engineer': {
                    'user_id': eng_id,
                    'name': self.engineer_user.get('name', 'Eng. Regina'),
                    'email': self.engineer_user.get('email', 'regina@kenha.co.ke')
                },
                'assigned_engineer_id': eng_id,
                'collaborators': []
            }
        }
        report_id = db_service.insert('infrastructure_reports', test_report)

        try:
            # 1. Fetch available engineers
            res_avail = self.client.get(f'/api/reviews/engineers/available?report_id={report_id}', headers={
                'Authorization': f"Bearer {self.engineer_token}"
            })
            self.assertEqual(res_avail.status_code, 200)
            engineers = res_avail.get_json().get('engineers', [])
            self.assertTrue(len(engineers) > 0, "Should have accredited engineers available for collaboration")

            other_eng = next((e for e in engineers if e.get('user_id') != eng_id), engineers[0])
            other_eng_id = other_eng.get('user_id')

            # 2. Invite collaborator
            res_invite = self.client.post(f'/api/reviews/report/{report_id}/collaborators', json={
                'engineer_id': other_eng_id,
                'role': 'Structural Specialist',
                'invite_note': 'Please assist with pavement distress assessment'
            }, headers={'Authorization': f"Bearer {self.engineer_token}"})
            self.assertIn(res_invite.status_code, (200, 201))
            self.assertEqual(len(res_invite.get_json().get('collaborators', [])), 1)

            # 3. Transfer Lead to other engineer (requires mandatory reason)
            res_transfer_no_reason = self.client.post(f'/api/reviews/report/{report_id}/transfer-lead', json={
                'new_lead_id': other_eng_id,
                'reason': ''
            }, headers={'Authorization': f"Bearer {self.engineer_token}"})
            self.assertEqual(res_transfer_no_reason.status_code, 400)

            res_transfer = self.client.post(f'/api/reviews/report/{report_id}/transfer-lead', json={
                'new_lead_id': other_eng_id,
                'reason': 'Geotechnical specialist expertise required for foundation subsidence'
            }, headers={'Authorization': f"Bearer {self.engineer_token}"})
            self.assertEqual(res_transfer.status_code, 200)
            trans_data = res_transfer.get_json()
            self.assertEqual(trans_data.get('lead_engineer', {}).get('user_id'), other_eng_id)

            # 4. Remove collaborator
            res_remove = self.client.delete(f'/api/reviews/report/{report_id}/collaborators/{eng_id}', headers={
                'Authorization': f"Bearer {self.admin_token}"
            })
            self.assertEqual(res_remove.status_code, 200)

        finally:
            # Cleanup
            db_service.delete_one('infrastructure_reports', {'_id': report_id})

    def test_06_verified_only_collaboration_invitations_and_notebook_conflict(self):
        """Verify invitations reject Citizens/unverified Engineers, support Accept/Reject, and enforce 409 conflicts."""
        import time
        ts = int(time.time())
        lead_id = f"eng_lead_c6_{ts}"
        peer_id = f"eng_peer_c6_{ts}"
        unverified_eng_id = f"eng_pend_c6_{ts}"
        cit_id = f"cit_c6_{ts}"
        rep_id = f"rep_c6_{ts}"

        db_service.insert('users', {
            '_id': lead_id, 'user_id': lead_id, 'name': 'Eng. Lead C6',
            'email': f'{lead_id}@kenha.ke', 'role': 'engineer', 'verification_status': 'verified'
        })
        db_service.insert('users', {
            '_id': peer_id, 'user_id': peer_id, 'name': 'Eng. Peer C6',
            'email': f'{peer_id}@kenha.ke', 'role': 'engineer', 'verification_status': 'verified'
        })
        db_service.insert('users', {
            '_id': unverified_eng_id, 'user_id': unverified_eng_id, 'name': 'Pending Eng',
            'email': f'{unverified_eng_id}@kenha.ke', 'role': 'engineer', 'verification_status': 'pending'
        })
        db_service.insert('users', {
            '_id': cit_id, 'user_id': cit_id, 'name': 'Citizen User',
            'email': f'{cit_id}@gmail.com', 'role': 'citizen', 'verification_status': 'verified'
        })
        db_service.insert('infrastructure_reports', {
            '_id': rep_id,
            'report_id': rep_id,
            'status': 'Verified',
            'metadata': {
                'assigned_engineer_id': lead_id,
                'current_lead_engineer': {'user_id': lead_id, 'name': 'Eng. Lead C6'},
                'collaborators': [],
                'inspection_notebook': {'checklist': [], 'note_cards': [], 'last_updated_at': '2026-11-12T07:00:00+00:00'}
            }
        })

        with self.app.app_context():
            lead_tok = create_access_token({'user_id': lead_id, 'role': 'engineer', 'name': 'Eng. Lead C6'})
            peer_tok = create_access_token({'user_id': peer_id, 'role': 'engineer', 'name': 'Eng. Peer C6'})

        try:
            # 1. Citizen and unverified engineer excluded from available list & rejected by invite endpoint
            avail = self.client.get('/api/reviews/engineers/available', headers={'Authorization': f'Bearer {lead_tok}'})
            self.assertEqual(avail.status_code, 200)
            avail_ids = {e['user_id'] for e in avail.get_json().get('engineers', [])}
            self.assertIn(peer_id, avail_ids)
            self.assertNotIn(unverified_eng_id, avail_ids)
            self.assertNotIn(cit_id, avail_ids)

            res_cit = self.client.post(f'/api/reviews/report/{rep_id}/collaborators', json={'engineer_id': cit_id}, headers={'Authorization': f'Bearer {lead_tok}'})
            self.assertEqual(res_cit.status_code, 400)

            res_unv = self.client.post(f'/api/reviews/report/{rep_id}/collaborators', json={'engineer_id': unverified_eng_id}, headers={'Authorization': f'Bearer {lead_tok}'})
            self.assertEqual(res_unv.status_code, 400)

            # 2. Verified peer invite starts with 'pending' status, then accepted
            res_inv = self.client.post(f'/api/reviews/report/{rep_id}/collaborators', json={'engineer_id': peer_id, 'role': 'Structural Engineer'}, headers={'Authorization': f'Bearer {lead_tok}'})
            self.assertEqual(res_inv.status_code, 201)
            self.assertEqual(res_inv.get_json()['collaborator']['invitation_status'], 'pending')

            res_acc = self.client.post(f'/api/reviews/report/{rep_id}/collaborators/respond', json={'response': 'accepted'}, headers={'Authorization': f'Bearer {peer_tok}'})
            self.assertEqual(res_acc.status_code, 200)
            self.assertEqual(res_acc.get_json()['collaborator']['invitation_status'], 'accepted')

            # 3. Notebook stale timestamp triggers 409 Conflict
            res_conf = self.client.post(
                f'/api/reviews/report/{rep_id}/inspection-notebook',
                json={'summary_notes': 'Stale edit', 'expected_updated_at': '2020-01-01T00:00:00+00:00'},
                headers={'Authorization': f'Bearer {peer_tok}'}
            )
            self.assertEqual(res_conf.status_code, 409)
            self.assertTrue(res_conf.get_json().get('conflict'))
        finally:
            db_service.delete_one('infrastructure_reports', {'_id': rep_id})
            for uid in (lead_id, peer_id, unverified_eng_id, cit_id):
                db_service.delete_one('users', {'_id': uid})


if __name__ == '__main__':
    unittest.main()
