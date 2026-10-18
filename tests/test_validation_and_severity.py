"""
Automated Unit Tests for Domain Integrity Validation and Visual Severity Calculation.
Verifies:
- Standard defect-infrastructure combinations (Road + Pothole, Building + Crack, Bridge + Pothole)
- Unusual combinations flagged for engineer review (Building + Pothole) NOT rejected
- Input integrity validation for empty or malformed assets
- Relative visual severity based on bounding box extent (<5% Low, 5-15% Moderate, >=15% Critical)
- Pixel box area ratio calculation
"""

import os
import sys
import unittest

# Ensure backend directory is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.services.validation import validation_service
from app.services.severity import severity_service


class TestValidationAndSeverity(unittest.TestCase):

    # ─────────────────────────────────────────────────────────────
    # VALIDATION RULES TESTS
    # ─────────────────────────────────────────────────────────────

    def test_01_standard_road_combinations(self):
        """Verifies standard defect types expected on roads."""
        for defect in ['Crack', 'Pothole', 'Surface deterioration']:
            res = validation_service.check_defect_compatibility('Road / Pavement', defect)
            self.assertEqual(res['validation_status'], 'valid', f"Expected valid for Road + {defect}")
            self.assertFalse(res['is_unusual'])

    def test_02_standard_building_combinations(self):
        """Verifies standard defect types expected on buildings."""
        for defect in ['Crack', 'Surface deterioration']:
            res = validation_service.check_defect_compatibility('Building', defect)
            self.assertEqual(res['validation_status'], 'valid', f"Expected valid for Building + {defect}")
            self.assertFalse(res['is_unusual'])

    def test_03_standard_bridge_combinations(self):
        """Verifies standard defect types expected on bridges."""
        for defect in ['Crack', 'Surface deterioration', 'Pothole']:
            res = validation_service.check_defect_compatibility('Bridge / Viaduct', defect)
            self.assertEqual(res['validation_status'], 'valid', f"Expected valid for Bridge + {defect}")
            self.assertFalse(res['is_unusual'])

    def test_04_unusual_building_pothole_flagged_not_rejected(self):
        """CRITICAL: Building + Pothole must be flagged as unusual for engineer review, NOT rejected."""
        res = validation_service.check_defect_compatibility('Building', 'Pothole')
        self.assertEqual(res['validation_status'], 'unusual')
        self.assertTrue(res['is_unusual'])
        self.assertTrue(res['is_valid'], "Unusual combinations must remain valid submissions")
        self.assertIn("Pothole is unusual for the selected infrastructure type", res['validation_message'])

    def test_05_invalid_input_handling(self):
        """Verifies that missing asset_type is flagged as invalid."""
        res = validation_service.check_defect_compatibility('', 'Crack')
        self.assertEqual(res['validation_status'], 'invalid')
        self.assertFalse(res['is_valid'])

        valid_in, errors = validation_service.validate_submission_inputs('', '')
        self.assertFalse(valid_in)
        self.assertGreater(len(errors), 0)

    def test_06_holistic_report_validation_enriches_detections(self):
        """Verifies that validate_report attaches validation_status to individual detection items."""
        sample_detection_result = {
            'defect_class': 'Pothole',
            'confidence_score': 0.85,
            'area_percentage': 12.0,
            'relative_severity': 'Moderate',
            'detections': [
                {'class_name': 'Pothole', 'confidence': 0.85},
                {'class_name': 'Crack', 'confidence': 0.75}
            ]
        }
        report_val = validation_service.validate_report('Building', 'Annex Perimeter Wall', sample_detection_result)
        self.assertEqual(report_val['validation_status'], 'unusual')
        self.assertEqual(report_val['recommended_status'], 'Received')
        self.assertTrue(report_val['requires_engineer_review'])

        # Check that individual detection items received validation statuses
        pothole_det = sample_detection_result['detections'][0]
        crack_det = sample_detection_result['detections'][1]
        self.assertEqual(pothole_det['validation_status'], 'unusual')
        self.assertEqual(crack_det['validation_status'], 'valid')

    # ─────────────────────────────────────────────────────────────
    # SEVERITY CALCULATION TESTS
    # ─────────────────────────────────────────────────────────────

    def test_07_severity_threshold_mapping(self):
        """Verifies relative visual severity threshold categories: Low (<5%), Moderate (5-15%), Critical (>=15%)."""
        self.assertEqual(severity_service.calculate_severity_for_area(0.01), 'Low')
        self.assertEqual(severity_service.calculate_severity_for_area(0.049), 'Low')
        self.assertEqual(severity_service.calculate_severity_for_area(0.05), 'Moderate')
        self.assertEqual(severity_service.calculate_severity_for_area(0.061), 'Moderate')
        self.assertEqual(severity_service.calculate_severity_for_area(0.149), 'Moderate')
        self.assertEqual(severity_service.calculate_severity_for_area(0.15), 'Critical')
        self.assertEqual(severity_service.calculate_severity_for_area(0.45), 'Critical')

    def test_08_box_area_ratio_calculation(self):
        """Verifies normalized and pixel bounding-box area calculations."""
        # Normalized: [ymin, xmin, ymax, xmax] -> 0.4 * 0.6 = 0.24
        norm_area = severity_service.calculate_box_area([0.1, 0.2, 0.5, 0.8])
        self.assertAlmostEqual(norm_area, 0.24, places=4)

        # Pixel: (310 - 85) * (430 - 120) / (800 * 600) = 225 * 310 / 480000 = 69750 / 480000 = 0.1453
        px_box = {'xmin': 120, 'ymin': 85, 'xmax': 430, 'ymax': 310}
        px_area = severity_service.calculate_box_area(px_box, image_width=800, image_height=600)
        self.assertAlmostEqual(px_area, 0.1453, places=4)

    def test_09_evaluate_relative_severity_aggregate(self):
        """Verifies aggregate severity calculation across detections list."""
        detections = [
            {'relative_area': 0.03},
            {'relative_area': 0.04}
        ]
        res = severity_service.evaluate_relative_severity(detections)
        self.assertAlmostEqual(res['relative_area'], 0.07, places=4)
        self.assertEqual(res['severity'], 'Moderate')

        empty_res = severity_service.evaluate_relative_severity([])
        self.assertEqual(empty_res['severity'], 'Low')
        self.assertEqual(empty_res['relative_area'], 0.0)


if __name__ == '__main__':
    unittest.main()
