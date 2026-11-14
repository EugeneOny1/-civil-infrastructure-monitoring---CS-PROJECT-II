"""
Automated Unit and Integration Tests for SavedModel Defect Detection Inference Service.
Verifies:
- Model loading and serving_default signature accessibility
- Preprocessing and tensor formatting (RGB uint8 [1, H, W, 3])
- Single-image live inference execution
- Output tensor parsing (num_detections, classes, scores, boxes)
- Confidence threshold filtering
- Normalized to pixel coordinate conversion & boundary clipping
- Zero detections handling
- Invalid/corrupt image rejection
"""

import os
import sys
import unittest
import numpy as np
from PIL import Image

# Ensure backend directory is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.services.inference import InferenceService, inference_service


class TestInferenceService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fixtures', 'images'))
        for target_dir in [
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'uploads')),
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'uploads')),
        ]:
            os.makedirs(target_dir, exist_ok=True)
            if os.path.exists(fixtures_dir):
                import shutil
                for fn in os.listdir(fixtures_dir):
                    src = os.path.join(fixtures_dir, fn)
                    dst = os.path.join(target_dir, fn)
                    if os.path.isfile(src) and not os.path.exists(dst):
                        shutil.copy2(src, dst)

        cls.service = inference_service
        cls.test_image_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'uploads', 'seed_pothole.jpg'
        ))
        if not os.path.exists(cls.test_image_path):
            fallback_img = os.path.join(fixtures_dir, 'seed_pothole.jpg')
            if os.path.exists(fallback_img):
                cls.test_image_path = fallback_img

    def test_01_model_loaded_successfully(self):
        """Verifies that the SavedModel is loaded once with the serving_default signature."""
        self.assertTrue(self.service.is_loaded, "InferenceService failed to load SavedModel")
        self.assertIsNotNone(self.service.saved_model, "saved_model attribute should not be None")
        self.assertIsNotNone(self.service.serving_fn, "serving_default callable must be present")
        self.assertEqual(self.service.model_version, 'ssd_mobilenet_v2_lr00015_step1500_v2_1')

    def test_02_preprocessing_preserves_dimensions_and_dtype(self):
        """Verifies that preprocessing keeps original image size and uint8 RGB channels."""
        self.assertTrue(os.path.exists(self.test_image_path), f"Missing test image: {self.test_image_path}")
        with Image.open(self.test_image_path) as img:
            expected_w, expected_h = img.size

        rgb_arr, (w, h) = self.service.preprocess_image(self.test_image_path)
        self.assertEqual(w, expected_w)
        self.assertEqual(h, expected_h)
        self.assertEqual(rgb_arr.dtype, np.uint8)
        self.assertEqual(rgb_arr.shape, (expected_h, expected_w, 3))

    def test_03_single_image_live_inference(self):
        """Executes live SavedModel inference on seed_pothole.jpg and checks detection schema."""
        result = self.service.detect_defects(self.test_image_path, confidence_threshold=0.30)

        self.assertIn('defect_class', result)
        self.assertIn('confidence', result)
        self.assertIn('severity', result)
        self.assertIn('relative_area', result)
        self.assertIn('detections', result)
        self.assertIn('image_dimensions', result)

        self.assertGreaterEqual(result['confidence'], 0.30)
        self.assertIn(result['defect_class'], ['Crack', 'Pothole', 'Surface deterioration'])
        self.assertGreater(len(result['detections']), 0)

        first_det = result['detections'][0]
        self.assertIn('class_id', first_det)
        self.assertIn('class_name', first_det)
        self.assertIn('confidence', first_det)
        self.assertIn('bounding_box', first_det)
        self.assertIn('relative_area', first_det)
        self.assertIn('severity', first_det)
        self.assertIn('validation_status', first_det)

        # Verify pixel bounding box structure
        bbox = first_det['bounding_box']
        self.assertIn('xmin', bbox)
        self.assertIn('ymin', bbox)
        self.assertIn('xmax', bbox)
        self.assertIn('ymax', bbox)
        self.assertLessEqual(bbox['xmin'], bbox['xmax'])
        self.assertLessEqual(bbox['ymin'], bbox['ymax'])

    def test_04_coordinate_clipping_within_image_boundaries(self):
        """Verifies that pixel coordinates never exceed original image width and height."""
        result = self.service.detect_defects(self.test_image_path, confidence_threshold=0.20)
        w = result['image_dimensions']['width']
        h = result['image_dimensions']['height']

        for det in result['detections']:
            box = det['bounding_box']
            self.assertGreaterEqual(box['xmin'], 0)
            self.assertGreaterEqual(box['ymin'], 0)
            self.assertLessEqual(box['xmax'], w)
            self.assertLessEqual(box['ymax'], h)

    def test_05_confidence_threshold_filtering(self):
        """Verifies that raising the threshold filters out low-confidence detections."""
        low_thresh_result = self.service.detect_defects(self.test_image_path, confidence_threshold=0.25)
        high_thresh_result = self.service.detect_defects(self.test_image_path, confidence_threshold=0.70)

        self.assertGreaterEqual(len(low_thresh_result['detections']), len(high_thresh_result['detections']))
        for det in high_thresh_result['detections']:
            self.assertGreaterEqual(det['confidence'], 0.70)

    def test_06_zero_detections_handling(self):
        """Verifies that an image with no detections is handled gracefully without errors."""
        blank_image = np.zeros((300, 300, 3), dtype=np.uint8)
        result = self.service.detect_defects(blank_image, confidence_threshold=0.99)

        self.assertEqual(len(result['detections']), 0)
        self.assertEqual(result['class_name'], 'None Detected')
        self.assertEqual(result['confidence'], 0.0)
        self.assertIsNone(result['bounding_box_pixels'])
        self.assertEqual(result['severity'], 'Low')

    def test_07_corrupt_image_rejection(self):
        """Verifies that non-existent or corrupted files raise descriptive errors."""
        with self.assertRaises(FileNotFoundError):
            self.service.preprocess_image('non_existent_file_xyz_123.jpg')

        temp_corrupt = 'temp_corrupt_test_file.jpg'
        with open(temp_corrupt, 'wb') as f:
            f.write(b'THIS_IS_NOT_A_VALID_IMAGE_CONTENT')
        try:
            with self.assertRaises(ValueError):
                self.service.preprocess_image(temp_corrupt)
        finally:
            if os.path.exists(temp_corrupt):
                os.remove(temp_corrupt)

    def test_08_class_aware_duplicate_suppression(self):
        """Verifies that duplicate boxes of the SAME class with high IoU are suppressed."""
        mock_detections = [
            {
                'class_id': 1,
                'class_name': 'Crack',
                'confidence': 0.90,
                'normalized_box': [0.10, 0.10, 0.50, 0.50],
                'relative_area': 0.16
            },
            {
                'class_id': 1,
                'class_name': 'Crack',
                'confidence': 0.70,
                'normalized_box': [0.12, 0.11, 0.49, 0.51],  # ~90% IoU with previous box
                'relative_area': 0.15
            }
        ]
        surviving = self.service.suppress_class_aware_duplicates(mock_detections, iou_threshold=0.50)
        self.assertEqual(len(surviving), 1)
        self.assertEqual(surviving[0]['confidence'], 0.90)

    def test_09_multi_class_overlapping_preservation(self):
        """CRITICAL: Verifies that overlapping boxes of DIFFERENT classes (e.g. Crack + Pothole) are BOTH preserved."""
        mock_detections = [
            {
                'class_id': 1,
                'class_name': 'Crack',
                'confidence': 0.92,
                'normalized_box': [0.20, 0.20, 0.60, 0.60],
                'relative_area': 0.16
            },
            {
                'class_id': 2,
                'class_name': 'Pothole',
                'confidence': 0.88,
                'normalized_box': [0.22, 0.21, 0.59, 0.58],  # Overlaps significantly with Crack
                'relative_area': 0.14
            }
        ]
        surviving = self.service.suppress_class_aware_duplicates(mock_detections, iou_threshold=0.50)
        self.assertEqual(len(surviving), 2)
        classes = {d['class_name'] for d in surviving}
        self.assertIn('Crack', classes)
        self.assertIn('Pothole', classes)


if __name__ == '__main__':
    unittest.main()
