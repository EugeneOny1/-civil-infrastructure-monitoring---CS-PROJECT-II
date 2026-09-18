import os
from pathlib import Path
from dotenv import load_dotenv

# Base project directories
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

# Load .env if present
load_dotenv(BASE_DIR / '.env')
load_dotenv(ROOT_DIR / '.env')

class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv('SECRET_KEY', 'civil-infra-default-dev-secret-key-2026')
    DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')
    
    # MongoDB Configuration
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/civil_infrastructure')
    DB_NAME = os.getenv('DB_NAME', 'civil_infrastructure')

    # File uploads
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', str(BASE_DIR / 'uploads'))
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16 MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

    # Machine Learning / AI Model
    MODEL_DIR = os.getenv('MODEL_DIR', str(ROOT_DIR / 'models'))
    MODEL_NAME = 'SSD-MobileNetV2'
    MODEL_VERSION = os.getenv('MODEL_VERSION', 'SSD-MobileNetV2-v1.0')

    # Target defect classes defined in project proposal
    DEFECT_CLASSES = ['Crack', 'Pothole', 'Surface Deterioration']

    # Severity assessment thresholds (relative bounding box area to image area)
    # FR-04: Defect extent mapped to Low, Medium, Critical
    SEVERITY_LOW_THRESHOLD = float(os.getenv('SEVERITY_LOW_THRESHOLD', '0.05'))       # < 5%
    SEVERITY_CRITICAL_THRESHOLD = float(os.getenv('SEVERITY_CRITICAL_THRESHOLD', '0.15')) # >= 15%

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
