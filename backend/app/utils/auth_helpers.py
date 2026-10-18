import re
from datetime import datetime, timezone, timedelta
from functools import wraps
from typing import Tuple
import jwt
from flask import request, jsonify, current_app
from ..services.database import db_service

# Common weak or default passwords that should always be rejected
COMMON_WEAK_PASSWORDS = {
    'password', 'password123', 'admin', 'admin123', '12345678', '123456789',
    'qwerty', 'letmein', 'welcome', 'welcome1', 'pass1234', 'citizen123',
    'engineer123', 'infrastructure', 'kenya2026', 'strathmore'
}

def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Validates password complexity against modern security standards:
    - Minimum 8 characters
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one numeric digit (0-9)
    - At least one special symbol (!@#$%^&*...)
    - Not in list of common weak/default passwords
    """
    if not password:
        return False, "Password is required."

    if len(password) < 8:
        return False, "Password must contain at least 8 characters."

    if password.lower() in COMMON_WEAK_PASSWORDS:
        return False, "This password is too common or easily guessable. Please choose a stronger password."

    if not re.search(r'[A-Z]', password):
        return False, "Password must include at least one uppercase letter (A-Z)."

    if not re.search(r'[a-z]', password):
        return False, "Password must include at least one lowercase letter (a-z)."

    if not re.search(r'\d', password):
        return False, "Password must include at least one numeric digit (0-9)."

    if not re.search(r'[!@#$%^&*()\-_=+\[\]{};:\'",.<>?/\\|`~]', password):
        return False, "Password must include at least one special character (e.g. !@#$%^&*)."

    return True, ""

def validate_ebk_registration(category: str, reg_no: str) -> Tuple[bool, str, str]:
    """
    Validates Kenyan Engineers Board (EBK) professional registration number by category:
    - Graduate Engineer: 'B' followed by digits (e.g. B24512, B12345; does NOT require B0).
    - Professional Engineer: 'A' followed by digits (e.g. A3947).
    - Consulting Engineer: 'E' followed by digits (e.g. E475).

    Returns:
        (is_valid: bool, normalized_reg_no: str, error_message: str)
    """
    if not reg_no or not reg_no.strip():
        return False, "", "EBK Registration Number is required for professional engineer accounts."

    clean_no = re.sub(r'[\s/.-]', '', reg_no.strip().upper())
    # Handle cases where user might have prefixed with 'EBK' e.g. 'EBKB24512'
    if clean_no.startswith('EBK'):
        clean_no = clean_no[3:]

    cat_norm = (category or '').strip().lower()

    if 'graduate' in cat_norm:
        # Graduate Engineer: B followed by 3 to 7 digits
        if not re.match(r'^B\d{3,7}$', clean_no):
            return False, clean_no, "Invalid Graduate Engineer format. Expected 'B' followed by digits (e.g. B24512)."
        return True, clean_no, ""

    elif 'consulting' in cat_norm:
        # Consulting Engineer: E followed by 2 to 6 digits
        if not re.match(r'^E\d{2,7}$', clean_no):
            return False, clean_no, "Invalid Consulting Engineer format. Expected 'E' followed by digits (e.g. E475)."
        return True, clean_no, ""

    elif 'professional' in cat_norm or 'registered' in cat_norm or not cat_norm:
        # Professional Engineer: A followed by 3 to 7 digits (default)
        if not re.match(r'^A\d{3,7}$', clean_no):
            # Check if it's B or E with a clear category mismatch
            if clean_no.startswith('B'):
                return False, clean_no, "Selected category is Professional Engineer, but registration starts with 'B' (Graduate Engineer)."
            elif clean_no.startswith('E'):
                return False, clean_no, "Selected category is Professional Engineer, but registration starts with 'E' (Consulting Engineer)."
            return False, clean_no, "Invalid Professional Engineer format. Expected 'A' followed by digits (e.g. A3947)."
        return True, clean_no, ""

    else:
        # Fallback general EBK format: starts with A, B, or E followed by digits
        if not re.match(r'^[ABE]\d{2,7}$', clean_no):
            return False, clean_no, "Invalid EBK format. Expected 'A', 'B', or 'E' prefix followed by registration digits."
        return True, clean_no, ""

def create_access_token(user):
    """
    Generates a cryptographically signed JWT access token for the authenticated user.
    """
    secret = current_app.config.get('JWT_SECRET_KEY', current_app.config.get('SECRET_KEY', 'dev-secret-key'))
    exp_hours = current_app.config.get('JWT_EXPIRATION_HOURS', 24)
    
    user_id = str(user.get('user_id') or user.get('_id'))
    now = datetime.now(timezone.utc)
    payload = {
        'sub': user_id,
        'user_id': user_id,
        'email': user.get('email', ''),
        'role': user.get('role', 'citizen'),
        'verification_status': user.get('verification_status', 'verified'),
        'iat': now,
        'exp': now + timedelta(hours=exp_hours)
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
