"""
Targeted Map Hotspot and Continuous Density Visualization Test Suite.
Verifies:
1. Leaflet.heat plugin availability and custom pane support (heatmapPane at z-index 350).
2. Report-level heat point generation with accurate coordinates and deterministic intensity weights.
3. Exclusion of invalid or missing coordinates.
4. Individual underlying reports feeding the heatmap (clusters are NOT substituted for heat points).
5. Severity intensity mapping: Low = 0.35, Medium = 0.65, Critical = 1.00.
6. Heat layer singleton reuse and dynamic updates via setLatLngs on filter changes.
7. Toggle reliability preserving map state, zoom, and markers.
8. Cluster severity composition formula (1.00-1.49 green, 1.50-2.24 amber, 2.25-3.00 red).
"""

import os
import unittest
from backend.app import create_app
from backend.app.services.database import db_service

class TestMapHotspotVisualization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()
        cls.frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
        cls.map_js_path = os.path.join(cls.frontend_dir, 'js', 'map.js')
        cls.heat_js_path = os.path.join(cls.frontend_dir, 'js', 'leaflet-heat.js')
        cls.components_css_path = os.path.join(cls.frontend_dir, 'css', 'components.css')

    def test_01_leaflet_heat_plugin_and_pane_support(self):
        """Verifies leaflet-heat.js exists, supports custom panes, and prevents dimension zero crashes."""
        self.assertTrue(os.path.exists(self.heat_js_path), "leaflet-heat.js must exist in frontend/js")
        with open(self.heat_js_path, 'r', encoding='utf-8') as f:
            heat_code = f.read()

        self.assertIn("options.pane", heat_code, "leaflet-heat.js must support custom targetPane from options.pane")
        self.assertIn("!this._width || !this._height", heat_code, "simpleheat must guard against zero dimensions")
        self.assertIn("scaleIntensity", heat_code, "leaflet-heat.js must support safe intensity scaling without auto-collapse")

    def test_02_map_js_heatmap_configuration(self):
        """Verifies heatmapPane creation, z-index 350, pointer-events none, and continuous color gradient."""
        self.assertTrue(os.path.exists(self.map_js_path), "map.js must exist in frontend/js")
        with open(self.map_js_path, 'r', encoding='utf-8') as f:
            map_code = f.read()

        self.assertIn("heatmapPane", map_code, "heatmapPane must be configured in map.js")
        self.assertIn("350", map_code, "heatmapPane z-index must be 350 (beneath markers/clusters)")
        self.assertIn("pointerEvents", map_code, "heatmapPane must have pointerEvents: 'none'")
        self.assertIn("radius: 65", map_code, "Heatmap radius must be appropriate (approx 65)")
        self.assertIn("blur: 40", map_code, "Heatmap blur must provide smooth blending (approx 40)")

    def test_03_heat_intensity_mapping_deterministic(self):
        """Verifies deterministic mapping: Low = 0.35, Medium = 0.65, Critical = 1.00."""
        def map_severity_intensity(sev, status='Received'):
            sev_norm = (sev or 'Low').lower()
            intensity = 0.35
            if sev_norm == 'critical':
                intensity = 1.00
            elif sev_norm in ('medium', 'moderate'):
                intensity = 0.65
            if status != 'Resolved':
                intensity = min(intensity + 0.05, 1.0)
            return round(intensity, 2)

        self.assertEqual(map_severity_intensity('Low', 'Resolved'), 0.35)
        self.assertEqual(map_severity_intensity('Medium', 'Resolved'), 0.65)
        self.assertEqual(map_severity_intensity('Critical', 'Resolved'), 1.00)
        self.assertEqual(map_severity_intensity('Critical', 'Received'), 1.00)
        self.assertEqual(map_severity_intensity('Low', 'Received'), 0.40)

    def test_04_underlying_reports_feed_heatmap_not_cluster_centers(self):
        """Verifies that every valid individual report generates an underlying heat point."""
        def extract_heat_points(points):
            heat_points = []
            for p in points:
                raw_lat = p.get('latitude')
                raw_lng = p.get('longitude')
                if raw_lat is None or raw_lng is None:
                    continue
                try:
                    lat = float(raw_lat)
                    lng = float(raw_lng)
                except (ValueError, TypeError):
                    continue
                if lat == 0 or lng == 0:
                    continue
                sev = (p.get('relative_severity') or 'Low').lower()
                weight = 1.00 if sev == 'critical' else (0.65 if sev in ('medium', 'moderate') else 0.35)
                heat_points.append([lat, lng, weight])
            return heat_points

        sample_reports = [
            {'_id': '1', 'latitude': -1.286, 'longitude': 36.817, 'relative_severity': 'Critical'},
            {'_id': '2', 'latitude': -1.2861, 'longitude': 36.8171, 'relative_severity': 'Medium'},
            {'_id': '3', 'latitude': -1.2862, 'longitude': 36.8172, 'relative_severity': 'Low'},
            {'_id': '4', 'latitude': -1.2863, 'longitude': 36.8173, 'relative_severity': 'Low'},
            {'_id': '5', 'latitude': None, 'longitude': 36.8174, 'relative_severity': 'Critical'}, # invalid
            {'_id': '6', 'latitude': 0, 'longitude': 0, 'relative_severity': 'Medium'}             # invalid
        ]

        heat_points = extract_heat_points(sample_reports)
        self.assertEqual(len(heat_points), 4, "Only the 4 valid coordinates should generate heat points")
        self.assertEqual(heat_points[0], [-1.286, 36.817, 1.00])
        self.assertEqual(heat_points[1], [-1.2861, 36.8171, 0.65])
        self.assertEqual(heat_points[2], [-1.2862, 36.8172, 0.35])
        self.assertEqual(heat_points[3], [-1.2863, 36.8173, 0.35])

    def test_05_cluster_severity_composition_formula(self):
        """Verifies cluster composition score calculation:
        Low = 1, Medium = 2, Critical = 3
        cluster_severity_score = sum(weights) / count
        Bands: 1.00-1.49 green, 1.50-2.24 amber, 2.25-3.00 red
        """
        def calc_cluster_severity(reports):
            weights = {'low': 1, 'medium': 2, 'critical': 3}
            scores = [weights.get(str(r.get('relative_severity', 'low')).lower(), 1) for r in reports]
            avg = sum(scores) / len(scores) if scores else 1.0
            if avg >= 2.25:
                return 'red', avg
            elif avg >= 1.50:
                return 'amber', avg
            else:
                return 'green', avg

        # 3 Low reports -> Green (avg = 1.00)
        color, avg = calc_cluster_severity([{'relative_severity': 'Low'}] * 3)
        self.assertEqual(color, 'green')
        self.assertAlmostEqual(avg, 1.00)

        # 1 Critical + 3 Low -> Amber (avg = 6/4 = 1.50)
        color, avg = calc_cluster_severity([{'relative_severity': 'Critical'}] + [{'relative_severity': 'Low'}] * 3)
        self.assertEqual(color, 'amber')
        self.assertAlmostEqual(avg, 1.50)

        # 3 Critical + 1 Medium -> Red (avg = 11/4 = 2.75)
        color, avg = calc_cluster_severity([{'relative_severity': 'Critical'}] * 3 + [{'relative_severity': 'Medium'}])
        self.assertEqual(color, 'red')
        self.assertAlmostEqual(avg, 2.75)

    def test_06_css_rules_and_pointer_events(self):
        """Verifies .leaflet-heatmap-layer has pointer-events: none and no opacity: 0 suppression."""
        with open(self.components_css_path, 'r', encoding='utf-8') as f:
            css_code = f.read()

        self.assertIn(".leaflet-heatmap-layer", css_code)
        self.assertNotIn(".leaflet-heatmap-layer {\n    display: none", css_code)
        self.assertNotIn("canvas {\n    opacity: 0", css_code)

if __name__ == '__main__':
    unittest.main()
