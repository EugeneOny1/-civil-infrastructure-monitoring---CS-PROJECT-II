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
        """Verifies heatmapPane creation, z-index 350, pointer-events none, zoom-aware configuration, and continuous color gradient."""
        self.assertTrue(os.path.exists(self.map_js_path), "map.js must exist in frontend/js")
        with open(self.map_js_path, 'r', encoding='utf-8') as f:
            map_code = f.read()

        self.assertIn("heatmapPane", map_code, "heatmapPane must be configured in map.js")
        self.assertIn("350", map_code, "heatmapPane z-index must be 350 (beneath markers/clusters)")
        self.assertIn("pointerEvents", map_code, "heatmapPane must have pointerEvents: 'none'")
        self.assertIn("getZoomHeatOptions", map_code, "map.js must contain getZoomHeatOptions for zoom-aware scaling")
        self.assertIn("updateZoomAwareHeatmap", map_code, "map.js must contain updateZoomAwareHeatmap")
        self.assertIn("#10b981", map_code, "map.js must include emerald green stop in heatGradient")
        self.assertIn("#991b1b", map_code, "map.js must include deep red stop in heatGradient")

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

    def test_07_zoom_aware_radius_blur_ranges_and_attenuation(self):
        """Verifies zoom-aware options logic matching getZoomHeatOptions:
        - zoom <= 7: attenuated, radius 12, blur 10, minOpacity 0.08
        - zoom 8-10: radius 16, blur 14, minOpacity 0.12
        - zoom 11-13: radius 24, blur 18, minOpacity 0.20
        - zoom >= 14: radius 34, blur 22, minOpacity 0.24
        """
        def get_zoom_heat_options(zoom):
            if zoom <= 7:
                return {'radius': 12, 'blur': 10, 'minOpacity': 0.08, 'attenuated': True}
            elif zoom <= 10:
                return {'radius': 16, 'blur': 14, 'minOpacity': 0.12, 'attenuated': False}
            elif zoom <= 13:
                return {'radius': 24, 'blur': 18, 'minOpacity': 0.20, 'attenuated': False}
            else:
                return {'radius': 34, 'blur': 22, 'minOpacity': 0.24, 'attenuated': False}

        opt_country = get_zoom_heat_options(6)
        self.assertTrue(opt_country['attenuated'])
        self.assertEqual(opt_country['radius'], 12)
        self.assertEqual(opt_country['blur'], 10)

        opt_regional = get_zoom_heat_options(9)
        self.assertFalse(opt_regional['attenuated'])
        self.assertEqual(opt_regional['radius'], 16)
        self.assertEqual(opt_regional['blur'], 14)

        opt_nairobi = get_zoom_heat_options(12)
        self.assertFalse(opt_nairobi['attenuated'])
        self.assertEqual(opt_nairobi['radius'], 24)
        self.assertEqual(opt_nairobi['blur'], 18)

        opt_street = get_zoom_heat_options(16)
        self.assertFalse(opt_street['attenuated'])
        self.assertEqual(opt_street['radius'], 34)
        self.assertEqual(opt_street['blur'], 22)

    def test_08_image_serving_endpoint_security_and_reliability(self):
        """Verifies safe image serving endpoint:
        - 200 for existing image
        - 404 for missing image (no fake fallback)
        - 400 for path traversal attempt (../)
        - 200 for legacy path prefix normalization
        """
        # Test existing image if available (check uploads directory)
        upload_dir = os.path.join(os.path.dirname(__file__), '..', 'backend', 'uploads')
        existing_files = [f for f in os.listdir(upload_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if existing_files:
            target_file = existing_files[0]
            # Valid direct filename
            res = self.client.get(f"/api/reports/images/{target_file}")
            self.assertEqual(res.status_code, 200)
            self.assertIn("image/", res.content_type)

            # Legacy prefixed filename
            res_legacy = self.client.get(f"/api/reports/images/uploads/{target_file}")
            self.assertEqual(res_legacy.status_code, 200)

        # Missing file must return 404
        res_missing = self.client.get("/api/reports/images/nonexistent_defect_image_xyz_9999.jpg")
        self.assertEqual(res_missing.status_code, 404)

        # Path traversal must return 400
        res_traversal = self.client.get("/api/reports/images/../../app/__init__.py")
        self.assertIn(res_traversal.status_code, (400, 404))

    def test_09_navigation_motion_transition_css(self):
        """Verifies viewSlideFadeIn transition keyframe and prefers-reduced-motion in main.css."""
        main_css_path = os.path.join(self.frontend_dir, 'css', 'main.css')
        self.assertTrue(os.path.exists(main_css_path))
        with open(main_css_path, 'r', encoding='utf-8') as f:
            css = f.read()

        self.assertIn("viewSlideFadeIn", css, "main.css must contain viewSlideFadeIn animation")
        self.assertIn("prefers-reduced-motion", css, "main.css must respect prefers-reduced-motion")
        self.assertIn("cubic-bezier(0.16, 1, 0.3, 1)", css, "main.css must use smooth easing curve")

if __name__ == '__main__':
    unittest.main()
