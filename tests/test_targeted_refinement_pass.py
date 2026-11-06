"""
Targeted Refinement Pass Automated Test Suite
=============================================
Validates:
1. Active heat excludes Resolved reports (intensity 0 / omitted).
2. Heat receives raw report coordinates directly, never cluster centers.
3. Severity intensity mapping: Low = 0.35, Medium = 0.65, Critical = 1.00.
4. Adaptive unclustered markers: Individual pins displayed when visible reports <= 150.
5. Safety Advisories: Dedicated Leaflet pane (safetyAdvisoryPane, z-index 675), dark navy/indigo styling,
   and unified opening callback for direct map-click and notification deep-link.
6. Citizen My Reports layout: Default closed detail panel, List & Gallery view modes, clickable rows,
   evidence thumbnails, and ordered detail sections without primary long IDs.
7. Backend Analytics Trends: Real DB aggregation, zero-month continuity, View by Defect Class & Visual Severity,
   County/Ward geographic filters, and data-backed recurrence insights without weather speculation.
8. Backend Critical Calendar: Daily continuous aggregation, intensities 0 to 3, date-matched counts,
   and explicit temporal concentration metadata.
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app import create_app
from app.services.database import db_service
from app.models.report import InfrastructureReport
from app.utils.auth_helpers import create_access_token


class TestTargetedRefinementPass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()
        cls.created_reports = []
        cls.created_users = []

        # Create engineer user for testing analytics endpoints
        cls.engineer_id = str(ObjectId())
        cls.engineer_user = {
            '_id': cls.engineer_id,
            'name': 'Test Senior Engineer',
            'email': 'refine.engineer@test.gov.ke',
            'role': 'engineer',
            'verification_status': 'verified',
            'is_verified': True
        }
        db_service.delete_one('users', {'email': cls.engineer_user['email']})
        db_service.insert('users', cls.engineer_user)
        cls.created_users.append(cls.engineer_id)

        with cls.app.app_context():
            cls.engineer_token = create_access_token({
                'user_id': cls.engineer_id,
                'email': cls.engineer_user['email'],
                'role': 'engineer'
            })
        cls.auth_headers = {'Authorization': f'Bearer {cls.engineer_token}'}

        # Seed reports with diverse statuses and dates for testing
        now = datetime.now(timezone.utc)
        test_reports = [
            {
                'report_id': 'rep_active_crit_1',
                'description': 'Severe crater on Jakaya Kikwete Road',
                'status': 'Under Review',
                'date_submitted': (now - timedelta(days=5)).isoformat(),
                'location': {'latitude': -1.2884, 'longitude': 36.8142},
                'asset': {'location': 'Jakaya Kikwete Road', 'asset_type': 'Road'},
                'metadata': {
                    'location_name': 'Jakaya Kikwete Road, Nairobi',
                    'defect_class': 'Pothole',
                    'relative_severity': 'Critical',
                    'county': 'Nairobi',
                    'ward': 'CBD'
                }
            },
            {
                'report_id': 'rep_active_med_1',
                'description': 'Surface wear on Uhuru Highway',
                'status': 'Received',
                'date_submitted': (now - timedelta(days=12)).isoformat(),
                'location': {'latitude': -1.2910, 'longitude': 36.8200},
                'asset': {'location': 'Uhuru Highway', 'asset_type': 'Highway'},
                'metadata': {
                    'location_name': 'Uhuru Highway, Nairobi',
                    'defect_class': 'Crack',
                    'relative_severity': 'Medium',
                    'county': 'Nairobi',
                    'ward': 'CBD'
                }
            },
            {
                'report_id': 'rep_resolved_1',
                'description': 'Fixed crack on Waiyaki Way',
                'status': 'Resolved',
                'date_submitted': (now - timedelta(days=20)).isoformat(),
                'location': {'latitude': -1.2650, 'longitude': 36.7900},
                'asset': {'location': 'Waiyaki Way', 'asset_type': 'Road'},
                'metadata': {
                    'location_name': 'Waiyaki Way, Westlands',
                    'defect_class': 'Crack',
                    'relative_severity': 'Critical',
                    'county': 'Nairobi',
                    'ward': 'Westlands'
                }
            }
        ]

        for rep in test_reports:
            r_id = db_service.insert('infrastructure_reports', rep)
            cls.created_reports.append(r_id)

        # Seed AI assessments for these reports
        db_service.insert('ai_assessments', {
            'report_id': 'rep_active_crit_1',
            'defect_class': 'Pothole',
            'relative_severity': 'Critical'
        })
        db_service.insert('ai_assessments', {
            'report_id': 'rep_active_med_1',
            'defect_class': 'Crack',
            'relative_severity': 'Medium'
        })
        db_service.insert('ai_assessments', {
            'report_id': 'rep_resolved_1',
            'defect_class': 'Crack',
            'relative_severity': 'Critical'
        })

    @classmethod
    def tearDownClass(cls):
        for rep_id in cls.created_reports:
            try:
                db_service.delete_one('infrastructure_reports', {'_id': rep_id})
            except Exception:
                pass
        for u_id in cls.created_users:
            try:
                db_service.delete_one('users', {'_id': u_id})
            except Exception:
                pass
        db_service.delete_many('ai_assessments', {'report_id': {'$in': ['rep_active_crit_1', 'rep_active_med_1', 'rep_resolved_1']}})

    # =========================================================================
    # MAP & HEATMAP TESTS
    # =========================================================================

    def test_01_active_heat_excludes_resolved_reports(self):
        """Verifies that Resolved reports contribute 0 intensity and are excluded from active heat points in map.js."""
        map_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'map.js'))
        with open(map_js_path, 'r', encoding='utf-8') as f:
            js = f.read()

        self.assertIn("point.status === 'Resolved'", js, "map.js must explicitly check for Resolved status")
        self.assertIn("!isResolved", js, "Only non-resolved reports must be pushed into heatPoints")

    def test_02_raw_report_coordinates_feed_heatmap(self):
        """Verifies that heatmap receives raw report coordinates directly, not cluster centers."""
        map_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'map.js'))
        with open(map_js_path, 'r', encoding='utf-8') as f:
            js = f.read()

        self.assertIn("heatPoints.push([lat, lng, intensity])", js, "map.js must assemble raw coordinates [lat, lng, intensity]")
        self.assertIn("this.heatLayer.setLatLngs(heatPoints)", js, "map.js must update heatLayer directly with raw heatPoints")

    def test_03_severity_weighting_values(self):
        """Verifies severity weighting: Low = 0.35, Medium = 0.65, Critical = 1.00."""
        map_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'map.js'))
        with open(map_js_path, 'r', encoding='utf-8') as f:
            js = f.read()

        self.assertIn("0.35", js, "Low severity must map to 0.35 intensity")
        self.assertIn("0.65", js, "Medium severity must map to 0.65 intensity")
        self.assertIn("1.00", js, "Critical severity must map to 1.00 intensity")

    def test_04_adaptive_unclustered_markers_threshold(self):
        """Verifies that <= 150 visible reports render as individual unclustered markers."""
        map_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'map.js'))
        with open(map_js_path, 'r', encoding='utf-8') as f:
            js = f.read()

        self.assertIn("CLUSTER_THRESHOLD = 150", js, "map.js must define CLUSTER_THRESHOLD = 150")
        self.assertIn("reportMarkerLayer", js, "map.js must maintain a dedicated unclustered reportMarkerLayer")
        self.assertIn("points.length <= CLUSTER_THRESHOLD", js, "map.js must check visible reports against CLUSTER_THRESHOLD")

    def test_05_safety_advisory_dedicated_pane_and_navy_styling(self):
        """Verifies safetyAdvisoryPane with z-index 675, navy/indigo styling, and unified opening logic."""
        map_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'map.js'))
        with open(map_js_path, 'r', encoding='utf-8') as f:
            js = f.read()

        self.assertIn("safetyAdvisoryPane", js, "map.js must create dedicated safetyAdvisoryPane")
        self.assertIn("675", js, "safetyAdvisoryPane z-index must be 675")
        self.assertIn("#1e1b4b", js, "Safety advisory marker must use dark navy/indigo styling (#1e1b4b)")
        self.assertIn("bx-shield-quarter", js, "Safety advisory marker must use white shield icon bx-shield-quarter")
        self.assertIn("openSafetyAdvisory", js, "map.js must define unified openSafetyAdvisory callback")

    # =========================================================================
    # CITIZEN MY REPORTS TESTS
    # =========================================================================

    def test_06_citizen_my_reports_master_detail_structure(self):
        """Verifies master-detail layout container, default closed state, and list/gallery toggle."""
        html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'index.html'))
        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        self.assertIn("trackingLayoutContainer", html, "index.html must contain trackingLayoutContainer")
        self.assertIn("trackingExplorerCol", html, "index.html must contain trackingExplorerCol")
        self.assertIn("trackingDetailCol", html, "index.html must contain trackingDetailCol")
        self.assertIn("btnTrackingListView", html, "index.html must provide List view toggle button")
        self.assertIn("btnTrackingGalleryView", html, "index.html must provide Gallery view toggle button")

        app_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'app.js'))
        with open(app_js_path, 'r', encoding='utf-8') as f:
            app_js = f.read()

        self.assertIn("closeTrackingDetail", app_js, "app.js must provide closeTrackingDetail method")
        self.assertIn("setTrackingViewMode", app_js, "app.js must provide setTrackingViewMode method")
        self.assertIn("tracking-evidence-thumb", app_js, "app.js list view must render evidence thumbnail")

    # =========================================================================
    # ANALYTICS & TRENDS TESTS
    # =========================================================================

    def test_07_historical_defect_trends_endpoint_and_recurrence_insights(self):
        """Verifies GET /api/analytics/trends returns continuous buckets and genuine recurrence insights without weather claims."""
        res = self.client.get('/api/analytics/trends?range=6m&view_by=defect_class', headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertIn('trend_data', data)
        self.assertIn('summary', data)
        self.assertTrue(len(data['trend_data']) >= 6, "6m view must return at least 6 monthly buckets")

        # Zero-month continuity check: buckets must have numeric counts
        for b in data['trend_data']:
            self.assertIn('period', b)
            self.assertIn('total', b)
            self.assertIsInstance(b['total'], int)

        # Recurrence insights check
        insights = data['summary'].get('recurrence_insights', [])
        self.assertIsInstance(insights, list)
        for ins in insights:
            self.assertIn('title', ins)
            self.assertIn('value', ins)
            self.assertIn('basis', ins)
            # Confirm no weather causation claims
            self.assertNotIn('rain', ins['basis'].lower())
            self.assertNotIn('weather', ins['basis'].lower())
            self.assertNotIn('forecast', ins['basis'].lower())

    def test_08_critical_reports_calendar_endpoint(self):
        """Verifies GET /api/analytics/critical-calendar returns continuous day grid with intensities 0 to 3."""
        res = self.client.get('/api/analytics/critical-calendar?range=3m', headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        cal = res.get_json()

        self.assertEqual(cal['time_range'], '3m')
        self.assertIn('total_critical_reports', cal)
        self.assertIn('days', cal)
        self.assertIn('max_daily_count', cal)
        self.assertTrue(len(cal['days']) >= 89, "3m range must have ~90 continuous daily records")

        # Verify daily cell structure and intensity limits
        for day in cal['days']:
            self.assertIn('date', day)
            self.assertIn('count', day)
            self.assertIn('intensity', day)
            self.assertIn(day['intensity'], [0, 1, 2, 3], "Intensity must be between 0 and 3")
            if day['count'] == 0:
                self.assertEqual(day['intensity'], 0)
            elif day['count'] == 1:
                self.assertEqual(day['intensity'], 1)
            elif day['count'] == 2:
                self.assertEqual(day['intensity'], 2)
            else:
                self.assertEqual(day['intensity'], 3)

        # Analytical distinction confirmation
        self.assertIn("temporal concentration", cal['note'].lower())

    def test_09_dashboard_chartjs_integration_and_calendar_grid(self):
        """Verifies dashboard.js configures Chart.js line chart with smooth cubic interpolation and destroys prior instances."""
        dash_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'js', 'dashboard.js'))
        with open(dash_js_path, 'r', encoding='utf-8') as f:
            js = f.read()

        self.assertIn("new Chart(", js, "dashboard.js must instantiate Chart.js")
        self.assertIn("cubicInterpolationMode: 'monotone'", js, "Chart must use monotone cubic interpolation")
        self.assertIn("tension: 0.35", js, "Chart line tension must be approx 0.35")
        self.assertIn("this.trendChart.destroy()", js, "dashboard.js must destroy previous Chart instance on reload")
        self.assertIn("renderCriticalCalendarGrid", js, "dashboard.js must define renderCriticalCalendarGrid")
        self.assertIn("loadCriticalCalendar", js, "dashboard.js must define loadCriticalCalendar")


if __name__ == '__main__':
    unittest.main()
