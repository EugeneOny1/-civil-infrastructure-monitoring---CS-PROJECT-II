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
    
    # JWT Authentication
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
    JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', '24'))
    
    # MongoDB Configuration
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/civil_infrastructure')
    DB_NAME = os.getenv('DB_NAME', 'civil_infrastructure')

    # File uploads
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', str(BASE_DIR / 'uploads'))
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16 MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

    # Machine Learning / AI Model
    MODEL_PATH = os.getenv('MODEL_PATH', str(BASE_DIR / 'models' / 'structural_defect_detector'))
    MODEL_DIR = os.getenv('MODEL_DIR', str(BASE_DIR / 'models'))
    MODEL_NAME = 'SSD-MobileNetV2'
    MODEL_VERSION = os.getenv('MODEL_VERSION', 'ssd_mobilenet_v2_lr00125_step5000_v1')
    DETECTION_CONFIDENCE_THRESHOLD = float(os.getenv('DETECTION_CONFIDENCE_THRESHOLD', '0.30'))

    # Target defect classes defined in project proposal & label_map.pbtxt
    CLASS_NAMES = {
        1: 'Crack',
        2: 'Pothole',
        3: 'Surface deterioration'
    }
    DEFECT_CLASSES = ['Crack', 'Pothole', 'Surface deterioration']

    # Severity assessment thresholds (relative bounding box area to image area)
    # FR-04: Defect extent mapped to Low, Moderate, High/Critical
    SEVERITY_LOW_THRESHOLD = float(os.getenv('SEVERITY_LOW_THRESHOLD', '0.05'))       # < 5%
    SEVERITY_CRITICAL_THRESHOLD = float(os.getenv('SEVERITY_CRITICAL_THRESHOLD', '0.15')) # >= 15%
    DUPLICATE_IOU_THRESHOLD = float(os.getenv('DUPLICATE_IOU_THRESHOLD', '0.50'))

    # Two-Factor Authentication (2FA) & Real Email Delivery (SMTP)
    SMTP_HOST = os.getenv('SMTP_HOST', '').strip()
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USER = os.getenv('SMTP_USER', '').strip()
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '').strip()
    SMTP_SENDER = os.getenv('SMTP_SENDER', 'infravision-alerts@strathmore.edu').strip()
    SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'True').lower() in ('true', '1', 't')

    # OTP Lifecycle & Rate Limits
    OTP_EXPIRY_SECONDS = int(os.getenv('OTP_EXPIRY_SECONDS', '300'))  # 5 minutes
    OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv('OTP_RESEND_COOLDOWN_SECONDS', '60'))  # 60 seconds
    OTP_MAX_ATTEMPTS = int(os.getenv('OTP_MAX_ATTEMPTS', '5'))  # 5 attempts max
    OTP_MAX_SENDS_PER_HOUR = int(os.getenv('OTP_MAX_SENDS_PER_HOUR', '5'))  # 5 sends per hour max
    ENABLE_DEMO_OTP = os.getenv('ENABLE_DEMO_OTP', 'True').lower() in ('true', '1', 't')

    # Google Authentication (OAuth2 / GIS)
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '').strip()
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '').strip()

    # GIS / Mapping (Leaflet + OpenStreetMap)
    MAP_PROVIDER = os.getenv('MAP_PROVIDER', 'leaflet').strip()
    MAP_DEFAULT_LAT = float(os.getenv('MAP_DEFAULT_LAT', '-1.286389'))
    MAP_DEFAULT_LNG = float(os.getenv('MAP_DEFAULT_LNG', '36.817223'))
    MAP_DEFAULT_ZOOM = int(os.getenv('MAP_DEFAULT_ZOOM', '12'))

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
