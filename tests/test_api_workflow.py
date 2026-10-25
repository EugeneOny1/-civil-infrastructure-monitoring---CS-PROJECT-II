"""
Automated Integration Tests for Flask REST API Endpoints, Uploads, and Persistence.
Verifies:
- Application startup and health check endpoint
- JWT Authentication and role authorization
- Full image upload and SavedModel inference execution (POST /api/reports)
- JSON response schema (defect_class, confidence, severity, detections, image dimensions)
- Unusual defect combination workflow (Building + Pothole -> Flagged for Review)
- Zero-detection upload workflow (blank image -> None Detected)
- Corrupt/invalid file upload rejection (HTTP 400)
- MongoDB persistence verification
"""

import os
import sys
import io
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image

# Ensure backend directory is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app import create_app
from app.services.database import db_service


class TestApiWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()
        cls.test_image_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'uploads', 'seed_pothole.jpg'
        ))
        cls.created_report_ids = []

        # Login as citizen
        res = cls.client.post('/api/auth/login', json={
            'email': 'citizen@strathmore.edu',
            'password': 'Citizen@123'
        })
        cls.citizen_token = res.get_json().get('token')

        # Login as engineer (handles mandatory 2FA)
        res_eng = cls.client.post('/api/auth/login', json={
            'email': 'engineer@kenha.go.ke',
            'password': 'Engineer@123'
        })
        eng_data = res_eng.get_json() or {}
        if eng_data.get('require_2fa'):
            otp = eng_data.get('demo_otp')
            res_2fa = cls.client.post('/api/auth/verify-2fa', json={
                'user_id': eng_data.get('user_id'),
                'otp': otp
            })
            cls.engineer_token = res_2fa.get_json().get('token')
        else:
            cls.engineer_token = eng_data.get('token')

    @classmethod
    def tearDownClass(cls):
        """Clean up reports created during integration testing to keep database pristine."""
        for rid in getattr(cls, 'created_report_ids', []):
            try:
                db_service.delete_one('infrastructure_reports', {'_id': rid})
                db_service.delete_many('submitted_images', {'report_id': rid})
                db_service.delete_many('ai_assessments', {'report_id': rid})
            except Exception:
                pass

    def test_01_health_check_endpoint(self):
        """Verifies GET /api/health returns online status and SavedModel version."""
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'online')
        self.assertEqual(data.get('model'), 'ssd_mobilenet_v2_lr00625_step8000_v2')
        self.assertTrue(data.get('model_loaded'))

    def test_02_report_submission_with_saved_model_inference(self):
        """Executes full defect report submission with real SavedModel inference."""
        with open(self.test_image_path, 'rb') as f:
            img_bytes = f.read()

        payload = {
            'image': (io.BytesIO(img_bytes), 'seed_pothole.jpg'),
            'asset_type': 'Road / Pavement',
            'location': 'Uhuru Highway (Chainage 14+350)',
            'description': 'Integration test defect submission'
        }

        res = self.client.post(
            '/api/reports',
            data=payload,
            content_type='multipart/form-data',
            headers={'Authorization': f'Bearer {self.citizen_token}'}
        )

        self.assertEqual(res.status_code, 201)
        data = res.get_json()

        # Check top-level response structure
        self.assertIn('report_id', data)
        self.assertIn('status', data)
        self.assertIn('report', data)
        self.assertIn('image', data)
        self.assertIn('ai_assessment', data)
        self.assertIn('validation', data)

        # Check AI assessment payload
        ai = data['ai_assessment']
        self.assertEqual(ai['model_version'], 'ssd_mobilenet_v2_lr00625_step8000_v2')
        self.assertIn(ai['defect_class'], ['Crack', 'Pothole', 'Surface deterioration'])
        self.assertGreaterEqual(ai['confidence_score'], 0.30)
        self.assertIn('relative_severity', ai)
        self.assertIn('detections', ai)
        self.assertGreater(len(ai['detections']), 0)

        # Verify MongoDB persistence
        report_id = data['report_id']
        self.__class__.created_report_ids.append(report_id)
        persisted_report = db_service.find_one('infrastructure_reports', {'_id': report_id})
        self.assertIsNotNone(persisted_report)
        self.assertEqual(persisted_report['user_id'], 'usr_cit_01')

        persisted_ai = db_service.find_one('ai_assessments', {'image_id': data['image']['image_id']})
        self.assertIsNotNone(persisted_ai)
        self.assertEqual(persisted_ai['model_version'], 'ssd_mobilenet_v2_lr00625_step8000_v2')

    @patch('app.routes.reports.inference_service.detect_defects')
    def test_03_unusual_combination_workflow(self, mock_detect):
        """CRITICAL: Building + Pothole must be accepted (HTTP 201) and flagged for review."""
        mock_detect.return_value = {
            'defect_class': 'Pothole',
            'confidence_score': 0.88,
            'relative_severity': 'High',
            'area_percentage': 18.0,
            'detections': [{
                'defect_class': 'Pothole',
                'class_name': 'Pothole',
                'confidence_score': 0.88,
                'bounding_box': [0.2, 0.2, 0.6, 0.6],
                'relative_severity': 'High'
            }],
            'model_version': 'ssd_mobilenet_v2_lr00625_step8000_v2',
            'model_name': 'SSD-MobileNetV2',
            'bounding_box': [0.2, 0.2, 0.6, 0.6],
            'image_dimensions': {'width': 300, 'height': 300}
        }
        with open(self.test_image_path, 'rb') as f:
            img_bytes = f.read()

        payload = {
            'image': (io.BytesIO(img_bytes), 'seed_pothole.jpg'),
            'asset_type': 'Building',
            'location': 'Nyayo Municipal Annex Wall',
            'description': 'Unusual defect pairing test'
        }

        res = self.client.post(
            '/api/reports',
            data=payload,
            content_type='multipart/form-data',
            headers={'Authorization': f'Bearer {self.citizen_token}'}
        )

        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        if 'report_id' in data:
            self.__class__.created_report_ids.append(data['report_id'])
        self.assertEqual(data['status'], 'Received')
        self.assertEqual(data['validation']['validation_status'], 'unusual')
        self.assertTrue(data['validation']['is_unusual'])
        self.assertTrue(data['validation'].get('requires_engineer_review'))

    def test_04_zero_detections_workflow(self):
        """Verifies that an image with no defects detected creates a valid Pending report."""
        blank_arr = np.full((300, 300, 3), 255, dtype=np.uint8)
        blank_img = Image.fromarray(blank_arr)
        buf = io.BytesIO()
        blank_img.save(buf, format='JPEG')
        buf.seek(0)

        payload = {
            'image': (buf, 'clean_wall.jpg'),
            'asset_type': 'Road / Pavement',
            'location': 'Kenyatta Avenue Corridor',
            'description': 'Clean surface test'
        }

        res = self.client.post(
            '/api/reports',
            data=payload,
            content_type='multipart/form-data',
            headers={'Authorization': f'Bearer {self.citizen_token}'}
        )

        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        if 'report_id' in data:
            self.__class__.created_report_ids.append(data['report_id'])
        ai = data['ai_assessment']
        self.assertEqual(ai['defect_class'], 'None Detected')
        self.assertEqual(ai['confidence_score'], 0.0)
        self.assertEqual(len(ai['detections']), 0)

    def test_05_corrupt_upload_rejection(self):
        """Verifies that corrupt or non-image uploads return HTTP 400."""
        payload = {
            'image': (io.BytesIO(b'NOT_AN_IMAGE_PAYLOAD'), 'corrupt.jpg'),
            'asset_type': 'Road / Pavement',
            'location': 'Mombasa Road'
        }

        res = self.client.post(
            '/api/reports',
            data=payload,
            content_type='multipart/form-data',
            headers={'Authorization': f'Bearer {self.citizen_token}'}
        )

        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn('error', data)

    def test_06_role_authorization_preservation(self):
        """Verifies role authorization: Citizens can list own reports; Engineers can view all."""
        # Citizen request
        res_cit = self.client.get('/api/reports', headers={'Authorization': f'Bearer {self.citizen_token}'})
        self.assertEqual(res_cit.status_code, 200)
        cit_reports = res_cit.get_json().get('reports', [])
        for r in cit_reports:
            self.assertEqual(r['user_id'], 'usr_cit_01')

        # Engineer request
        res_eng = self.client.get('/api/reports', headers={'Authorization': f'Bearer {self.engineer_token}'})
        self.assertEqual(res_eng.status_code, 200)

        # Unauthenticated request
        res_anon = self.client.get('/api/reports')
        self.assertEqual(res_anon.status_code, 401)


if __name__ == '__main__':
    unittest.main()
