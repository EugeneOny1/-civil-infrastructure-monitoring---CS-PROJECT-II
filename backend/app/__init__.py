import os
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
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

    if config_name == 'production':
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Initialize database service with app config
    db_service.init_app(app)

    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Configure Cross-Origin Resource Sharing (CORS)
    cors_config = app.config.get('CORS_ORIGINS', '*')
    if cors_config == '*':
        cors_origins = '*'
    elif isinstance(cors_config, str):
        cors_origins = [o.strip() for o in cors_config.split(',') if o.strip()]
    else:
        cors_origins = list(cors_config or [])

    if cors_origins:
        CORS(app, resources={r"/api/*": {"origins": cors_origins}})

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(admin_bp)

    # Lightweight Liveness Probe for Azure Container Apps / Cloud Run / Kubernetes
    @app.route('/health', methods=['GET'])
    def liveness_probe():
        """
        Lightweight liveness probe returning immediate HTTP 200 without running inference or exposing secrets.
        """
        return jsonify({'status': 'healthy'}), 200

    # Genuine Readiness Probe verifying TensorFlow SavedModel and persistent DB connectivity
    @app.route('/ready', methods=['GET'])
    @app.route('/api/ready', methods=['GET'])
    def readiness_probe():
        """
        Readiness probe for Azure Container Apps: returns HTTP 200 only once
        the V2.1 SavedModel is loaded (and persistent MongoDB is reachable when required).
        """
        from .services.inference import inference_service
        db_required = bool(app.config.get('REQUIRE_PERSISTENT_DB', False))
        db_ready = db_service.is_connected(verify_ping=True) if db_required else True
        if not inference_service.is_loaded or not db_ready:
            return jsonify({
                'status': 'initializing',
                'model_loaded': bool(inference_service.is_loaded),
                'database_ready': bool(db_ready),
            }), 503
        return jsonify({
            'status': 'ready',
            'model_loaded': True,
            'database_ready': bool(db_ready),
            'model': app.config.get('MODEL_VERSION', 'ssd_mobilenet_v2_lr00015_step1500_v2_1')
        }), 200

    # Detailed System Health & Model Telemetry
    @app.route('/api/health', methods=['GET'])
    def health_check():
        from .services.inference import inference_service
        return jsonify({
            'status': 'online',
            'system': 'Civil Infrastructure Monitoring System',
            'version': '1.0.0',
            'model': app.config.get('MODEL_VERSION', 'ssd_mobilenet_v2_lr00015_step1500_v2_1'),
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
