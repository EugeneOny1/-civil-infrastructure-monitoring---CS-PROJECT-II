from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class User:
    """
    User entity mapping to Figure 4.3 Class Diagram and Figure 4.5 Database Schema.
    Roles: 'citizen', 'engineer', 'admin'
    Verification status: 'pending', 'verified', 'rejected'
    """
    def __init__(self, name, email, password=None, password_hash=None, role='citizen', verification_status=None, user_id=None, created_at=None, organization=None, professional_reg_no=None, phone=None, two_factor_enabled=False, rejection_reason=None, rejection_notes=None, rejected_at=None, verified_at=None):
        self.user_id = str(user_id) if user_id else None
        self.name = name
        self.email = email.lower().strip() if email else ''
        if password_hash:
            self.password_hash = password_hash
        elif password:
            self.password_hash = generate_password_hash(password)
        else:
            self.password_hash = ''
        
        self.role = role  # 'citizen', 'engineer', 'admin'
        self.organization = organization or ''
        self.professional_reg_no = professional_reg_no or ''
        self.phone = phone or ''
        self.two_factor_enabled = bool(two_factor_enabled)
        
        # Engineers require admin verification per FR-01 / FR-10; citizens are automatically verified
        if verification_status:
            self.verification_status = verification_status
        else:
            self.verification_status = 'verified' if role == 'citizen' else 'pending'
            
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.rejection_reason = rejection_reason
        self.rejection_notes = rejection_notes
        self.rejected_at = rejected_at
        self.verified_at = verified_at

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self, include_sensitive=False):
        data = {
            'user_id': self.user_id,
            'name': self.name,
            'email': self.email,
            'role': self.role,
            'organization': self.organization,
            'professional_reg_no': self.professional_reg_no,
            'phone': self.phone,
            'two_factor_enabled': self.two_factor_enabled,
            'verification_status': self.verification_status,
            'created_at': self.created_at
        }
        if self.verification_status == 'rejected':
            data['rejection_reason'] = self.rejection_reason
            data['rejection_notes'] = self.rejection_notes
            data['rejected_at'] = self.rejected_at
        elif self.verification_status == 'verified':
            data['verified_at'] = self.verified_at
        if include_sensitive:
            data['password_hash'] = self.password_hash
        return data

    @classmethod
    def from_dict(cls, data):
        if not data:
            return None
        return cls(
            user_id=data.get('_id') or data.get('user_id'),
            name=data.get('name', ''),
            email=data.get('email', ''),
            password_hash=data.get('password_hash', ''),
            role=data.get('role', 'citizen'),
            organization=data.get('organization', ''),
            professional_reg_no=data.get('professional_reg_no', ''),
            phone=data.get('phone', ''),
            two_factor_enabled=data.get('two_factor_enabled', False),
            verification_status=data.get('verification_status', 'verified'),
            created_at=data.get('created_at'),
            rejection_reason=data.get('rejection_reason'),
            rejection_notes=data.get('rejection_notes'),
            rejected_at=data.get('rejected_at'),
            verified_at=data.get('verified_at')
        )


class Administrator(User):
    """
    Administrator entity per Figure 4.3 Class Diagram.
    Inherits from User with administrative authority to verify professional accounts.
    """
    def __init__(self, name, email, password=None, password_hash=None, user_id=None, created_at=None):
        super().__init__(
            name=name,
            email=email,
            password=password,
            password_hash=password_hash,
            role='admin',
            verification_status='verified',
            user_id=user_id,
            created_at=created_at
        )
