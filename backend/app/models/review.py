from datetime import datetime

class ProfessionalReview:
    """
    ProfessionalReview entity mapping to Figure 4.3 Class Diagram and Figure 4.5 Database Schema.
    Captures human-in-the-loop engineering validation and certification sign-off.
    """
    DECISION_CONFIRMED = 'Confirmed'
    DECISION_OVERRIDDEN = 'Overridden'

    def __init__(self, assessment_id, reviewer_id, decision=DECISION_CONFIRMED, comments='',
                 override_details=None, review_id=None, review_date=None):
        self.review_id = str(review_id) if review_id else None
        self.assessment_id = str(assessment_id)
        self.reviewer_id = str(reviewer_id)
        self.decision = decision  # 'Confirmed' or 'Overridden'
        self.comments = comments  # Engineer Certification Notes / sign-off instructions
        self.override_details = override_details or {}  # e.g., {'override_class': ..., 'override_severity': ...}
        self.review_date = review_date or datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            'review_id': self.review_id,
            'assessment_id': self.assessment_id,
            'reviewer_id': self.reviewer_id,
            'decision': self.decision,
            'comments': self.comments,
            'override_details': self.override_details,
            'review_date': self.review_date
        }

    @classmethod
    def from_dict(cls, data):
        if not data:
            return None
        return cls(
            review_id=data.get('_id') or data.get('review_id'),
            assessment_id=data.get('assessment_id'),
            reviewer_id=data.get('reviewer_id'),
            decision=data.get('decision', cls.DECISION_CONFIRMED),
            comments=data.get('comments', ''),
            override_details=data.get('override_details', {}),
            review_date=data.get('review_date')
        )
