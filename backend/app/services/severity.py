"""
Severity Assessment Service for Civil Infrastructure Monitoring System.
Implements FR-04: Relative Severity Assessment based on image-derived defect extent.

Defect extent is measured computationally as the proportion of the image surface area
occupied by the bounding box envelope of detected structural anomalies:
- Low Severity: < 5% image area ratio (< 0.05)
- Medium Severity: 5% - 15% image area ratio (0.05 - 0.15)
- Critical Severity: > 15% image area ratio (> 0.15)
"""

class SeverityService:
    """
    Computes image-derived defect extent and maps bounding boxes
    to standardized engineering condition severity categories.
    """
    SEVERITY_LOW = 'Low'
    SEVERITY_MEDIUM = 'Medium'
    SEVERITY_CRITICAL = 'Critical'

    DEFAULT_LOW_THRESHOLD = 0.05      # 5% of total frame area
    DEFAULT_CRITICAL_THRESHOLD = 0.15 # 15% of total frame area

    @staticmethod
    def calculate_box_area_ratio(box):
        """
        Calculates the normalized area of a bounding box [ymin, xmin, ymax, xmax].
        Coordinates are normalized to [0.0, 1.0].
        """
        if not box or len(box) < 4:
            return 0.0
        ymin, xmin, ymax, xmax = box[0], box[1], box[2], box[3]
        height = max(0.0, min(1.0, ymax) - max(0.0, ymin))
        width = max(0.0, min(1.0, xmax) - max(0.0, xmin))
        return round(float(height * width), 4)

    @classmethod
    def evaluate_relative_severity(cls, detections, low_thresh=None, critical_thresh=None):
        """
        Evaluates cumulative and primary defect extent from SSD bounding boxes.
        Returns mapped relative severity category and percentage coverage.
        """
        low_t = low_thresh if low_thresh is not None else cls.DEFAULT_LOW_THRESHOLD
        crit_t = critical_thresh if critical_thresh is not None else cls.DEFAULT_CRITICAL_THRESHOLD

        if not detections:
            return {
                'relative_severity': cls.SEVERITY_LOW,
                'area_ratio': 0.0,
                'area_percentage': 0.0,
                'thresholds': {'low': low_t, 'critical': crit_t}
            }

        # Calculate cumulative bounding box coverage
        total_area = sum(d.get('area_ratio', 0.0) for d in detections)
        total_area = min(1.0, total_area)

        # Determine mapped severity category
        if total_area > crit_t:
            severity = cls.SEVERITY_CRITICAL
        elif total_area >= low_t:
            severity = cls.SEVERITY_MEDIUM
        else:
            severity = cls.SEVERITY_LOW

        return {
            'relative_severity': severity,
            'area_ratio': round(total_area, 4),
            'area_percentage': round(total_area * 100.0, 1),
            'thresholds': {'low': low_t, 'critical': crit_t}
        }

# Global singleton
severity_service = SeverityService()
__all__ = ['SeverityService', 'severity_service']
