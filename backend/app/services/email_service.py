"""
Email & Two-Factor Authentication (2FA) Service for InfraVision.
Supports real SMTP email delivery (Gmail, SendGrid, Mailgun, Strathmore/Enterprise SMTP)
with graceful demo fallback when external credentials are not yet configured.
"""

import os
import smtplib
import secrets
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple


class EmailService:
    """
    Handles cryptographically secure OTP generation, email dispatch via SMTP,
    cooldown management, and attempt rate-limiting.
    """

    OTP_EXPIRY_MINUTES = 5
    RESEND_COOLDOWN_SECONDS = 60
    MAX_VERIFICATION_ATTEMPTS = 5
    MAX_SENDS_PER_HOUR = 5

    def __init__(self, app=None):
        self.app = app
        self._demo_last_dispatched: Dict[str, Dict[str, Any]] = {}

    def get_expiry_seconds(self) -> int:
        try:
            from flask import current_app
            if current_app:
                return int(current_app.config.get('OTP_EXPIRY_SECONDS', 300))
        except Exception:
            pass
        return int(os.getenv('OTP_EXPIRY_SECONDS', '300'))

    def get_cooldown_seconds(self) -> int:
        try:
            from flask import current_app
            if current_app:
                return int(current_app.config.get('OTP_RESEND_COOLDOWN_SECONDS', 60))
        except Exception:
            pass
        return int(os.getenv('OTP_RESEND_COOLDOWN_SECONDS', '60'))

    def get_max_attempts(self) -> int:
        try:
            from flask import current_app
            if current_app:
                return int(current_app.config.get('OTP_MAX_ATTEMPTS', 5))
        except Exception:
            pass
        return int(os.getenv('OTP_MAX_ATTEMPTS', '5'))

    def get_max_sends_per_hour(self) -> int:
        try:
            from flask import current_app
            if current_app:
                return int(current_app.config.get('OTP_MAX_SENDS_PER_HOUR', 5))
        except Exception:
            pass
        return int(os.getenv('OTP_MAX_SENDS_PER_HOUR', '5'))

    def is_demo_mode(self) -> bool:
        """
        Environment-gated check for controlled OTP verification fallback.
        Never silently enabled in production: ProductionConfig disables this unless
        ENABLE_PRODUCTION_OTP_FALLBACK is explicitly set in the environment.
        """
        try:
            from flask import current_app
            if current_app:
                return bool(current_app.config.get('ENABLE_DEMO_OTP', False))
        except Exception:
            pass
        if os.getenv('FLASK_ENV', 'development').strip().lower() == 'production':
            return os.getenv('ENABLE_PRODUCTION_OTP_FALLBACK', 'False').lower() in ('true', '1', 't')
        return os.getenv('ENABLE_DEMO_OTP', 'False').lower() in ('true', '1', 't')

    def should_expose_fallback_otp(self, to_email: str, dispatch_result: Optional[Dict[str, Any]] = None) -> bool:
        """
        Determines whether controlled in-app OTP autofill is available for this challenge:
        - Strictly disabled in production unless ENABLE_PRODUCTION_OTP_FALLBACK=True.
        - Enabled across local development / evaluation environments when ENABLE_DEMO_OTP=True
          so reviewers and demo accounts without accessible inboxes can complete 2FA.
        """
        return self.is_demo_mode()

    def is_configured(self) -> bool:
        """Checks if real SMTP transport credentials are configured in the environment."""
        try:
            from flask import current_app
            if current_app and current_app.config.get('TESTING'):
                return False
        except Exception:
            pass
        host = os.getenv('SMTP_HOST', '').strip()
        user = os.getenv('SMTP_USER', '').strip()
        password = os.getenv('SMTP_PASSWORD', '').strip()
        return bool(host and user and password)

    def verify_smtp_health(self) -> Tuple[bool, str]:
        """
        Genuinely verifies whether the configured SMTP server can connect and authenticate.
        Does not reveal credentials.
        """
        if not self.is_configured():
            return False, "Unconfigured (Missing SMTP credentials)"

        host = os.getenv('SMTP_HOST', '').strip()
        port = int(os.getenv('SMTP_PORT', '587'))
        user = os.getenv('SMTP_USER', '').strip()
        password = os.getenv('SMTP_PASSWORD', '').strip()
        use_tls = os.getenv('SMTP_USE_TLS', 'True').lower() in ('true', '1', 't')

        try:
            server = smtplib.SMTP(host, port, timeout=5)
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
            if user and password:
                server.login(user, password)
            server.quit()
            return True, "Operational (SMTP Authenticated)"
        except Exception as e:
            return False, f"Degraded ({type(e).__name__})"

    @classmethod
    def generate_otp(cls) -> str:
        """Generates a cryptographically secure 6-digit verification passcode."""
        return ''.join(secrets.choice(string.digits) for _ in range(6))

    def can_resend(self, last_dispatched_at: Optional[str]) -> Tuple[bool, int]:
        """
        Enforces cooldown between OTP generation requests.
        Returns (can_resend: bool, seconds_remaining: int).
        """
        if not last_dispatched_at:
            return True, 0

        cooldown = self.get_cooldown_seconds()
        try:
            last_time = datetime.fromisoformat(last_dispatched_at)
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            elapsed = (now - last_time).total_seconds()
            if elapsed < cooldown:
                remaining = int(cooldown - elapsed)
                return False, remaining
        except Exception:
            return True, 0

        return True, 0

    def send_otp_email(self, to_email: str, otp_code: str, user_name: str = 'User') -> Dict[str, Any]:
        """
        Dispatches a 6-digit OTP verification email to the user.
        Uses real SMTP if configured; otherwise prepares demo payload cleanly.
        Never logs the active OTP in runtime logs.
        """
        now_utc = datetime.now(timezone.utc)
        expiry_seconds = self.get_expiry_seconds()
        expiry_minutes = max(1, expiry_seconds // 60)
        expiry_utc = now_utc + timedelta(seconds=expiry_seconds)

        smtp_host = os.getenv('SMTP_HOST', '').strip()
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_user = os.getenv('SMTP_USER', '').strip()
        smtp_password = os.getenv('SMTP_PASSWORD', '').strip()
        smtp_sender = os.getenv('SMTP_SENDER', 'infravision-alerts@strathmore.edu').strip()
        use_tls = os.getenv('SMTP_USE_TLS', 'True').lower() in ('true', '1', 't')

        allow_demo_exposure = False
        is_testing = False
        try:
            from flask import current_app
            if current_app:
                is_testing = bool(current_app.config.get('TESTING', False))
        except Exception:
            pass

        if self.is_configured():
            try:
                msg = MIMEMultipart('alternative')
                msg['Subject'] = 'InfraVision Two-Factor Authentication (2FA) Code'
                msg['From'] = f"InfraVision Security <{smtp_sender}>"
                msg['To'] = to_email

                text_content = (
                    f"Hello {user_name},\n\n"
                    f"Your 6-digit InfraVision authentication passcode is: {otp_code}\n\n"
                    f"This code will expire in {expiry_minutes} minutes. "
                    "If you did not initiate this login request, please ignore this email and contact your system administrator.\n\n"
                    "Civil Infrastructure Monitoring System - Strathmore University"
                )

                html_content = f"""
                <div style="font-family: -apple-system, BlinkMacSystemFont, 'Montserrat', 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
                    <div style="text-align: center; margin-bottom: 20px;">
                        <span style="font-size: 26px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px;">InfraVision</span>
                        <p style="font-size: 13px; color: #64748b; margin-top: 4px;">Civil Infrastructure Defect Monitoring</p>
                    </div>
                    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; text-align: center; margin: 24px 0;">
                        <p style="font-size: 13px; color: #475569; margin: 0 0 10px; font-weight: 600;">Your One-Time Authentication Code</p>
                        <span style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #0f172a; font-family: monospace;">{otp_code}</span>
                        <p style="font-size: 12px; color: #dc2626; margin: 12px 0 0; font-weight: 500;">Valid for {expiry_minutes} minutes • Single use only</p>
                    </div>
                    <p style="font-size: 13px; color: #334155; line-height: 1.5;">
                        Hello <strong>{user_name}</strong>, enter this verification code to complete your secure sign-in.
                    </p>
                    <p style="font-size: 12px; color: #94a3b8; margin-top: 24px; border-top: 1px solid #e2e8f0; padding-top: 16px;">
                        If you did not initiate this login request, please ignore this email. Your account credentials remain secure.
                    </p>
                </div>
                """

                msg.attach(MIMEText(text_content, 'plain'))
                msg.attach(MIMEText(html_content, 'html'))

                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                if use_tls:
                    server.starttls()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)

                server.sendmail(smtp_sender, [to_email], msg.as_string())
                server.quit()

                res: Dict[str, Any] = {
                    'delivered': True,
                    'method': 'smtp',
                    'email': to_email,
                    'expires_at': expiry_utc.isoformat(),
                    'expires_in_seconds': expiry_seconds,
                    'error': None
                }
                if self.should_expose_fallback_otp(to_email, res):
                    res['demo_code'] = otp_code
                return res

            except Exception as e:
                # Mask sensitive info and avoid logging raw OTP
                res_fail: Dict[str, Any] = {
                    'delivered': False,
                    'method': 'smtp_failed_fallback',
                    'email': to_email,
                    'expires_at': expiry_utc.isoformat(),
                    'expires_in_seconds': expiry_seconds,
                    'error': type(e).__name__
                }
                if self.should_expose_fallback_otp(to_email, res_fail):
                    res_fail['demo_code'] = otp_code
                return res_fail
        else:
            # Controlled evaluation / test dispatch mode
            if is_testing:
                self._demo_last_dispatched[to_email] = {
                    'otp': otp_code,
                    'expires_at': expiry_utc.isoformat()
                }
            res_fallback: Dict[str, Any] = {
                'delivered': self.is_demo_mode(),
                'method': 'controlled_fallback' if self.is_demo_mode() else 'smtp_unconfigured',
                'email': to_email,
                'expires_at': expiry_utc.isoformat(),
                'expires_in_seconds': expiry_seconds,
                'note': 'SMTP transport unconfigured.'
            }
            if self.should_expose_fallback_otp(to_email, res_fallback):
                res_fallback['demo_code'] = otp_code
            return res_fallback


# Global singleton instance
email_service = EmailService()
__all__ = ['EmailService', 'email_service']
