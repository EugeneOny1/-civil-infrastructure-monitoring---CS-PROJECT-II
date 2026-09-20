"""
Forwarding shim for relative severity service.
Consolidated into backend.app.services.inference.
"""
from .inference import InferenceService

class SeverityService:
    @staticmethod
    def calculate_box_area_ratio(box):
        return InferenceService.calculate_box_area_ratio(box)

    @classmethod
    def assess_severity(cls, detections, low_thresh=0.05, critical_thresh=0.15):
        res = InferenceService.evaluate_relative_severity(detections, low_thresh, critical_thresh)
        return {
            'relative_severity': res['relative_severity'],
            'area_ratio': res['area_ratio'],
            'area_percentage': res['area_percentage']
        }

__all__ = ['SeverityService']
