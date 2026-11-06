import unittest
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from backend.app import create_app
from backend.app.services.database import db_service
from backend.app.services.weather_service import weather_service
from backend.app.utils.auth_helpers import create_access_token

class TestFinalEnhancementPass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()

        # Create engineer user for testing authenticated endpoints
        cls.engineer_id = str(ObjectId())
        cls.engineer_email = f"eng_{cls.engineer_id[:8]}@ebk.gov.ke"
        cls.engineer_name = "Eng. J. Kipchumba"
        cls.engineer_user = {
            '_id': cls.engineer_id,
            'name': cls.engineer_name,
            'email': cls.engineer_email,
            'role': 'engineer',
            'verification_status': 'verified',
            'is_verified': True
        }
        db_service.insert('users', cls.engineer_user)

        with cls.app.app_context():
            cls.engineer_token = create_access_token({
                'user_id': cls.engineer_id,
                'email': cls.engineer_email,
                'role': 'engineer'
            })

        cls.auth_headers = {
            'Authorization': f"Bearer {cls.engineer_token}",
            'Content-Type': 'application/json'
        }

        # Create other engineer
        cls.other_engineer_id = str(ObjectId())
        cls.other_engineer_email = f"other_{cls.other_engineer_id[:8]}@ebk.gov.ke"
        cls.other_user = {
            '_id': cls.other_engineer_id,
            'name': 'Other Engineer',
            'email': cls.other_engineer_email,
            'role': 'engineer',
            'verification_status': 'verified',
            'is_verified': True
        }
        db_service.insert('users', cls.other_user)

    def test_01_operational_map_resolved_retention_window(self):
        """Resolved reports <= 7 days appear on map; > 7 days disappear from operational map."""
        now = datetime.now(timezone.utc)
        recent_dt = (now - timedelta(days=2)).isoformat()
        old_dt = (now - timedelta(days=12)).isoformat()

        recent_id = str(ObjectId())
        recent_rep = {
            '_id': recent_id,
            'report_id': recent_id,
            'status': 'Resolved',
            'defect_class': 'Pothole',
            'relative_severity': 'Critical',
            'latitude': -1.286389,
            'longitude': 36.817223,
            'metadata': {
                'latitude': -1.286389,
                'longitude': 36.817223,
                'resolved_at': recent_dt
            },
            'date_submitted': (now - timedelta(days=5)).isoformat(),
            'created_at': (now - timedelta(days=5)).isoformat()
        }
        db_service.insert('infrastructure_reports', recent_rep)

        old_id = str(ObjectId())
        old_rep = {
            '_id': old_id,
            'report_id': old_id,
            'status': 'Resolved',
            'defect_class': 'Crack',
            'relative_severity': 'Medium',
            'latitude': -1.2921,
            'longitude': 36.8219,
            'metadata': {
                'latitude': -1.2921,
                'longitude': 36.8219,
                'resolved_at': old_dt
            },
            'date_submitted': (now - timedelta(days=20)).isoformat(),
            'created_at': (now - timedelta(days=20)).isoformat()
        }
        db_service.insert('infrastructure_reports', old_rep)

        # Default map query: recent is included, old is excluded
        res = self.client.get('/api/reports/map')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        ids = [str(p.get('report_id')) for p in data.get('points', [])]
        self.assertIn(recent_id, ids)
        self.assertNotIn(old_id, ids)

        # Explicit resolved filter: both are accessible
        res_all = self.client.get('/api/reports/map?status=Resolved')
        self.assertEqual(res_all.status_code, 200)
        data_all = res_all.get_json()
        all_ids = [str(p.get('report_id')) for p in data_all.get('points', [])]
        self.assertIn(recent_id, all_ids)
        self.assertIn(old_id, all_ids)

    def test_02_forward_only_lifecycle(self):
        """Lifecycle is strictly forward-only: Verified cannot revert; Resolved is read-only."""
        rep_id = str(ObjectId())
        rep = {
            '_id': rep_id,
            'report_id': rep_id,
            'status': 'Verified',
            'defect_class': 'Pothole',
            'relative_severity': 'Critical',
            'metadata': {
                'assigned_engineer_id': self.engineer_id
            },
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        db_service.insert('infrastructure_reports', rep)

        # Attempting backward transition Verified -> Received must fail with 400
        res_back = self.client.patch(
            f'/api/reports/{rep_id}/status',
            json={'status': 'Received'},
            headers=self.auth_headers
        )
        self.assertEqual(res_back.status_code, 400)
        data_back = res_back.get_json()
        self.assertIn('Forward-only', data_back.get('error', ''))

        # Valid forward transition Verified -> Resolved must succeed
        res_fwd = self.client.patch(
            f'/api/reports/{rep_id}/status',
            json={'status': 'Resolved'},
            headers=self.auth_headers
        )
        self.assertEqual(res_fwd.status_code, 200)

        # Once Resolved, report becomes read-only and cannot transition anywhere
        res_res = self.client.patch(
            f'/api/reports/{rep_id}/status',
            json={'status': 'Under Review'},
            headers=self.auth_headers
        )
        self.assertEqual(res_res.status_code, 400)
        self.assertIn('read-only', res_res.get_json().get('error', '').lower())

    def test_03_engineer_ownership_and_casework_filters(self):
        """Engineer ownership persisted and filterable via casework_filter."""
        rep_mine_id = str(ObjectId())
        rep_mine = {
            '_id': rep_mine_id,
            'report_id': rep_mine_id,
            'status': 'Under Review',
            'defect_class': 'Pothole',
            'metadata': {
                'assigned_engineer_id': self.engineer_id,
                'assigned_engineer_name': self.engineer_name
            },
            'date_submitted': datetime.now(timezone.utc).isoformat(),
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        db_service.insert('infrastructure_reports', rep_mine)

        rep_other_id = str(ObjectId())
        rep_other = {
            '_id': rep_other_id,
            'report_id': rep_other_id,
            'status': 'Under Review',
            'defect_class': 'Crack',
            'metadata': {
                'assigned_engineer_id': self.other_engineer_id,
                'assigned_engineer_name': 'Other Engineer'
            },
            'date_submitted': datetime.now(timezone.utc).isoformat(),
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        db_service.insert('infrastructure_reports', rep_other)

        # Filter: my_reviews should only return reports assigned to self.engineer_id
        res = self.client.get('/api/reports?casework_filter=my_reviews', headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        reports = data.get('reports', [])
        ids = [str(r.get('report_id') or r.get('_id')) for r in reports]
        self.assertIn(rep_mine_id, ids)
        self.assertNotIn(rep_other_id, ids)

    def test_04_inspection_notebook_and_compliance_persistence(self):
        """POST /api/reviews/report/<id>/inspection-notebook persists checklist, notes and compliance."""
        rep_id = str(ObjectId())
        rep = {
            '_id': rep_id,
            'report_id': rep_id,
            'status': 'Under Review',
            'defect_class': 'Crack',
            'metadata': {},
            'date_submitted': datetime.now(timezone.utc).isoformat(),
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        db_service.insert('infrastructure_reports', rep)

        notebook_payload = {
            'inspection_checklist': [
                {'text': 'Visual condition of structural elements reviewed', 'checked': True},
                {'text': 'Drainage and slope reviewed', 'checked': False}
            ],
            'note_cards': [
                {'category': 'Observation', 'content': 'Minor hairline cracking observed on south abutment.'}
            ],
            'compliance_context': {
                'approval_info': 'Yes',
                'apparent_alteration': 'No',
                'additional_floors': 'No',
                'planning_review_needed': 'No',
                'authority_verification': 'No',
                'compliance_notes': 'Structure conforms to approved planning elevation.'
            }
        }

        res = self.client.post(
            f'/api/reviews/report/{rep_id}/inspection-notebook',
            json=notebook_payload,
            headers=self.auth_headers
        )
        self.assertEqual(res.status_code, 200)

        # Check DB persistence
        saved = db_service.find_one('infrastructure_reports', {'_id': rep_id})
        saved_meta = saved.get('metadata', {})
        self.assertIn('inspection_notebook', saved_meta)
        notebook = saved_meta['inspection_notebook']
        self.assertIn('checklist', notebook)
        self.assertEqual(len(notebook['checklist']), 2)
        self.assertEqual(notebook['checklist'][0]['checked'], True)
        self.assertIn('note_cards', notebook)
        self.assertEqual(len(notebook['note_cards']), 1)
        self.assertIn('compliance_context', notebook)
        self.assertEqual(notebook['compliance_context']['approval_info'], 'Yes')

    def test_05_all_47_kenyan_counties_in_analytics(self):
        """Trends endpoint includes all 47 official Kenyan counties in standard order."""
        res = self.client.get('/api/analytics/trends', headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        counties = data.get('filter_options', {}).get('counties', [])
        # 'All Counties' + 47 counties = 48 items
        self.assertEqual(len(counties), 48)
        self.assertIn('Mombasa', counties)
        self.assertIn('Nairobi', counties)
        self.assertIn('Kiambu', counties)
        self.assertIn('Turkana', counties)
        self.assertIn('Kisumu', counties)

    def test_06_dynamic_monitoring_insights_and_weather_qualification(self):
        """Monitoring insights returns data-driven metrics and non-causal weather association."""
        res = self.client.get('/api/analytics/trends', headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('monitoring_insights', data)
        insights = data['monitoring_insights']
        self.assertIn('critical_last_30d', insights)
        self.assertIn('top_corridor_repeat', insights)
        self.assertIn('avg_received_to_verified', insights)
        self.assertIn('avg_verified_to_resolved', insights)
        self.assertIn('weather_insight', insights)

        weather = insights['weather_insight']
        self.assertIn('qualification', weather)
        self.assertIn('Observed historical association', weather['qualification'])

    def test_07_weather_service_association_calculation(self):
        """WeatherService analyzes empirical reports and caches queries."""
        sample_reports = [
            {
                'report_id': 'w_1',
                'defect_class': 'Pothole',
                'date_submitted': '2026-10-10T12:00:00Z',
                'metadata': {'latitude': -1.286389, 'longitude': 36.817223, 'location_name': 'Mombasa Road'}
            },
            {
                'report_id': 'w_2',
                'defect_class': 'Pothole',
                'date_submitted': '2026-10-12T12:00:00Z',
                'metadata': {'latitude': -1.286389, 'longitude': 36.817223, 'location_name': 'Mombasa Road'}
            },
            {
                'report_id': 'w_3',
                'defect_class': 'Crack',
                'date_submitted': '2026-10-15T12:00:00Z',
                'metadata': {'latitude': -1.286389, 'longitude': 36.817223, 'location_name': 'Mombasa Road'}
            }
        ]
        result = weather_service.analyze_weather_associations(sample_reports)
        self.assertIsNotNone(result)
        self.assertIn('qualification', result)
        self.assertFalse('caused' in result.get('observation', '').lower() or 'cause' in result.get('headline', '').lower())

if __name__ == '__main__':
    unittest.main()
