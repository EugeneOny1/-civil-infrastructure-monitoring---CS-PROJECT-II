"""
Tests for Final Monitoring Dashboard Intelligence Refinement.
Validates:
1. Critical Reports Calendar month-centric carousel payload structure.
2. Historical Defect Trends straight lines and Pattern Intelligence generation.
3. Climatological seasonal accuracy (Kenyan Long Rains vs Short Rains).
4. Non-causal engineering wording and minimum evidence thresholds.
5. Zero-result safety and frontend contract integrity.
"""

import unittest
from datetime import datetime, timezone
from backend.app import create_app
from backend.app.services.database import db_service
from backend.app.services.weather_service import weather_service, classify_kenya_season


class TestFinalMonitoringRefinement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()

        # Seed test verified engineer
        from backend.app.utils.auth_helpers import create_access_token
        cls.engineer_id = 'test_eng_refine_01'
        db_service.delete_many('users', {'_id': cls.engineer_id})
        user_doc = {
            '_id': cls.engineer_id,
            'email': 'engineer.refine@example.com',
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

    def test_01_classify_kenya_season_accuracy(self):
        """Kenyan climatological seasons must strictly differentiate Long Rains (MAM) vs Short Rains (OND)."""
        # Long Rains: March, April, May
        self.assertEqual(classify_kenya_season(3)['season'], 'Long Rains')
        self.assertEqual(classify_kenya_season(4)['season'], 'Long Rains')
        self.assertEqual(classify_kenya_season(5)['season'], 'Long Rains')

        # Short Rains: October, November, December
        self.assertEqual(classify_kenya_season(10)['season'], 'Short Rains')
        self.assertEqual(classify_kenya_season(11)['season'], 'Short Rains')
        self.assertEqual(classify_kenya_season(12)['season'], 'Short Rains')

        # Dry season / Inter-monsoon
        self.assertIn('Dry', classify_kenya_season(1)['season'])
        self.assertIn('Dry', classify_kenya_season(7)['season'])

    def test_02_critical_calendar_month_structure(self):
        """GET /api/analytics/critical-calendar returns month groupings with active summary metrics."""
        resp = self.client.get('/api/analytics/critical-calendar?range=6m', headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertIn('months', data)
        self.assertIsInstance(data['months'], list)
        self.assertGreater(len(data['months']), 0)

        # Inspect first month contract
        m = data['months'][0]
        self.assertIn('key', m)
        self.assertIn('label', m)
        self.assertIn('year', m)
        self.assertIn('month', m)
        self.assertIn('total_critical', m)
        self.assertIn('most_reported_defect', m)
        self.assertIn('most_active_corridor', m)
        self.assertIn('resolved_during_month', m)
        self.assertIn('days', m)
        self.assertIsInstance(m['days'], list)

        # Inspect day structure
        day = m['days'][0]
        self.assertIn('date', day)
        self.assertIn('intensity', day)
        self.assertIn('count', day)
        self.assertIn('defect_breakdown', day)

    def test_03_pattern_intelligence_in_trends(self):
        """GET /api/analytics/trends attaches rich pattern_intelligence smart cards."""
        resp = self.client.get('/api/analytics/trends?range=6m&view_by=defect_class', headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertIn('monitoring_insights', data)
        insights = data['monitoring_insights']
        self.assertIn('pattern_intelligence', insights)
        cards = insights['pattern_intelligence']
        self.assertIsInstance(cards, list)

        if len(cards) > 0:
            card = cards[0]
            self.assertIn('card_id', card)
            self.assertIn('category_tag', card)
            self.assertIn('title', card)
            self.assertIn('icon', card)
            self.assertTrue(card['icon'].startswith('bx-'), f"Icon should be a Boxicon class: {card['icon']}")
            self.assertIn('statement', card)
            self.assertIn('evidence', card)
            self.assertIn('actions', card)

            # Ensure strictly non-causal language in statement
            statement_lower = card['statement'].lower()
            self.assertNotIn("causes pothole", statement_lower)
            self.assertNotIn("directly caused by rain", statement_lower)

    def test_04_zero_data_resilience_county(self):
        """Selecting a county with zero reports returns 200 OK and valid zero state without crashing."""
        resp = self.client.get('/api/analytics/trends?county=Vihiga&range=6m', headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('total_reports', 0), 0)
        self.assertIn('monitoring_insights', data)

        cal_resp = self.client.get('/api/analytics/critical-calendar?county=Vihiga&range=6m', headers=self.headers)
        self.assertEqual(cal_resp.status_code, 200)
        cal_data = cal_resp.get_json()
        self.assertEqual(cal_data.get('total_critical_reports', 0), 0)

    def test_05_frontend_code_contract(self):
        """Verify frontend assets contain straight lines, carousel stage, and focusCorridor."""
        with open('frontend/js/dashboard.js', 'r', encoding='utf-8') as f:
            dash_js = f.read()

        # Straight-line verification
        self.assertIn("tension: 0", dash_js)
        self.assertNotIn("cubicInterpolationMode: 'monotone'", dash_js)
        self.assertIn("pointRadius: 4", dash_js)
        self.assertIn("pointHoverRadius: 7", dash_js)
        self.assertIn("borderWidth: 2", dash_js)
        self.assertIn("Total Reports: ${sum}", dash_js)

        # Carousel & KPI toggle verification
        self.assertIn("renderMonthCarousel", dash_js)
        self.assertIn("switchCarouselMonth", dash_js)
        self.assertIn("isVerifiedFilterActive", dash_js)

        with open('frontend/js/map.js', 'r', encoding='utf-8') as f:
            map_js = f.read()
        self.assertIn("focusCorridor(corridorName)", map_js)

        with open('frontend/index.html', 'r', encoding='utf-8') as f:
            html = f.read()
        self.assertIn('id="criticalCalendarCarouselStage"', html)
        self.assertIn('id="calCurrentMonthLabel"', html)
        self.assertIn('id="btnCalPrevMonth"', html)
        self.assertIn('id="btnCalNextMonth"', html)
        self.assertIn('id="kpiVerifiedActiveBadge"', html)


if __name__ == '__main__':
    unittest.main()
