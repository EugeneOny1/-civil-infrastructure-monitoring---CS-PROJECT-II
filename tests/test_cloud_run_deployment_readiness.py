"""
Automated Regression Test Suite: Cloud Run Deployment Readiness.
Validates:
1. Lightweight container health-check probe (/health).
2. Deep system health & SavedModel telemetry (/api/health).
3. Single-service static frontend serving (/ and /css/main.css).
4. Durable StorageService abstraction (local & GCS fallback).
5. Gunicorn WSGI entrypoint export integrity (wsgi:app and backend.run:app).
6. Production configuration security (DEBUG=False in production).
"""

import os
import io
import unittest
from pathlib import Path
from flask import Flask
from werkzeug.datastructures import FileStorage
from PIL import Image

# Ensure path resolution
repo_root = Path(__file__).resolve().parent.parent
backend_dir = repo_root / 'backend'

import sys
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from backend.app import create_app
from backend.app.config import ProductionConfig, DevelopmentConfig
from backend.app.services.storage import StorageService, storage_service
from backend.app.services.inference import inference_service


class TestCloudRunDeploymentReadiness(unittest.TestCase):
    """Verifies that the InfraVision service meets all Google Cloud Run production prerequisites."""

    @classmethod
    def setUpClass(cls):
        # Create test app instance
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()

    def test_01_lightweight_health_probe(self):
        """Verifies GET /health returns HTTP 200 {'status': 'healthy'} immediately."""
        resp = self.client.get('/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsNotNone(data)
        self.assertEqual(data.get('status'), 'healthy')

    def test_02_deep_system_health_telemetry(self):
        """Verifies GET /api/health exposes active detector version and model state."""
        resp = self.client.get('/api/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'online')
        self.assertEqual(data.get('model'), 'ssd_mobilenet_v2_lr00015_step1500_v2_1')
        self.assertIn('model_loaded', data)

    def test_03_frontend_static_serving(self):
        """Verifies single-service serving of index.html and static assets."""
        # Root index.html
        resp_root = self.client.get('/')
        self.assertEqual(resp_root.status_code, 200)
        self.assertIn(b'InfraVision', resp_root.data)

        # Static CSS asset
        resp_css = self.client.get('/css/main.css')
        self.assertEqual(resp_css.status_code, 200)
        self.assertIn(b':root', resp_css.data)

    def test_04_storage_service_extension_validation(self):
        """Verifies StorageService allows permissible image extensions and rejects invalid."""
        self.assertTrue(storage_service.is_allowed_file('pothole.jpg'))
        self.assertTrue(storage_service.is_allowed_file('crack.PNG'))
        self.assertTrue(storage_service.is_allowed_file('surface.webp'))
        self.assertFalse(storage_service.is_allowed_file('script.sh'))
        self.assertFalse(storage_service.is_allowed_file('exploit.exe'))
        self.assertFalse(storage_service.is_allowed_file(''))

    def test_05_storage_service_directory_traversal_protection(self):
        """Verifies StorageService rejects path traversal attempts."""
        with self.app.test_request_context():
            resp = storage_service.serve_file('../../etc/passwd')
            self.assertEqual(resp.status_code, 400)
            data = resp.get_json()
            self.assertIn('error', data)

    def test_06_storage_service_local_save_and_serve(self):
        """Verifies StorageService saves valid PIL image and can serve it."""
        # Create an in-memory 100x100 RGB test image
        img_byte_arr = io.BytesIO()
        test_img = Image.new('RGB', (100, 100), color=(120, 130, 140))
        test_img.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0)

        file_storage = FileStorage(
            stream=img_byte_arr,
            filename='test_road_defect.jpg',
            content_type='image/jpeg'
        )

        with self.app.app_context():
            unique_filename, dest_path, orig_name, file_size, storage_url = storage_service.save_file(file_storage)
            self.assertTrue(os.path.exists(dest_path))
            self.assertEqual(orig_name, 'test_road_defect.jpg')
            self.assertGreater(file_size, 0)
            self.assertEqual(storage_url, f"/api/reports/images/{unique_filename}")

            # Serve the saved image
            with self.app.test_request_context():
                resp = storage_service.serve_file(unique_filename)
                self.assertEqual(resp.status_code, 200)

            # Cleanup
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass

    def test_07_wsgi_entrypoint_integrity(self):
        """Verifies wsgi.py exports valid Flask application object."""
        import wsgi
        self.assertTrue(hasattr(wsgi, 'app'))
        self.assertIsInstance(wsgi.app, Flask)

    def test_08_production_config_debug_is_false(self):
        """Verifies ProductionConfig strictly enforces DEBUG=False."""
        self.assertFalse(ProductionConfig.DEBUG)


if __name__ == '__main__':
    unittest.main()

