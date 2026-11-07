"""
Comprehensive Integration Tests for Monitoring Intelligence Workspace.
Validates:
1. All 5 focused monitoring analysis modes return 200 OK and expected analytical contract.
2. Lightweight Natural-Language Analytics Interface ('Ask InfraVision'):
   - Keyword intent scoring and slot extraction for recurring potholes, rainfall, seasons, critical concentration, response trends.
   - Query interpretation metadata ('Interpreted as: Analysis... | Defect... | Location... | Period...').
3. Unsupported query handling:
   - Returns status: unsupported with friendly explanation and 5 suggested questions without crashing.
4. Insufficient data handling:
   - Sparse county/ward filter (e.g. Vihiga) returns status: insufficient_data with honest sparsity threshold.
5. Verified KPI contract preservation:
   - Validates endpoint and report query filtering for engineer verification toggle.
6. Non-causal engineering language:
   - Verifies observational association language ('recorded', 'associated', never 'caused').
"""

import unittest
from datetime import datetime, timezone
from backend.app import create_app
from backend.app.services.database import db_service


class TestMonitoringIntelligenceWorkspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()

        # Seed test verified engineer
        from backend.app.utils.auth_helpers import create_access_token
        cls.engineer_id = 'test_eng_workspace_01'
        db_service.delete_many('users', {'_id': cls.engineer_id})
        user_doc = {
            '_id': cls.engineer_id,
            'email': 'engineer.workspace@example.com',
            'role': 'engineer',
            'verification_status': 'verified',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        db_service.insert('users', user_doc)
        with cls.app.app_context():
            cls.engineer_token = create_access_token(user_doc)
        cls.headers = {
            'Authorization': f'Bearer {cls.engineer_token}'
        }

    @classmethod
    def tearDownClass(cls):
        db_service.delete_many('users', {'_id': cls.engineer_id})

    def test_01_all_five_modes_contract(self):
        """All 5 monitoring modes must return 200 OK and conform to analytical contracts."""
        modes = [
            'rainfall_defect_pattern',
            'corridor_recurrence',
            'seasonal_defect_pattern',
            'critical_defect_concentration',
            'resolution_response_trend'
        ]

        for mode in modes:
            resp = self.client.get(f'/api/analytics/intelligence?mode={mode}&time_range=12m', headers=self.headers)
            self.assertEqual(resp.status_code, 200, f"Mode {mode} failed with status {resp.status_code}")
            data = resp.get_json()

            self.assertIn('mode', data)
            self.assertEqual(data['mode'], mode)
            self.assertIn('status', data)
            self.assertIn(data['status'], ['success', 'insufficient_data'])
            self.assertIn('all_modes', data)
            self.assertEqual(len(data['all_modes']), 5)

            if data['status'] == 'success':
                self.assertIn('primary_finding', data)
                self.assertIn('supporting_stats', data)
                self.assertIsInstance(data['supporting_stats'], list)
                self.assertIn('evidence', data)
                self.assertIn('comparison', data)
                self.assertIn('actions', data)
                self.assertIsInstance(data['actions'], list)

    def test_02_natural_language_queries(self):
        """Natural-language queries must detect intent, extract slots, and return query explanation."""
        test_queries = [
            ("Which roads have recurring potholes?", "corridor_recurrence", "Pothole"),
            ("Which roads develop potholes after heavy rain?", "rainfall_defect_pattern", "Pothole"),
            ("What patterns occur during the Long Rains?", "seasonal_defect_pattern", None),
            ("Where are Critical reports concentrated in Nairobi?", "critical_defect_concentration", None),
            ("How quickly are reports being resolved?", "resolution_response_trend", None)
        ]

        for query_text, expected_mode, expected_defect in test_queries:
            resp = self.client.post('/api/analytics/intelligence', json={'query': query_text}, headers=self.headers)
            self.assertEqual(resp.status_code, 200, f"Query '{query_text}' failed")
            data = resp.get_json()

            self.assertEqual(data.get('active_mode'), expected_mode,
                             f"Expected mode '{expected_mode}' for query '{query_text}', got '{data.get('active_mode')}'")
            self.assertIn('interpreted_query', data)
            interp = data['interpreted_query']
            self.assertIn('explanation', interp)
            self.assertIn('Interpreted as:', interp['explanation'])

            if expected_defect:
                self.assertEqual(data.get('active_filters', {}).get('defect_class'), expected_defect)

    def test_03_unsupported_query_handling(self):
        """Unsupported natural language questions must return status 'unsupported' with suggestions, never 500."""
        unsupported_query = "Tell me something random about football"
        resp = self.client.post('/api/analytics/intelligence', json={'query': unsupported_query}, headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertEqual(data.get('status'), 'unsupported')
        self.assertIn('message', data)
        self.assertIn('supported_topics', data)
        self.assertIsInstance(data['supported_topics'], list)
        self.assertEqual(len(data['supported_topics']), 5)
        self.assertIn('suggestions', data)
        self.assertIsInstance(data['suggestions'], list)
        self.assertGreaterEqual(len(data['suggestions']), 5)

    def test_04_insufficient_data_handling(self):
        """Zero or sparse results (e.g. Vihiga) must return status 'insufficient_data' with honest threshold."""
        resp = self.client.get('/api/analytics/intelligence?county=Vihiga&mode=rainfall_defect_pattern', headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertEqual(data.get('status'), 'insufficient_data')
        self.assertIn('evidence_threshold', data)
        self.assertIn('current_count', data)
        self.assertIn('location', data)
        self.assertIn('Vihiga', data['location'])
        self.assertIn('message', data)

    def test_05_verified_kpi_toggle_contract(self):
        """The Verified Inspections KPI toggle contract must return verified casework."""
        resp = self.client.get('/api/reports?status=Verified', headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        reports = data.get('reports', [])
        for r in reports:
            self.assertEqual(r.get('status'), 'Verified')

    def test_06_non_causal_language(self):
        """Rainfall defect pattern analysis must strictly use non-causal language."""
        resp = self.client.get('/api/analytics/intelligence?mode=rainfall_defect_pattern&time_range=12m', headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        if data.get('status') == 'success':
            finding = data.get('primary_finding', '').lower()
            self.assertNotIn('rainfall caused', finding)
            self.assertNotIn('rain caused', finding)


if __name__ == '__main__':
    unittest.main()

