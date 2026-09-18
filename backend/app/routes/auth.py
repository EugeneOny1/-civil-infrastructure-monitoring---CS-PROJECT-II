from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from ..models.user import User, Administrator
from ..services.db import db_service
from ..utils.auth_helpers import get_current_user

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/register', methods=['POST'])
def register():
    """FR-01: User registration for citizens and professional engineers."""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    role = data.get('role', 'citizen').strip().lower()

    if not name or not email or not password:
        return jsonify({'error': 'Name, email, and password are required.'}), 400

    if role not in ['citizen', 'engineer', 'admin']:
        role = 'citizen'

    # Check if user exists
    existing = db_service.find_one('users', {'email': email})
    if existing:
        return jsonify({'error': 'An account with this email address already exists.'}), 409

    # Engineer accounts start with 'pending' verification per FR-01 / FR-10
    verification_status = 'verified' if role == 'citizen' else 'pending'

    user = User(
        name=name,
        email=email,
        password=password,
        role=role,
        verification_status=verification_status
    )
    user_dict = user.to_dict(include_sensitive=True)
    user_id = db_service.insert('users', user_dict)
    user.user_id = user_id

    return jsonify({
        'message': 'Account created successfully.',
        'user': user.to_dict()
    }), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    """FR-01: Authentication with role-based status check."""
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()

    if not email or not password:
        return jsonify({'error': 'Email and password are required.'}), 400

    user_data = db_service.find_one('users', {'email': email})
    if not user_data:
        return jsonify({'error': 'Invalid email or password.'}), 401

    if not check_password_hash(user_data.get('password_hash', ''), password):
        return jsonify({'error': 'Invalid email or password.'}), 401

    user = User.from_dict(user_data)
    return jsonify({
        'message': 'Login successful.',
        'user': user.to_dict(),
        'token': user.user_id
    }), 200

@auth_bp.route('/me', methods=['GET'])
def get_profile():
    """Returns currently authenticated user profile."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'No active user session.'}), 401
    return jsonify({'user': User.from_dict(user).to_dict()})

@auth_bp.route('/demo-users', methods=['GET'])
def get_demo_users():
    """Convenience endpoint returning pre-seeded accounts for testing in UI."""
    users = db_service.find('users')
    sanitized = [User.from_dict(u).to_dict() for u in users]
    return jsonify({'users': sanitized})
