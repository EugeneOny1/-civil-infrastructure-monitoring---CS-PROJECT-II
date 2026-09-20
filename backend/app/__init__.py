import os
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from .config import config_by_name
from .services.database import db_service
from .routes import auth_bp, users_bp, reports_bp, assets_bp, reviews_bp, analytics_bp, admin_bp

def create_app(config_name=None):
    """
    Application factory for the Civil Infrastructure Monitoring System.
    Configures Flask, enables CORS, registers REST blueprints, and mounts static frontend.
    """
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    base_dir = Path(__file__).resolve().parent.parent
    root_dir = base_dir.parent
    frontend_dir = root_dir / 'frontend'

    app = Flask(
        __name__,
        static_folder=str(frontend_dir),
        static_url_path=''
    )
    
    # Load configuration
    cfg = config_by_name.get(config_name, config_by_name['default'])
    app.config.from_object(cfg)

    # Initialize database service with app config
    db_service.init_app(app)

    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Enable Cross-Origin Resource Sharing
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(admin_bp)

    # Health check endpoint
    @app.route('/api/health', methods=['GET'])
    def health_check():
        return jsonify({
            'status': 'online',
            'system': 'Civil Infrastructure Monitoring System',
            'version': '1.0.0',
            'model': app.config.get('MODEL_VERSION', 'SSD-MobileNetV2-v1.0')
        })

    # Serve Frontend Single Page App
    @app.route('/')
    def serve_frontend():
        return send_from_directory(str(frontend_dir), 'index.html')

    @app.route('/<path:path>')
    def serve_static(path):
        target_file = frontend_dir / path
        if target_file.exists():
            return send_from_directory(str(frontend_dir), path)
        return send_from_directory(str(frontend_dir), 'index.html')

    return app
