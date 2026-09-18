import os
import sys
from pathlib import Path

# Ensure backend directory is on Python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app

app = create_app(os.getenv('FLASK_ENV', 'development'))

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')
    print(f"===============================================================")
    print(f"  Civil Infrastructure Monitoring System - Backend Server      ")
    print(f"  Computer Vision & AI Defect Detection (SSD-MobileNetV2)      ")
    print(f"  Strathmore University - ICS Project II                       ")
    print(f"  Serving on: http://127.0.0.1:{port}                          ")
    print(f"===============================================================")
    app.run(host='0.0.0.0', port=port, debug=debug)
