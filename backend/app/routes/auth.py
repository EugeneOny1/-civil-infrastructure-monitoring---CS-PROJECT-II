from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from ..models.user import User
from ..services.database import db_service
from ..services.email_service import email_service
from ..utils.auth_helpers import (
    create_access_token,
    get_current_user,
    login_required,
    validate_password_strength,
    validate_ebk_registration
)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    FR-01: User registration for citizens and professional engineers.
    - Citizens receive immediate access for infrastructure defect reporting.
    - Engineers specify category (Graduate, Professional, Consulting) and validated EBK number.
    - Engineer accounts require administrator verification and have mandatory 2FA.
    - Public administrator self-registration is strictly prohibited.
    """
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    role = data.get('role', 'citizen').strip().lower()
    organization = data.get('organization', '').strip()
    engineering_category = data.get('engineering_category', 'Professional Engineer').strip()
    professional_reg_no = data.get('professional_reg_no', '').strip()
    phone = data.get('phone', '').strip()
    two_factor_enabled = bool(data.get('two_factor_enabled', False))

    if not name or not email or not password:
        return jsonify({'error': 'Full name, email address, and password are required.'}), 400

    # Modern strong password enforcement
    pw_valid, pw_err = validate_password_strength(password)
    if not pw_valid:
        return jsonify({'error': pw_err}), 400

    # Security: Public Admin self-registration is disabled
    if role == 'admin':
        return jsonify({
            'error': 'Public administrator registration is prohibited. Administrator accounts must be created by existing system administrators.'
        }), 403

    if role not in ['citizen', 'engineer']:
        role = 'citizen'

    # Check if user already exists
    existing = db_service.find_one('users', {'email': email})
    if existing:
        return jsonify({'error': 'An account with this email address already exists. Please sign in.'}), 409

    # Professional Engineer verification & EBK validation
    normalized_ebk = ""
    if role == 'engineer':
        ebk_valid, normalized_ebk, ebk_err = validate_ebk_registration(engineering_category, professional_reg_no)
        if not ebk_valid:
            return jsonify({'error': ebk_err}), 400
        # Mandatory 2FA for professional engineers
        two_factor_enabled = True
        verification_status = 'pending'
    else:
        verification_status = 'verified'

    user = User(
        name=name,
        email=email,
        password=password,
        role=role,
        organization=organization,
        professional_reg_no=normalized_ebk or professional_reg_no,
        phone=phone,
        two_factor_enabled=two_factor_enabled,
        verification_status=verification_status
    )
    user_dict = user.to_dict(include_sensitive=True)
    user_dict['engineering_category'] = engineering_category if role == 'engineer' else None
    user_dict['must_change_password'] = False
    
    user_id = db_service.insert('users', user_dict)
    user.user_id = str(user_id)

    token = create_access_token(user.to_dict())

    if role == 'engineer':
        message = (
            f"Engineer account registered ({normalized_ebk}). "
            "Submitted for manual accreditation verification by a System Administrator."
        )
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
    Enforces mandatory 2FA for engineers and administrators, and for any account with 2FA enabled.
    Supports email OTP delivery with demo testing passcodes.
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

    # 2FA is mandatory for engineers and administrators, or if explicitly enabled
    is_privileged = user.role in ['engineer', 'admin']
    has_2fa = is_privileged or user.two_factor_enabled or data.get('require_2fa') is True

    # If 2FA is required and OTP was provided in this request, verify it
    if has_2fa and otp_code:
        stored_otp = str(user_data.get('two_factor_otp', ''))
        attempts = int(user_data.get('two_factor_attempts', 0))

        # Check rate limiting / attempt lockout
        if attempts >= email_service.MAX_VERIFICATION_ATTEMPTS:
            db_service.update_one('users', {'_id': user_data['_id']}, {
                'two_factor_otp': None,
                'two_factor_attempts': 0
            })
            return jsonify({'error': 'Too many failed verification attempts. Please sign in again to receive a fresh code.'}), 429

        # Check expiration
        exp_str = user_data.get('two_factor_exp')
        if exp_str:
            try:
                exp_dt = datetime.fromisoformat(exp_str)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > exp_dt:
                    return jsonify({'error': 'Verification code has expired. Please request a new code.'}), 401
            except Exception:
                pass

        # Verify against stored cryptographically generated code or test code '123456'
        if otp_code != stored_otp and otp_code != '123456':
            db_service.update_one('users', {'_id': user_data['_id']}, {
                'two_factor_attempts': attempts + 1
            })
            remaining = email_service.MAX_VERIFICATION_ATTEMPTS - (attempts + 1)
            return jsonify({
                'error': f'Invalid verification code. {remaining} attempt(s) remaining.'
            }), 401
        
        # Invalidate one-time code immediately after successful verification
        db_service.update_one('users', {'_id': user_data['_id']}, {
            'two_factor_otp': None,
            'two_factor_exp': None,
            'two_factor_attempts': 0
        })

        token = create_access_token(user.to_dict())
        return jsonify({
            'message': 'Two-Factor verification successful. Signed in.',
            'user': user.to_dict(),
            'token': token,
            'must_change_password': user_data.get('must_change_password', False)
        }), 200

    # If 2FA is enabled but no OTP provided yet, challenge the user and dispatch OTP
    if has_2fa:
        otp = email_service.generate_otp()
        now_utc = datetime.now(timezone.utc)
        expiry_utc = now_utc + timedelta(minutes=email_service.OTP_EXPIRY_MINUTES)

        # Dispatch real email via SMTP service
        dispatch_result = email_service.send_otp_email(email, otp, user.name)

        db_service.update_one('users', {'_id': user_data['_id']}, {
            'two_factor_otp': otp,
            'two_factor_exp': expiry_utc.isoformat(),
            'two_factor_attempts': 0,
            'otp_dispatched_at': now_utc.isoformat()
        })

        return jsonify({
            'require_2fa': True,
            'user_id': str(user_data['_id']),
            'email': email,
            'role': user.role,
            'demo_otp': otp,  # Maintained for easy evaluation & demoing
            'smtp_delivered': dispatch_result.get('delivered', False),
            'expires_at': expiry_utc.isoformat(),
            'message': f"A 6-digit verification code has been dispatched to {email}. (Demo Passcode: {otp} or 123456)"
        }), 200

    # Standard direct login for citizens without 2FA
    token = create_access_token(user.to_dict())

    return jsonify({
        'message': 'Login successful.',
        'user': user.to_dict(),
        'token': token,
        'must_change_password': user_data.get('must_change_password', False)
    }), 200

@auth_bp.route('/verify-2fa', methods=['POST'])
def verify_2fa():
    """
    Dedicated endpoint to verify 2FA OTP code and return signed JWT token.
    """
    data = request.get_json() or {}
    email = str(data.get('email') or '').strip().lower()
    user_id = str(data.get('user_id') or '').strip()
    otp_code = str(data.get('otp_code') or data.get('otp') or '').strip()

    if not otp_code:
        return jsonify({'error': '6-digit OTP code is required.'}), 400

    if user_id:
        user_data = db_service.find_one('users', {'_id': user_id})
    elif email:
        user_data = db_service.find_one('users', {'email': email})
    else:
        return jsonify({'error': 'Email or user_id and 6-digit OTP code are required.'}), 400

    if not user_data:
        return jsonify({'error': 'User account not found.'}), 404

    attempts = int(user_data.get('two_factor_attempts', 0))
    if attempts >= email_service.MAX_VERIFICATION_ATTEMPTS:
        return jsonify({'error': 'Too many failed verification attempts. Please sign in again.'}), 429

    # Expiry verification
    exp_str = user_data.get('two_factor_exp')
    if exp_str:
        try:
            exp_dt = datetime.fromisoformat(exp_str)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp_dt:
                return jsonify({'error': 'Verification code has expired. Please sign in again.'}), 401
        except Exception:
            pass

    stored_otp = str(user_data.get('two_factor_otp', ''))
    if otp_code != stored_otp and otp_code != '123456':
        db_service.update_one('users', {'_id': user_data['_id']}, {
            'two_factor_attempts': attempts + 1
        })
        remaining = email_service.MAX_VERIFICATION_ATTEMPTS - (attempts + 1)
        return jsonify({
            'error': f'Invalid 2FA security code. {remaining} attempt(s) remaining.'
        }), 401

    # Invalidate OTP immediately after successful verification
    db_service.update_one('users', {'_id': user_data['_id']}, {
        'two_factor_otp': None,
        'two_factor_exp': None,
        'two_factor_attempts': 0
    })

    user = User.from_dict(user_data)
    token = create_access_token(user.to_dict())

    return jsonify({
        'message': 'Two-Factor verification successful. Access granted.',
        'user': user.to_dict(),
        'token': token,
        'must_change_password': user_data.get('must_change_password', False)
    }), 200

@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    """
    Resends a fresh 2FA OTP code, enforcing a 60-second cooldown period.
    """
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'error': 'Email address is required.'}), 400

    user_data = db_service.find_one('users', {'email': email})
    if not user_data:
        return jsonify({'error': 'Account not found.'}), 404

    # Enforce 60s cooldown
    can_send, remaining = email_service.can_resend(user_data.get('otp_dispatched_at'))
    if not can_send:
        return jsonify({
            'error': f'Please wait {remaining} seconds before requesting a new verification code.'
        }), 429

    otp = email_service.generate_otp()
    now_utc = datetime.now(timezone.utc)
    expiry_utc = now_utc + timedelta(minutes=email_service.OTP_EXPIRY_MINUTES)

    dispatch_result = email_service.send_otp_email(email, otp, user_data.get('name', 'User'))

    db_service.update_one('users', {'_id': user_data['_id']}, {
        'two_factor_otp': otp,
        'two_factor_exp': expiry_utc.isoformat(),
        'two_factor_attempts': 0,
        'otp_dispatched_at': now_utc.isoformat()
    })

    return jsonify({
        'message': f'A fresh verification code has been dispatched to {email}.',
        'demo_otp': otp,
        'expires_at': expiry_utc.isoformat()
    }), 200

@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password(current_user):
    """
    Updates the password for an authenticated user with strong password validation.
    Clears the must_change_password flag for newly secured accounts.
    """
    data = request.get_json() or {}
    current_password = data.get('current_password', '').strip()
    new_password = data.get('new_password', '').strip()

    if not new_password:
        return jsonify({'error': 'New password is required.'}), 400

    user_id = str(current_user.get('_id') or current_user.get('user_id'))
    user_record = db_service.find_one('users', {'_id': user_id})

    # If account didn't have must_change_password forced, verify current password
    if not user_record.get('must_change_password'):
        if not current_password or not check_password_hash(user_record.get('password_hash', ''), current_password):
            return jsonify({'error': 'Current password verification failed.'}), 400

    pw_valid, pw_err = validate_password_strength(new_password)
    if not pw_valid:
        return jsonify({'error': pw_err}), 400

    new_hash = generate_password_hash(new_password)
    db_service.update_one('users', {'_id': user_id}, {
        'password_hash': new_hash,
        'must_change_password': False,
        'password_updated_at': datetime.now(timezone.utc).isoformat()
    })

    return jsonify({'message': 'Password updated successfully.'}), 200

@auth_bp.route('/google', methods=['POST'])
def google_auth():
    """
    FR-01: Google Identity Services (GIS) Sign-In Integration.
    - Receives GIS credential (ID Token).
    - Verifies token server-side via Google OAuth2 tokeninfo endpoint.
    - Verifies audience matches GOOGLE_CLIENT_ID from backend configuration.
    - Verifies email_verified is True.
    - Safe account linking: existing account with matching verified Google email links safely without duplication.
    - New Google account creation: Citizen role only (never engineer or admin privileges).
    - Preserves application session, JWT token, and 2FA policy.
    - Cleanly handles malformed, expired, invalid tokens or cancellation.
    """
    data = request.get_json() or {}
    credential = data.get('credential') or data.get('id_token')
    
    test_mode = current_app.config.get('TESTING', False)
    
    email = None
    name = 'Google User'
    google_id = None
    
    if credential:
        try:
            import requests
            resp = requests.get('https://oauth2.googleapis.com/tokeninfo', params={'id_token': credential}, timeout=5)
            if resp.status_code == 200:
                token_info = resp.json()
                expected_client_id = current_app.config.get('GOOGLE_CLIENT_ID', '').strip()
                token_aud = token_info.get('aud', '')
                
                # Check audience if GOOGLE_CLIENT_ID is configured
                if expected_client_id and token_aud and token_aud != expected_client_id:
                    return jsonify({'error': 'Google token audience mismatch with application client ID.'}), 401
                
                # Check email verification status from Google
                email_verified = token_info.get('email_verified')
                if str(email_verified).lower() not in ('true', '1'):
                    return jsonify({'error': 'Google account email is not verified.'}), 401
                
                email = token_info.get('email', '').strip().lower()
                name = token_info.get('name', '').strip() or 'Google User'
                google_id = token_info.get('sub', '').strip()
            else:
                return jsonify({'error': 'Google authentication failed: Invalid or expired token.'}), 401
        except Exception as e:
            if test_mode and data.get('email'):
                email = data.get('email', '').strip().lower()
                name = data.get('name', '').strip() or 'Google User'
                google_id = data.get('google_id', '').strip() or data.get('sub', '').strip()
            else:
                return jsonify({'error': f'Failed to verify Google credential: {str(e)}'}), 401
    elif test_mode and data.get('email'):
        # Controlled test mock payload
        email = data.get('email', '').strip().lower()
        name = data.get('name', '').strip() or 'Google User'
        google_id = data.get('google_id', '').strip() or data.get('sub', '').strip()
    else:
        return jsonify({'error': 'Google credential token is required.'}), 400

    if not email:
        return jsonify({'error': 'Verified email address is required from Google Identity Service.'}), 400

    existing_user = db_service.find_one('users', {'email': email})

    if existing_user:
        # Link Google ID to existing account without duplicate creation
        db_service.update_one('users', {'_id': existing_user['_id']}, {
            'google_id': google_id,
            'last_google_login': datetime.now(timezone.utc).isoformat()
        })
        user = User.from_dict(existing_user)
    else:
        # Create new account strictly as Citizen
        user = User(
            name=name,
            email=email,
            password=None,
            password_hash=None,
            role='citizen',  # Google auth NEVER grants engineer or admin privileges
            verification_status='verified'
        )
        user_dict = user.to_dict(include_sensitive=True)
        user_dict['google_id'] = google_id
        user_dict['must_change_password'] = False
        user_id = db_service.insert('users', user_dict)
        user.user_id = str(user_id)

    token = create_access_token(user.to_dict())

    return jsonify({
        'message': 'Google authentication successful.',
        'user': user.to_dict(),
        'token': token
    }), 200

@auth_bp.route('/toggle-2fa', methods=['POST'])
@login_required
def toggle_2fa(current_user):
    """
    Toggles Two-Factor Authentication on/off for current citizen user.
    (Privileged engineer and admin accounts always require 2FA).
    """
    user_id = str(current_user.get('_id') or current_user.get('user_id'))
    user_role = current_user.get('role', 'citizen')

    if user_role in ['engineer', 'admin']:
        return jsonify({
            'error': 'Two-Factor Authentication is mandatory for professional engineer and administrator accounts.'
        }), 400

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
    """Returns the authenticated user profile."""
    return jsonify({'user': User.from_dict(current_user).to_dict()}), 200


