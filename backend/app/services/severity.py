"""
Visual Severity Assessment Service for Civil Infrastructure Monitoring System.
Implements centralized prototype heuristic mapping detected defect area to visual severity.

CRITICAL NOTICE:
Severity calculated here is:
"Relative visual severity based on detected bounding-box area."

It is NOT:
- structural integrity certification
- structural failure probability
- engineering safety assessment
- model confidence

The trained SSD-MobileNetV2 neural network predicts defect class, confidence,
and bounding-box coordinates. It DOES NOT predict engineering severity.
Visual severity is a separate downstream computational heuristic.
"""

import os
from typing import Dict, Any, List, Union


class SeverityService:
    """
    Computes image-derived defect extent and maps bounding boxes
    to standardized relative visual severity categories.
    """

    SEVERITY_LOW = 'Low'
    SEVERITY_MODERATE = 'Moderate'
    SEVERITY_MEDIUM = 'Moderate'  # Alias for compatibility
    SEVERITY_CRITICAL = 'Critical'
    SEVERITY_HIGH = 'Critical'   # Alias for compatibility

    # Prototype visual severity thresholds based on bounding-box area relative to image
    DEFAULT_LOW_THRESHOLD = float(os.getenv('SEVERITY_LOW_THRESHOLD', '0.05'))       # < 5%
    DEFAULT_CRITICAL_THRESHOLD = float(os.getenv('SEVERITY_CRITICAL_THRESHOLD', '0.15')) # >= 15%

    @classmethod
    def calculate_box_area(cls, box: Union[List, tuple, dict], image_width: int = None, image_height: int = None) -> float:
        """
        Calculates relative area (ratio between 0.0 and 1.0) of a bounding box.

        Supports:
        1. Normalized box [ymin, xmin, ymax, xmax] (coordinates in [0.0, 1.0])
        2. Pixel box dict {'xmin': ..., 'ymin': ..., 'xmax': ..., 'ymax': ...} with image_width and image_height
        """
        if isinstance(box, dict):
            xmin = box.get('xmin', 0)
            ymin = box.get('ymin', 0)
            xmax = box.get('xmax', 0)
            ymax = box.get('ymax', 0)

            if image_width and image_height and image_width > 0 and image_height > 0:
                bbox_w = max(0, xmax - xmin)
                bbox_h = max(0, ymax - ymin)
                bbox_area = bbox_w * bbox_h
                image_area = image_width * image_height
                return round(float(bbox_area / image_area), 4)
            else:
                return 0.0

        if not box or len(box) < 4:
            return 0.0

        ymin, xmin, ymax, xmax = float(box[0]), float(box[1]), float(box[2]), float(box[3])
        height = max(0.0, min(1.0, ymax) - max(0.0, ymin))
        width = max(0.0, min(1.0, xmax) - max(0.0, xmin))
        return round(float(height * width), 4)

    # Backwards compatibility alias
    calculate_box_area_ratio = calculate_box_area

    @classmethod
    def calculate_severity_for_area(cls, relative_area: float, low_thresh: float = None, critical_thresh: float = None) -> str:
        """
        Maps a relative bounding-box area (0.0 to 1.0) to a visual severity category:
        - relative_area >= critical_thresh (default 0.15) -> 'Critical'
        - relative_area >= low_thresh (default 0.05)      -> 'Moderate'
        - relative_area < low_thresh                      -> 'Low'
        """
        low_t = low_thresh if low_thresh is not None else cls.DEFAULT_LOW_THRESHOLD
        crit_t = critical_thresh if critical_thresh is not None else cls.DEFAULT_CRITICAL_THRESHOLD

        if relative_area >= crit_t:
            return cls.SEVERITY_CRITICAL
        elif relative_area >= low_t:
            return cls.SEVERITY_MODERATE
        else:
            return cls.SEVERITY_LOW

    @classmethod
    def evaluate_relative_severity(cls, detections: List[Dict[str, Any]], low_thresh: float = None, critical_thresh: float = None) -> Dict[str, Any]:
        """
        Evaluates cumulative defect extent from detection bounding boxes.
        Returns mapped relative severity category and percentage coverage.
        """
        low_t = low_thresh if low_thresh is not None else cls.DEFAULT_LOW_THRESHOLD
        crit_t = critical_thresh if critical_thresh is not None else cls.DEFAULT_CRITICAL_THRESHOLD

        if not detections:
            return {
                'severity': cls.SEVERITY_LOW,
                'relative_severity': cls.SEVERITY_LOW,
                'relative_area': 0.0,
                'area_ratio': 0.0,
                'area_percentage': 0.0,
                'thresholds': {'low': low_t, 'critical': crit_t}
            }

        # Calculate cumulative bounding-box coverage
        total_area = sum(
            d.get('relative_area') if d.get('relative_area') is not None
            else d.get('area_ratio', 0.0)
            for d in detections
        )
        total_area = min(1.0, max(0.0, total_area))
        severity = cls.calculate_severity_for_area(total_area, low_thresh=low_t, critical_thresh=crit_t)

        return {
            'severity': severity,
            'relative_severity': severity,
            'relative_area': round(total_area, 4),
            'area_ratio': round(total_area, 4),
            'area_percentage': round(total_area * 100.0, 2),
            'thresholds': {'low': low_t, 'critical': crit_t}
        }


# Global singleton service
severity_service = SeverityService()
__all__ = ['SeverityService', 'severity_service']
