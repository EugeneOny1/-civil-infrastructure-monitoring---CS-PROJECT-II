import os
import unittest
from datetime import datetime, timezone
from backend.app import create_app
from backend.app.services.database import db_service
from backend.app.utils.auth_helpers import create_access_token


class EmergencyFixTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()

        # Seed test verified engineer
        cls.engineer_id = 'eng_test_emergency_01'
        db_service.delete_many('users', {'_id': cls.engineer_id})
        user_doc = {
            '_id': cls.engineer_id,
            'email': 'engineer.emergency@example.com',
            'role': 'engineer',
            'verification_status': 'verified',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        db_service.insert('users', user_doc)
        with cls.app.app_context():
            cls.engineer_token = create_access_token(user_doc)

        cls.counties_47 = [
            "Mombasa", "Kwale", "Kilifi", "Tana River", "Lamu", "Taita Taveta", "Garissa",
            "Wajir", "Mandera", "Marsabit", "Isiolo", "Meru", "Tharaka Nithi", "Embu",
            "Kitui", "Machakos", "Makueni", "Nyandarua", "Nyeri", "Kirinyaga", "Murang'a",
            "Kiambu", "Turkana", "West Pokot", "Samburu", "Trans Nzoia", "Uasin Gishu",
            "Elgeyo Marakwet", "Nandi", "Baringo", "Laikipia", "Nakuru", "Narok", "Kajiado",
            "Kericho", "Bomet", "Kakamega", "Vihiga", "Bungoma", "Busia", "Siaya",
            "Kisumu", "Homa Bay", "Migori", "Kisii", "Nyamira", "Nairobi"
        ]

    @classmethod
    def tearDownClass(cls):
        db_service.delete_many('users', {'_id': cls.engineer_id})

    def test_01_vihiga_zero_data_trends_and_insights(self):
        """Verifies that querying a zero-data county like Vihiga returns HTTP 200 and safe zero structures."""
        headers = {'Authorization': f'Bearer {self.engineer_token}'}
        resp = self.client.get('/api/analytics/trends?range=6m&county=Vihiga&ward=all', headers=headers)
        self.assertEqual(resp.status_code, 200, "Vihiga trends query must return HTTP 200")
        data = resp.get_json()

        self.assertIn('trend_data', data)
        self.assertIn('summary', data)
        self.assertIn('monitoring_insights', data)

        # In zero-data state, has_sufficient_data must be False, total must be 0
        self.assertFalse(data.get('has_sufficient_data'), "Zero data county must report has_sufficient_data as False")
        self.assertEqual(data['summary'].get('total_reports'), 0, "Total reports for zero-data county must be 0")
        self.assertEqual(data['summary'].get('critical_reports_count'), 0)

        # Monitoring insights should safely report insufficient data
        insights = data['monitoring_insights']
        self.assertFalse(insights.get('has_sufficient_data'))
        self.assertIn("Not enough historical data", insights.get('message', ''))

    def test_02_vihiga_zero_data_critical_calendar(self):
        """Verifies that critical reports calendar returns HTTP 200 with 0 critical reports for Vihiga."""
        headers = {'Authorization': f'Bearer {self.engineer_token}'}
        resp = self.client.get('/api/analytics/critical-calendar?range=6m&county=Vihiga&ward=all', headers=headers)
        self.assertEqual(resp.status_code, 200, "Vihiga calendar query must return HTTP 200")
        data = resp.get_json()

        self.assertEqual(data.get('total_critical_reports'), 0, "Vihiga critical count must be 0")
        self.assertIsInstance(data.get('days'), list, "Days should be a continuous list")
        for day in data.get('days', []):
            self.assertEqual(day.get('count'), 0, "Day count must be 0 in zero-data county")

    def test_03_all_47_counties_analytics_safety(self):
        """Tests that every single one of Kenya's 47 counties executes without an unhandled server exception."""
        headers = {'Authorization': f'Bearer {self.engineer_token}'}
        self.assertEqual(len(self.counties_47), 47, "Must test exactly 47 counties")

        failed_counties = []
        for county in self.counties_47:
            with self.subTest(county=county):
                resp_trends = self.client.get(f'/api/analytics/trends?range=6m&county={county}&ward=all', headers=headers)
                if resp_trends.status_code != 200:
                    failed_counties.append((county, 'trends', resp_trends.status_code))

                resp_cal = self.client.get(f'/api/analytics/critical-calendar?range=6m&county={county}&ward=all', headers=headers)
                if resp_cal.status_code != 200:
                    failed_counties.append((county, 'calendar', resp_cal.status_code))

        self.assertEqual(len(failed_counties), 0, f"Some counties triggered exceptions: {failed_counties}")

    def test_04_recovery_vihiga_to_nairobi(self):
        """Tests that querying Vihiga (zero data) and then querying Nairobi (populated) works seamlessly."""
        headers = {'Authorization': f'Bearer {self.engineer_token}'}

        # Query Vihiga
        resp_v = self.client.get('/api/analytics/trends?range=6m&county=Vihiga&ward=all', headers=headers)
        self.assertEqual(resp_v.status_code, 200)
        data_v = resp_v.get_json()
        self.assertEqual(data_v['summary'].get('total_reports'), 0)

        # Query Nairobi
        resp_n = self.client.get('/api/analytics/trends?range=6m&county=Nairobi&ward=all', headers=headers)
        self.assertEqual(resp_n.status_code, 200)
        data_n = resp_n.get_json()
        self.assertGreater(data_n['summary'].get('total_reports'), 0, "Nairobi should have populated reports")
        self.assertTrue(data_n.get('has_sufficient_data'))

    def test_05_map_advisory_and_report_overlap_contract(self):
        """Verifies that active safety advisories maintain report_id linking and coordinate fidelity."""
        headers = {'Authorization': f'Bearer {self.engineer_token}'}
        resp = self.client.get('/api/reports/map', headers=headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        points = data.get('points', [])
        advisories = data.get('safety_advisories', [])

        # If advisories exist, check that coordinate integrity is preserved
        for adv in advisories:
            self.assertIn('latitude', adv)
            self.assertIn('longitude', adv)
            self.assertIsNotNone(adv['latitude'])
            self.assertIsNotNone(adv['longitude'])
            if adv.get('report_id'):
                # Report ID is preserved for linking
                self.assertTrue(len(str(adv['report_id'])) > 0)

    def test_06_frontend_map_clustering_and_composite_tokens(self):
        """Verifies map.js contains zoom-dependent clustering, composite marker, and context popup logic."""
        map_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'map.js'))
        with open(map_js_path, 'r', encoding='utf-8') as f:
            js = f.read()

        # Section 14: Zoom-dependent clustering rules
        self.assertIn("maxClusterRadius", js)
        self.assertIn("zoom >= 16", js)
        self.assertIn("disableClusteringAtZoom: 16", js)

        # Section 21 & 22: Composite marker & context popup
        self.assertIn("createCombinedPopupContent", js)
        self.assertIn("composite-advisory-badge", js)
        self.assertIn("openReportDetails", js)
        self.assertIn("_has_composite_marker", js)

    def test_07_frontend_dashboard_zero_data_safety(self):
        """Verifies dashboard.js contains safe empty-state rendering without destroying containers."""
        dash_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'dashboard.js'))
        with open(dash_js_path, 'r', encoding='utf-8') as f:
            js = f.read()

        # No canvas-placeholder in dashboard.js
        self.assertNotIn("canvas-placeholder", js, "dashboard.js must NEVER use canvas-placeholder")
        # In-flow queue empty state
        self.assertIn("queue-empty-state", js)
        self.assertIn("No reports match the selected filters.", js)
        # Safe chart handling
        self.assertIn("getTrendChartOptions", js)


if __name__ == '__main__':
    unittest.main()
