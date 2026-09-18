from functools import wraps
from flask import request, jsonify, current_app
from ..services.db import db_service

def get_current_user():
    """
    Extracts the authenticated user from the Authorization header or X-User-Id header.
    Allows easy role switching during demonstration and testing.
    """
    auth_header = request.headers.get('Authorization', '')
    user_id = request.headers.get('X-User-Id')

    if auth_header.startswith('Bearer '):
        token_id = auth_header.split(' ', 1)[1].strip()
        user_id = user_id or token_id

    if not user_id:
        # Default to demo citizen if unauthenticated (for public submission testing)
        user = db_service.find_one('users', {'role': 'citizen'})
        return user

    user = db_service.find_one('users', {'_id': user_id})
    if not user:
        user = db_service.find_one('users', {'email': user_id})
    return user

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required to perform this action.'}), 401
        return f(*args, current_user=user, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    """
    Enforces role-based access control (e.g., only 'engineer' or 'admin' can sign off).
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'error': 'Authentication required.'}), 401
            
            user_role = user.get('role', 'citizen')
            if user_role not in allowed_roles and 'admin' not in allowed_roles:
                return jsonify({
                    'error': f'Access forbidden: Role "{user_role}" lacks permission. Requires: {list(allowed_roles)}'
                }), 403
            
            # Check verification status for engineers per FR-01 / FR-10
            if user_role == 'engineer' and user.get('verification_status') != 'verified':
                return jsonify({'error': 'Engineer account pending administrative verification.'}), 403

            return f(*args, current_user=user, **kwargs)
        return decorated_function
    return decorator
