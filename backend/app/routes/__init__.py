from .auth import auth_bp
from .reports import reports_bp
from .assets import assets_bp
from .reviews import reviews_bp
from .analytics import analytics_bp
from .admin import admin_bp

__all__ = [
    'auth_bp',
    'reports_bp',
    'assets_bp',
    'reviews_bp',
    'analytics_bp',
    'admin_bp'
]
