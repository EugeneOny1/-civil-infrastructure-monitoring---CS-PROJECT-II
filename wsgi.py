"""
WSGI Entry Point for InfraVision Production Deployment on Google Cloud Run.
Serves the unified single-service application (Flask API + Static Frontend + SSD-MobileNetV2 Detector).
"""
import os
import sys
from pathlib import Path

# Ensure root and backend directories are on sys.path
root_dir = Path(__file__).resolve().parent
backend_dir = root_dir / 'backend'
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from backend.run import app

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
