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
        max_attempts = email_service.get_max_attempts()

        # Check rate limiting / attempt lockout
        if attempts >= max_attempts:
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
                    return jsonify({'error': 'Verification code has expired. Please sign in again.'}), 401
            except Exception:
                pass

        # Verify against active cryptographically generated code only (no hardcoded test codes)
        if not stored_otp or otp_code != stored_otp:
            db_service.update_one('users', {'_id': user_data['_id']}, {
                'two_factor_attempts': attempts + 1
            })
            remaining = max(0, max_attempts - (attempts + 1))
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
        expiry_seconds = email_service.get_expiry_seconds()
        expiry_utc = now_utc + timedelta(seconds=expiry_seconds)

        # Dispatch real email via SMTP service
        dispatch_result = email_service.send_otp_email(email, otp, user.name)

        db_service.update_one('users', {'_id': user_data['_id']}, {
            'two_factor_otp': otp,
            'two_factor_exp': expiry_utc.isoformat(),
            'two_factor_attempts': 0,
            'otp_dispatched_at': now_utc.isoformat()
        })

        resp_payload = {
            'require_2fa': True,
            'user_id': str(user_data['_id']),
            'email': email,
            'role': user.role,
            'smtp_delivered': dispatch_result.get('delivered', False),
            'expires_at': expiry_utc.isoformat(),
            'expires_in_seconds': expiry_seconds,
            'cooldown_seconds': email_service.get_cooldown_seconds(),
            'enable_demo_otp': email_service.is_demo_mode(),
            'message': f"A 6-digit verification code has been dispatched to {email}."
        }

        # Include demo OTP only when ENABLE_DEMO_OTP=true
        if email_service.is_demo_mode():
            resp_payload['demo_otp'] = otp

        return jsonify(resp_payload), 200

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
    Enforces single-use invalidation, expiration check, and attempt limits.
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

    max_attempts = email_service.get_max_attempts()
    attempts = int(user_data.get('two_factor_attempts', 0))
    if attempts >= max_attempts:
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
    if not stored_otp or otp_code != stored_otp:
        db_service.update_one('users', {'_id': user_data['_id']}, {
            'two_factor_attempts': attempts + 1
        })
        remaining = max(0, max_attempts - (attempts + 1))
        return jsonify({
            'error': f'Invalid 2FA security code. {remaining} attempt(s) remaining.'
        }), 401

    # Invalidate OTP immediately after successful verification (single-use)
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
    Resends a fresh 2FA OTP code, enforcing cooldown and hourly rate limits.
    Immediately invalidates any previous OTP code.
    """
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'error': 'Email address is required.'}), 400

    user_data = db_service.find_one('users', {'email': email})
    if not user_data:
        return jsonify({'error': 'Account not found.'}), 404

    # Enforce cooldown period
    can_send, remaining = email_service.can_resend(user_data.get('otp_dispatched_at'))
    if not can_send:
        return jsonify({
            'error': f'Please wait {remaining} seconds before requesting a new verification code.'
        }), 429

    now_utc = datetime.now(timezone.utc)
    # Enforce hourly send rate limits
    send_history = user_data.get('otp_send_history', [])
    one_hour_ago = (now_utc - timedelta(hours=1)).isoformat()
    recent_sends = [ts for ts in send_history if ts > one_hour_ago]
    max_per_hour = email_service.get_max_sends_per_hour()
    if len(recent_sends) >= max_per_hour:
        return jsonify({
            'error': f'Hourly limit of {max_per_hour} verification codes reached. Please try again later.'
        }), 429

    # Generate new OTP (invalidating the previous one)
    otp = email_service.generate_otp()
    expiry_seconds = email_service.get_expiry_seconds()
    expiry_utc = now_utc + timedelta(seconds=expiry_seconds)

    dispatch_result = email_service.send_otp_email(email, otp, user_data.get('name', 'User'))

    recent_sends.append(now_utc.isoformat())
    db_service.update_one('users', {'_id': user_data['_id']}, {
        'two_factor_otp': otp,
        'two_factor_exp': expiry_utc.isoformat(),
        'two_factor_attempts': 0,
        'otp_dispatched_at': now_utc.isoformat(),
        'otp_send_history': recent_sends
    })

    res_payload = {
        'message': f'A fresh verification code has been dispatched to {email}.',
        'expires_at': expiry_utc.isoformat(),
        'expires_in_seconds': expiry_seconds,
        'cooldown_seconds': email_service.get_cooldown_seconds(),
        'enable_demo_otp': email_service.is_demo_mode(),
        'smtp_delivered': dispatch_result.get('delivered', False)
    }

    if email_service.is_demo_mode():
        res_payload['demo_otp'] = otp

    return jsonify(res_payload), 200

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
        is_demo_token = credential in ('demo_google_gis_credential_token', 'demo_token') or str(credential).startswith('demo_')
        if is_demo_token:
            if test_mode:
                # Permitted ONLY when running automated test suite with TESTING=True
                email = data.get('email', 'citizen.demo@strathmore.edu').strip().lower()
                name = data.get('name', 'Demo Google Citizen')
                google_id = data.get('google_id', 'demo_google_sub_12345')
            else:
                return jsonify({'error': 'Demo Google tokens are disabled. A real verified Google Identity Services token is required.'}), 401
        else:
            try:
                import requests
                resp = requests.get('https://oauth2.googleapis.com/tokeninfo', params={'id_token': credential}, timeout=5)
                if resp.status_code == 200:
                    token_info = resp.json()
                    expected_client_id = current_app.config.get('GOOGLE_CLIENT_ID', '').strip()
                    token_aud = token_info.get('aud', '')
                    
                    # Verify audience matches GOOGLE_CLIENT_ID from backend configuration
                    if expected_client_id and token_aud and token_aud != expected_client_id:
                        return jsonify({'error': 'Google token audience mismatch with application client ID.'}), 401
                    
                    # Verify token issuer
                    token_iss = token_info.get('iss', '')
                    if token_iss not in ('accounts.google.com', 'https://accounts.google.com'):
                        return jsonify({'error': 'Invalid Google token issuer.'}), 401

                    # Verify expiration
                    now_ts = datetime.now(timezone.utc).timestamp()
                    exp_ts = float(token_info.get('exp', 0))
                    if exp_ts and exp_ts < now_ts:
                        return jsonify({'error': 'Google token has expired.'}), 401

                    # Check email verification status from Google
                    email_verified = token_info.get('email_verified')
                    if str(email_verified).lower() not in ('true', '1'):
                        return jsonify({'error': 'Google account email is not verified.'}), 401
                    
                    email = token_info.get('email', '').strip().lower()
                    name = token_info.get('name', '').strip() or 'Google User'
                    google_id = token_info.get('sub', '').strip()

                    # Live browser Google Sign-In succeeded: record operational state
                    db_service.update_one(
                        'system_state',
                        {'_id': 'google_identity_status'},
                        {
                            'operational': True,
                            'last_verified_at': datetime.now(timezone.utc).isoformat(),
                            'last_user_email': email
                        },
                        upsert=True
                    )
                else:
                    return jsonify({'error': 'Google authentication failed: Invalid or expired token.'}), 401
            except Exception as e:
                return jsonify({'error': f'Failed to verify Google credential: {str(e)}'}), 401
    elif test_mode and data.get('email'):
        # Controlled test mock payload
        email = data.get('email', '').strip().lower()
        name = data.get('name', '').strip() or 'Google User'
        google_id = data.get('google_id', '').strip() or data.get('sub', '').strip()
    else:
        return jsonify({'error': 'Google credential token is required.'}), 400

    now_iso = datetime.now(timezone.utc).isoformat()

    # Section 4: Check whether this Google identity is ALREADY linked to an InfraVision account
    # via Google's stable 'sub' claim identifier.
    existing_user = db_service.find_one('users', {'google_sub': google_id}) or db_service.find_one('users', {'google_id': google_id})

    if existing_user:
        # IF linked: Authenticate that existing InfraVision account
        db_service.update_one('users', {'_id': existing_user['_id']}, {
            'last_google_login': now_iso
        })
        user = User.from_dict(existing_user)
        user_data = existing_user
    else:
        # IF not linked: check if the VERIFIED Google email exactly matches an existing InfraVision account
        user_by_email = db_service.find_one('users', {'email': email})

        if user_by_email:
            # Safely link the Google identity to that account without overwriting existing role/profile
            db_service.update_one('users', {'_id': user_by_email['_id']}, {
                'google_id': google_id,
                'google_sub': google_id,
                'auth_provider': user_by_email.get('auth_provider') or 'google',
                'last_google_login': now_iso
            })
            # Preserve existing InfraVision display name, role, verification state, etc.
            user = User.from_dict(user_by_email)
            user_data = user_by_email
        else:
            # Otherwise create a new Citizen InfraVision account (defaults strictly to Citizen)
            new_user = User(
                name=name,
                email=email,
                password=None,
                password_hash=None,
                role='citizen',  # New Google users are STRICTLY Citizen
                verification_status='verified'
            )
            user_dict = new_user.to_dict(include_sensitive=True)
            user_dict['google_id'] = google_id
            user_dict['google_sub'] = google_id
            user_dict['auth_provider'] = 'google'
            user_dict['must_change_password'] = False
            user_dict['created_at'] = now_iso
            user_dict['last_google_login'] = now_iso
            inserted_id = db_service.insert('users', user_dict)
            new_user.user_id = str(inserted_id)
            user = new_user
            user_data = user_dict

    # Enforce mandatory 2FA for privileged accounts (engineer, admin) or if user enabled 2FA
    is_privileged = user.role in ['engineer', 'admin']
    has_2fa = is_privileged or user.two_factor_enabled

    if has_2fa:
        otp = email_service.generate_otp()
        expiry_seconds = email_service.get_expiry_seconds()
        now_utc = datetime.now(timezone.utc)
        expiry_utc = now_utc + timedelta(seconds=expiry_seconds)

        # Dispatch real OTP email (or demo fallback)
        dispatch_result = email_service.send_otp_email(user.email, otp, user.name)

        send_history = (existing_user.get('otp_send_history', []) if existing_user else [])
        send_history.append(now_utc.isoformat())

        target_user_id = existing_user['_id'] if existing_user else user.user_id
        db_service.update_one('users', {'_id': target_user_id}, {
            'two_factor_otp': otp,
            'two_factor_exp': expiry_utc.isoformat(),
            'two_factor_attempts': 0,
            'otp_dispatched_at': now_utc.isoformat(),
            'otp_send_history': send_history
        })

        res_payload = {
            'require_2fa': True,
            'email': user.email,
            'role': user.role,
            'message': f'Two-Factor Authentication required. Verification code dispatched to {user.email}.',
            'expires_in_seconds': expiry_seconds,
            'cooldown_seconds': email_service.get_cooldown_seconds(),
            'enable_demo_otp': email_service.is_demo_mode(),
            'smtp_delivered': dispatch_result.get('delivered', False)
        }
        if email_service.is_demo_mode():
            res_payload['demo_otp'] = otp
        return jsonify(res_payload), 200

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

@auth_bp.route('/profile', methods=['GET'])
@auth_bp.route('/me', methods=['GET'])
@login_required
def get_profile(current_user):
    """Returns the authenticated user profile with professional engineering and security details."""
    user_id = str(current_user.get('_id') or current_user.get('user_id'))
    user_record = db_service.find_one('users', {'_id': user_id}) or current_user

    role = user_record.get('role', 'citizen')
    has_weak_password = bool(user_record.get('must_change_password'))
    
    eng_details = None
    if role == 'engineer':
        eng_details = {
            'engineering_category': user_record.get('engineering_category', 'Graduate Engineer'),
            'professional_reg_no': user_record.get('professional_reg_no', 'N/A'),
            'verification_status': user_record.get('verification_status', 'pending'),
            'organization': user_record.get('organization', '')
        }

    user_dict = User.from_dict(user_record).to_dict()
    user_dict['phone'] = user_record.get('phone', '')

    return jsonify({
        'user': user_dict,
        'two_factor_enabled': bool(user_record.get('two_factor_enabled', False)),
        'has_weak_password': has_weak_password,
        'engineering_details': eng_details
    }), 200

@auth_bp.route('/profile', methods=['PUT'])
@login_required
def update_profile(current_user):
    """
    Updates editable personal user profile information with backend validation.
    Protects role assignment and verified professional engineering credentials.
    """
    user_id = str(current_user.get('_id') or current_user.get('user_id'))
    user_record = db_service.find_one('users', {'_id': user_id})
    if not user_record:
        return jsonify({'error': 'User account not found.'}), 404

    data = request.get_json() or {}

    # Security: Role can NEVER be self-assigned or edited
    if 'role' in data and data['role'] != user_record.get('role'):
        return jsonify({'error': 'Account role cannot be modified.'}), 400

    if 'is_admin' in data or ('role' in data and data['role'] == 'admin'):
        return jsonify({'error': 'Administrator privileges cannot be self-assigned.'}), 403

    updates = {}

    # Full name update
    if 'name' in data:
        name = str(data['name']).strip()
        if not name:
            return jsonify({'error': 'Full name cannot be empty.'}), 400
        updates['name'] = name

    # Phone number update
    if 'phone' in data:
        updates['phone'] = str(data['phone']).strip()

    # Organization update
    if 'organization' in data:
        updates['organization'] = str(data['organization']).strip()

    # Protected Engineer fields
    if user_record.get('role') == 'engineer':
        is_verified = user_record.get('verification_status') == 'verified'
        if is_verified:
            if 'professional_reg_no' in data and data['professional_reg_no'] != user_record.get('professional_reg_no'):
                return jsonify({'error': 'Verified EBK registration number is legally protected and cannot be modified.'}), 400
            if 'engineering_category' in data and data['engineering_category'] != user_record.get('engineering_category'):
                return jsonify({'error': 'Verified engineering category cannot be modified.'}), 400
        else:
            # Pending engineer updating registration details
            if 'engineering_category' in data or 'professional_reg_no' in data:
                cat = data.get('engineering_category', user_record.get('engineering_category'))
                reg = data.get('professional_reg_no', user_record.get('professional_reg_no'))
                valid, norm_reg, err = validate_ebk_registration(cat, reg)
                if not valid:
                    return jsonify({'error': err}), 400
                updates['engineering_category'] = cat
                updates['professional_reg_no'] = norm_reg

    if updates:
        updates['updated_at'] = datetime.now(timezone.utc).isoformat()
        db_service.update_one('users', {'_id': user_id}, updates)

    updated_user = db_service.find_one('users', {'_id': user_id})
    user_dict = User.from_dict(updated_user).to_dict()
    user_dict['phone'] = updated_user.get('phone', '')

    return jsonify({
        'message': 'Profile information updated successfully.',
        'user': user_dict
    }), 200

@auth_bp.route('/config', methods=['GET'])
def get_auth_config():
    """
    Returns public, non-secret client configuration for Google Identity Services and OTP UI.
    Never exposes secrets or credentials.
    """
    return jsonify({
        'google_client_id': current_app.config.get('GOOGLE_CLIENT_ID', ''),
        'enable_demo_otp': email_service.is_demo_mode(),
        'otp_expiry_seconds': email_service.get_expiry_seconds(),
        'otp_cooldown_seconds': email_service.get_cooldown_seconds()
    }), 200


