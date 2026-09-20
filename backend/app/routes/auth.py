from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from ..models.user import User
from ..services.database import db_service
from ..utils.auth_helpers import create_access_token, get_current_user, login_required

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    FR-01: User registration for citizens and professional engineers.
    Engineer accounts require administrative verification before access to review functions.
    """
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    role = data.get('role', 'citizen').strip().lower()

    if not name or not email or not password:
        return jsonify({'error': 'Name, email, and password are required.'}), 400

    if role not in ['citizen', 'engineer']:
        role = 'citizen'

    # Check if user already exists
    existing = db_service.find_one('users', {'email': email})
    if existing:
        return jsonify({'error': 'An account with this email address already exists.'}), 409

    # Engineers start with pending verification; citizens are immediately verified
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
    user.user_id = str(user_id)

    token = create_access_token(user.to_dict())

    message = (
        'Citizen account created successfully.'
        if role == 'citizen'
        else 'Engineer account submitted for administrative verification.'
    )

    return jsonify({
        'message': message,
        'user': user.to_dict(),
        'token': token
    }), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    FR-01: Authenticate user credentials and return signed JWT token.
    """
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
    token = create_access_token(user.to_dict())

    return jsonify({
        'message': 'Login successful.',
        'user': user.to_dict(),
        'token': token
    }), 200

@auth_bp.route('/me', methods=['GET'])
@login_required
def get_profile(current_user):
    """
    Returns the authenticated user profile.
    """
    return jsonify({'user': User.from_dict(current_user).to_dict()}), 200
