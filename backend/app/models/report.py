from datetime import datetime

class InfrastructureReport:
    """
    InfrastructureReport entity mapping to Figure 4.3 Class Diagram and Figure 4.5 Database Schema.
    Tracks citizen/inspector defect submission tickets through verification and resolution.
    """
    STATUS_PENDING = 'Pending'
    STATUS_UNDER_REVIEW = 'Under Review'
    STATUS_VERIFIED = 'Verified'
    STATUS_SCHEDULED = 'Scheduled'
    STATUS_RESOLVED = 'Resolved'
    STATUS_REJECTED = 'Rejected'

    def __init__(self, user_id, asset_id, description, status=STATUS_PENDING, report_id=None, date_submitted=None, metadata=None):
        self.report_id = str(report_id) if report_id else None
        self.user_id = str(user_id)
        self.asset_id = str(asset_id) if asset_id else None
        self.description = description
        self.status = status
        self.date_submitted = date_submitted or datetime.utcnow().isoformat()
        self.metadata = metadata or {}

    def update_status(self, new_status):
        """Updates the status of the infrastructure report."""
        self.status = new_status

    def to_dict(self):
        return {
            'report_id': self.report_id,
            'user_id': self.user_id,
            'asset_id': self.asset_id,
            'description': self.description,
            'status': self.status,
            'date_submitted': self.date_submitted,
            'metadata': self.metadata
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
            status=data.get('status', cls.STATUS_PENDING),
            date_submitted=data.get('date_submitted'),
            metadata=data.get('metadata', {})
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
