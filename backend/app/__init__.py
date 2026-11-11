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

    # Robust frontend directory resolution for local dev & container runtimes
    env_frontend = os.getenv('FRONTEND_DIR')
    if env_frontend and Path(env_frontend).exists():
        frontend_dir = Path(env_frontend).resolve()
    elif (root_dir / 'frontend').exists():
        frontend_dir = (root_dir / 'frontend').resolve()
    elif (base_dir / 'frontend').exists():
        frontend_dir = (base_dir / 'frontend').resolve()
    else:
        frontend_dir = (root_dir / 'frontend').resolve()

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

    # Configure Cross-Origin Resource Sharing (CORS)
    cors_config = app.config.get('CORS_ORIGINS', '*')
    if cors_config == '*' or not cors_config:
        cors_origins = '*'
    elif isinstance(cors_config, str):
        cors_origins = [o.strip() for o in cors_config.split(',') if o.strip()]
    else:
        cors_origins = cors_config

    CORS(app, resources={r"/api/*": {"origins": cors_origins}})

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(admin_bp)

    # Lightweight Liveness Probe for Cloud Run / Kubernetes Load Balancers
    @app.route('/health', methods=['GET'])
    def liveness_probe():
        """
        Lightweight health-check endpoint for Google Cloud Run container liveness.
        Returns immediate HTTP 200 without executing expensive inference or exposing secrets.
        """
        return jsonify({'status': 'healthy'}), 200

    # Detailed System Health & Model Telemetry
    @app.route('/api/health', methods=['GET'])
    def health_check():
        from .services.inference import inference_service
        return jsonify({
            'status': 'online',
            'system': 'Civil Infrastructure Monitoring System',
            'version': '1.0.0',
            'model': app.config.get('MODEL_VERSION', 'ssd_mobilenet_v2_lr00625_step8000_v2'),
            'model_loaded': inference_service.is_loaded,
            'model_name': inference_service.model_name
        })

    # Serve Frontend Single Page App
    @app.route('/')
    def serve_frontend():
        return send_from_directory(str(frontend_dir), 'index.html')

    @app.route('/<path:path>')
    def serve_static(path):
        target_file = frontend_dir / path
        if target_file.exists() and target_file.is_file():
            return send_from_directory(str(frontend_dir), path)
        return send_from_directory(str(frontend_dir), 'index.html')

    return app
