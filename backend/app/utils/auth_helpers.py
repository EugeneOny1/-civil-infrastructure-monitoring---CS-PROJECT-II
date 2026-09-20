from datetime import datetime, timedelta
from functools import wraps
import jwt
from flask import request, jsonify, current_app
from ..services.database import db_service

def create_access_token(user):
    """
    Generates a cryptographically signed JWT access token for the authenticated user.
    """
    secret = current_app.config.get('JWT_SECRET_KEY', current_app.config.get('SECRET_KEY', 'dev-secret-key'))
    exp_hours = current_app.config.get('JWT_EXPIRATION_HOURS', 24)
    
    user_id = str(user.get('user_id') or user.get('_id'))
    payload = {
        'sub': user_id,
        'user_id': user_id,
        'email': user.get('email', ''),
        'role': user.get('role', 'citizen'),
        'verification_status': user.get('verification_status', 'verified'),
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=exp_hours)
    }
    return jwt.encode(payload, secret, algorithm='HS256')

def decode_token(token):
    """
    Decodes and validates a JWT token string.
    Returns payload dict or None if invalid or expired.
    """
    secret = current_app.config.get('JWT_SECRET_KEY', current_app.config.get('SECRET_KEY', 'dev-secret-key'))
    try:
        payload = jwt.decode(token, secret, algorithms=['HS256'])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception):
        return None

def get_current_user():
    """
    Extracts and authenticates the user strictly from the Bearer token in the Authorization header.
    Returns the user document dict, or None if unauthenticated.
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None

    token = auth_header.split(' ', 1)[1].strip()
    payload = decode_token(token)
    if not payload:
        return None

    user_id = payload.get('user_id') or payload.get('sub')
    if not user_id:
        return None

    user = db_service.find_one('users', {'_id': user_id})
    return user

def login_required(f):
    """
    Decorator requiring valid authentication before accessing the endpoint.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required. Please log in.'}), 401
        return f(*args, current_user=user, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    """
    Decorator enforcing role-based access control (RBAC).
    Restricts access to specified roles and verifies engineer accounts before granting professional access.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'error': 'Authentication required. Please log in.'}), 401
            
            user_role = user.get('role', 'citizen')
            
            # Admin role has universal authorization
            if user_role not in allowed_roles and user_role != 'admin':
                allowed_str = ', '.join(allowed_roles)
                return jsonify({
                    'error': f'Access forbidden: Role "{user_role}" lacks permission. Requires: {allowed_str}'
                }), 403

            # Enforce engineer administrative verification per FR-01 & FR-10
            if user_role == 'engineer' and user.get('verification_status') != 'verified':
                return jsonify({
                    'error': 'Engineer account is pending administrative verification. Professional access is not yet granted.'
                }), 403

            return f(*args, current_user=user, **kwargs)
        return decorated_function
    return decorator
