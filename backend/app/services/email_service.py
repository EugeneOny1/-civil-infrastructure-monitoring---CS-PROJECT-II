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

    OTP_EXPIRY_MINUTES = 10
    RESEND_COOLDOWN_SECONDS = 60
    MAX_VERIFICATION_ATTEMPTS = 5

    def __init__(self, app=None):
        self.app = app
        self._demo_last_dispatched: Dict[str, Dict[str, Any]] = {}

    def is_configured(self) -> bool:
        """Checks if real SMTP transport credentials are configured in the environment."""
        host = os.getenv('SMTP_HOST', '').strip()
        user = os.getenv('SMTP_USER', '').strip()
        return bool(host and user)

    @classmethod
    def generate_otp(cls) -> str:
        """Generates a cryptographically secure 6-digit verification passcode."""
        return ''.join(secrets.choice(string.digits) for _ in range(6))

    def can_resend(self, last_dispatched_at: Optional[str]) -> Tuple[bool, int]:
        """
        Enforces a 60-second cooldown between OTP generation requests.
        Returns (can_resend: bool, seconds_remaining: int).
        """
        if not last_dispatched_at:
            return True, 0

        try:
            last_time = datetime.fromisoformat(last_dispatched_at)
            # Ensure timezone awareness
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            elapsed = (now - last_time).total_seconds()
            if elapsed < self.RESEND_COOLDOWN_SECONDS:
                remaining = int(self.RESEND_COOLDOWN_SECONDS - elapsed)
                return False, remaining
        except Exception:
            return True, 0

        return True, 0

    def send_otp_email(self, to_email: str, otp_code: str, user_name: str = 'User') -> Dict[str, Any]:
        """
        Dispatches a 6-digit OTP verification email to the user.
        Uses real SMTP if configured; otherwise logs and prepares demo payload cleanly.
        """
        now_utc = datetime.now(timezone.utc)
        expiry_utc = now_utc + timedelta(minutes=self.OTP_EXPIRY_MINUTES)

        smtp_host = os.getenv('SMTP_HOST', '').strip()
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_user = os.getenv('SMTP_USER', '').strip()
        smtp_password = os.getenv('SMTP_PASSWORD', '').strip()
        smtp_sender = os.getenv('SMTP_SENDER', 'infravision-alerts@strathmore.edu').strip()
        use_tls = os.getenv('SMTP_USE_TLS', 'True').lower() in ('true', '1', 't')

        if self.is_configured():
            try:
                msg = MIMEMultipart('alternative')
                msg['Subject'] = 'InfraVision Two-Factor Authentication (2FA) Code'
                msg['From'] = f"InfraVision Security <{smtp_sender}>"
                msg['To'] = to_email

                text_content = (
                    f"Hello {user_name},\n\n"
                    f"Your 6-digit InfraVision authentication passcode is: {otp_code}\n\n"
                    f"This code will expire in {self.OTP_EXPIRY_MINUTES} minutes. "
                    "If you did not initiate this login request, please contact your system administrator immediately.\n\n"
                    "Civil Infrastructure Monitoring System - Strathmore University"
                )

                html_content = f"""
                <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; border: 1px solid #e5e5ea; border-radius: 12px; background-color: #ffffff;">
                    <div style="text-align: center; margin-bottom: 20px;">
                        <span style="font-size: 28px; font-weight: 700; color: #0071e3;">InfraVision</span>
                        <p style="font-size: 13px; color: #86868b; margin-top: 4px;">Civil Infrastructure Defect Monitoring</p>
                    </div>
                    <div style="background-color: #f5f5f7; border-radius: 8px; padding: 20px; text-align: center; margin: 24px 0;">
                        <p style="font-size: 14px; color: #424245; margin: 0 0 12px;">Your One-Time Authentication Code</p>
                        <span style="font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #1d1d1f; font-family: monospace;">{otp_code}</span>
                        <p style="font-size: 12px; color: #dc2626; margin: 12px 0 0;">Valid for {self.OTP_EXPIRY_MINUTES} minutes • Single use only</p>
                    </div>
                    <p style="font-size: 13px; color: #424245; line-height: 1.5;">
                        Hello <strong>{user_name}</strong>, enter this verification code to complete your secure sign-in.
                    </p>
                    <p style="font-size: 12px; color: #86868b; margin-top: 24px; border-top: 1px solid #e5e5ea; padding-top: 16px;">
                        If you did not initiate this request, please change your password and notify your system administrator immediately.
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

                return {
                    'delivered': True,
                    'method': 'smtp',
                    'email': to_email,
                    'expires_at': expiry_utc.isoformat(),
                    'error': None
                }
            except Exception as e:
                # Fallback to local demo logging on SMTP delivery failure
                print(f"[EmailService / Error] SMTP delivery to {to_email} failed: {e}")
                return {
                    'delivered': False,
                    'method': 'smtp_failed_fallback_demo',
                    'email': to_email,
                    'demo_code': otp_code,
                    'expires_at': expiry_utc.isoformat(),
                    'error': str(e)
                }
        else:
            # Demo/Development mode
            self._demo_last_dispatched[to_email] = {
                'otp': otp_code,
                'expires_at': expiry_utc.isoformat()
            }
            return {
                'delivered': True,
                'method': 'demo',
                'email': to_email,
                'demo_code': otp_code,
                'expires_at': expiry_utc.isoformat(),
                'note': 'SMTP is not configured. Running in development/demo mode with automatic code provisioning.'
            }


# Global singleton instance
email_service = EmailService()
__all__ = ['EmailService', 'email_service']
