from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class User:
    """
    User entity mapping to Figure 4.3 Class Diagram and Figure 4.5 Database Schema.
    Roles: 'citizen', 'engineer', 'admin'
    Verification status: 'pending', 'verified', 'rejected'
    """
    def __init__(self, name, email, password=None, password_hash=None, role='citizen', verification_status=None, user_id=None, created_at=None):
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
        
        # Engineers require admin verification per FR-01 / FR-10; citizens are automatically verified
        if verification_status:
            self.verification_status = verification_status
        else:
            self.verification_status = 'verified' if role == 'citizen' else 'pending'
            
        self.created_at = created_at or datetime.utcnow().isoformat()

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self, include_sensitive=False):
        data = {
            'user_id': self.user_id,
            'name': self.name,
            'email': self.email,
            'role': self.role,
            'verification_status': self.verification_status,
            'created_at': self.created_at
        }
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
            verification_status=data.get('verification_status', 'verified'),
            created_at=data.get('created_at')
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
