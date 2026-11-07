from datetime import datetime

class InfrastructureReport:
    """
    InfrastructureReport entity mapping to Figure 4.3 Class Diagram and Figure 4.5 Database Schema.
    Tracks citizen/inspector defect submission tickets through verification and resolution.
    """
    # Canonical report lifecycle statuses (Received -> Verified -> Under Review -> Resolved)
    STATUS_RECEIVED = 'Received'
    STATUS_VERIFIED = 'Verified'
    STATUS_UNDER_REVIEW = 'Under Review'
    STATUS_RESOLVED = 'Resolved'

    CANONICAL_LIFECYCLE = [
        STATUS_RECEIVED,
        STATUS_VERIFIED,
        STATUS_UNDER_REVIEW,
        STATUS_RESOLVED
    ]

    # Legacy status compatibility aliases
    STATUS_PENDING = STATUS_RECEIVED
    STATUS_FLAGGED = STATUS_RECEIVED
    STATUS_SCHEDULED = STATUS_VERIFIED
    STATUS_REJECTED = 'Rejected'

    # Permitted forward lifecycle transitions
    VALID_TRANSITIONS = {
        STATUS_RECEIVED: [STATUS_VERIFIED],
        STATUS_VERIFIED: [STATUS_UNDER_REVIEW],
        STATUS_UNDER_REVIEW: [STATUS_RESOLVED],
        STATUS_RESOLVED: []
    }

    @classmethod
    def normalize_lifecycle_status(cls, raw_status: str) -> str:
        """
        Safely maps historical or alternate status strings to the canonical report lifecycle:
        Received -> Under Review -> Verified -> Resolved.
        """
        if not raw_status:
            return cls.STATUS_RECEIVED

        s = str(raw_status).strip()
        if s in cls.CANONICAL_LIFECYCLE:
            return s

        s_lower = s.lower()
        if s_lower in ('submitted', 'pending', 'flagged for review', 'flagged', 'received'):
            return cls.STATUS_RECEIVED
        elif s_lower in ('under review', 'in review', 'reviewing', 'under_review'):
            return cls.STATUS_UNDER_REVIEW
        elif s_lower in ('verified', 'confirmed', 'validated', 'scheduled'):
            return cls.STATUS_VERIFIED
        elif s_lower in ('resolved', 'closed', 'fixed', 'completed'):
            return cls.STATUS_RESOLVED

        return cls.STATUS_RECEIVED

    canonical_status = normalize_lifecycle_status

    @classmethod
    def can_transition(cls, current_status: str, target_status: str) -> bool:
        """Validates if transition between report statuses is permitted."""
        norm_curr = cls.normalize_lifecycle_status(current_status)
        norm_target = cls.normalize_lifecycle_status(target_status)
        if norm_curr == norm_target:
            return True
        return norm_target in cls.VALID_TRANSITIONS.get(norm_curr, [])

    def __init__(self, user_id, asset_id, description, status=STATUS_RECEIVED, report_id=None, date_submitted=None, metadata=None, latitude=None, longitude=None):
        self.report_id = str(report_id) if report_id else None
        self.user_id = str(user_id)
        self.asset_id = str(asset_id) if asset_id else None
        self.description = description
        self.status = self.normalize_lifecycle_status(status)
        self.date_submitted = date_submitted or datetime.utcnow().isoformat()
        self.metadata = metadata or {}
        self.latitude = latitude if latitude is not None else self.metadata.get('latitude')
        self.longitude = longitude if longitude is not None else self.metadata.get('longitude')
        if self.latitude is not None:
            self.metadata['latitude'] = float(self.latitude)
        if self.longitude is not None:
            self.metadata['longitude'] = float(self.longitude)

    def update_status(self, new_status):
        """Updates the status of the infrastructure report to a canonical status."""
        self.status = self.normalize_lifecycle_status(new_status)

    def to_dict(self):
        return {
            'report_id': self.report_id,
            'user_id': self.user_id,
            'asset_id': self.asset_id,
            'description': self.description,
            'status': self.status,
            'date_submitted': self.date_submitted,
            'metadata': self.metadata,
            'latitude': self.latitude,
            'longitude': self.longitude
        }

    @classmethod
    def from_dict(cls, data):
        if not data:
            return None
        return cls(
            report_id=data.get('_id') or data.get('report_id'),
            user_id=data.get('user_id'),
            asset_id=data.get('asset_id'),
            description=data.get('description', ''),
            status=cls.normalize_lifecycle_status(data.get('status', cls.STATUS_RECEIVED)),
            date_submitted=data.get('date_submitted'),
            metadata=data.get('metadata', {}),
            latitude=data.get('latitude') or data.get('metadata', {}).get('latitude'),
            longitude=data.get('longitude') or data.get('metadata', {}).get('longitude')
        )


class SubmittedImage:
    """
    SubmittedImage entity mapping to Figure 4.3 Class Diagram and Figure 4.5 Database Schema.
    Tracks photographic evidence uploaded for defect inspection.
    """
    def __init__(self, report_id, image_path, original_filename='', file_size=0, image_id=None, upload_date=None, dimensions=None):
        self.image_id = str(image_id) if image_id else None
        self.report_id = str(report_id)
        self.image_path = image_path
        self.original_filename = original_filename
        self.file_size = file_size
        self.upload_date = upload_date or datetime.utcnow().isoformat()
        self.dimensions = dimensions or {'width': 0, 'height': 0}

    def to_dict(self):
        return {
            'image_id': self.image_id,
            'report_id': self.report_id,
            'image_path': self.image_path,
            'original_filename': self.original_filename,
            'file_size': self.file_size,
            'upload_date': self.upload_date,
            'dimensions': self.dimensions
        }

    @classmethod
    def from_dict(cls, data):
        if not data:
            return None
        return cls(
            image_id=data.get('_id') or data.get('image_id'),
            report_id=data.get('report_id'),
            image_path=data.get('image_path', ''),
            original_filename=data.get('original_filename', ''),
            file_size=data.get('file_size', 0),
            upload_date=data.get('upload_date'),
            dimensions=data.get('dimensions', {'width': 0, 'height': 0})
        )
