import random
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from ..models.user import User
from ..services.database import db_service
from ..utils.auth_helpers import create_access_token, get_current_user, login_required

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    FR-01: User registration for citizens, professional engineers, and administrators.
    Citizens are verified immediately for easy reporting.
    Engineers provide professional registration (EBK/IEK) & organization and start as 'pending' verification.
    """
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    role = data.get('role', 'citizen').strip().lower()
    organization = data.get('organization', '').strip()
    professional_reg_no = data.get('professional_reg_no', '').strip()
    phone = data.get('phone', '').strip()
    two_factor_enabled = bool(data.get('two_factor_enabled', False))

    if not name or not email or not password:
        return jsonify({'error': 'Name, email, and password are required.'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must contain at least 6 characters.'}), 400

    if role not in ['citizen', 'engineer', 'admin']:
        role = 'citizen'

    # Check if user already exists
    existing = db_service.find_one('users', {'email': email})
    if existing:
        return jsonify({'error': 'An account with this email address already exists.'}), 409

    # Engineers start with pending verification; citizens are immediately verified
    verification_status = 'verified' if role in ['citizen', 'admin'] else 'pending'

    user = User(
        name=name,
        email=email,
        password=password,
        role=role,
        organization=organization,
        professional_reg_no=professional_reg_no,
        phone=phone,
        two_factor_enabled=two_factor_enabled,
        verification_status=verification_status
    )
    user_dict = user.to_dict(include_sensitive=True)
    user_id = db_service.insert('users', user_dict)
    user.user_id = str(user_id)

    token = create_access_token(user.to_dict())

    if role == 'engineer':
        message = 'Engineer account registered and submitted for administrative accreditation verification.'
    elif role == 'admin':
        message = 'Administrator account registered successfully.'
    else:
        message = 'Citizen reporter account created successfully.'

    return jsonify({
        'message': message,
        'user': user.to_dict(),
        'token': token
    }), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    FR-01: Authenticate user credentials and return signed JWT token.
    Supports email OTP Two-Factor Authentication (2FA) for professional engineer/admin accounts.
    """
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    otp_code = str(data.get('otp_code', '')).strip()

    if not email or not password:
        return jsonify({'error': 'Email and password are required.'}), 400

    user_data = db_service.find_one('users', {'email': email})
    if not user_data:
        return jsonify({'error': 'Invalid email or password.'}), 401

    if not check_password_hash(user_data.get('password_hash', ''), password):
        return jsonify({'error': 'Invalid email or password.'}), 401

    user = User.from_dict(user_data)

    # Check if 2FA is enabled or requested for this account (optional for citizens, recommended for engineers/admins)
    has_2fa = user.two_factor_enabled or data.get('require_2fa') is True

    # If 2FA is required and OTP was provided in this request, verify it
    if has_2fa and otp_code:
        stored_otp = str(user_data.get('two_factor_otp', ''))
        # Accept matched generated OTP or master development code '123456'
        if otp_code != stored_otp and otp_code != '123456':
            return jsonify({'error': 'Invalid or expired 2FA verification code.'}), 401
        
        # Clear one-time code after verification
        db_service.update_one('users', {'_id': user_data['_id']}, {'two_factor_otp': None})
        token = create_access_token(user.to_dict())
        return jsonify({
            'message': '2FA verification successful. Logged in.',
            'user': user.to_dict(),
            'token': token
        }), 200

    # If 2FA is enabled but no OTP provided yet, challenge the user
    if has_2fa:
        otp = str(random.randint(100000, 999999))
        expiry = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        db_service.update_one('users', {'_id': user_data['_id']}, {
            'two_factor_otp': otp,
            'two_factor_exp': expiry
        })
        print(f"[Security / 2FA] Verification OTP dispatched for {email}: {otp}")

        return jsonify({
            'require_2fa': True,
            'email': email,
            'role': user.role,
            'demo_otp': otp,
            'message': f"A 6-digit verification code has been dispatched to {email}. (Demo Passcode: {otp} or 123456)"
        }), 200

    # Standard direct login (e.g. for citizens or accounts without 2FA)
    token = create_access_token(user.to_dict())

    return jsonify({
        'message': 'Login successful.',
        'user': user.to_dict(),
        'token': token
    }), 200

@auth_bp.route('/verify-2fa', methods=['POST'])
def verify_2fa():
    """
    Verifies 2FA OTP code and returns signed JWT token.
    """
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    otp_code = str(data.get('otp_code', '')).strip()

    if not email or not otp_code:
        return jsonify({'error': 'Email and 6-digit OTP code are required.'}), 400

    user_data = db_service.find_one('users', {'email': email})
    if not user_data:
        return jsonify({'error': 'User account not found.'}), 404

    stored_otp = str(user_data.get('two_factor_otp', ''))
    if otp_code != stored_otp and otp_code != '123456':
        return jsonify({'error': 'Invalid 2FA security code. Please check your email or use test code 123456.'}), 401

    # Clear OTP after successful verification
    db_service.update_one('users', {'_id': user_data['_id']}, {'two_factor_otp': None})

    user = User.from_dict(user_data)
    token = create_access_token(user.to_dict())

    return jsonify({
        'message': '2FA verification successful. Access granted.',
        'user': user.to_dict(),
        'token': token
    }), 200

@auth_bp.route('/toggle-2fa', methods=['POST'])
@login_required
def toggle_2fa(current_user):
    """
    Toggles Two-Factor Authentication on/off for current user.
    """
    user_id = str(current_user.get('_id') or current_user.get('user_id'))
    data = request.get_json() or {}
    enable = data.get('enable')
    
    current_state = current_user.get('two_factor_enabled', False)
    new_state = not current_state if enable is None else bool(enable)

    db_service.update_one('users', {'_id': user_id}, {'two_factor_enabled': new_state})

    return jsonify({
        'message': f"Two-Factor Authentication has been {'enabled' if new_state else 'disabled'}.",
        'two_factor_enabled': new_state
    }), 200

@auth_bp.route('/me', methods=['GET'])
@login_required
def get_profile(current_user):
    """
    Returns the authenticated user profile.
    """
    return jsonify({'user': User.from_dict(current_user).to_dict()}), 200

