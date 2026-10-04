"""
Validation Service for Civil Infrastructure Monitoring System.
Implements Backend Integrity Checks, Input Sanitization, and Domain Logic Validation.

Enforces rules for defect-infrastructure pairings:
- Road / Pavement: Crack, Pothole, Surface Deterioration
- Bridge / Viaduct: Crack, Surface Deterioration, Pothole
- Building / Retaining Wall: Crack, Surface Deterioration

Special Handling:
Unusual combinations (such as a 'Pothole' reported on a 'Building') are NOT hard-rejected
because edge cases can occur and AI models can make errors. Instead, unusual reports are
flagged with 'is_unusual = True' and assigned the status 'Flagged for Review', placing them
into the certified engineer's priority queue for human-in-the-loop validation.
"""

import re
from typing import Dict, Any, List, Tuple

class ValidationService:
    """
    Backend integrity validation service for citizen submissions and AI pre-assessments.
    """
    
    # Standard engineering defect taxonomies mapped to infrastructure asset categories
    ALLOWED_DEFECTS = {
        'road': {'crack', 'pothole', 'surface deterioration'},
        'road / pavement': {'crack', 'pothole', 'surface deterioration'},
        'pavement': {'crack', 'pothole', 'surface deterioration'},
        'bridge': {'crack', 'surface deterioration', 'pothole'},
        'bridge / viaduct': {'crack', 'surface deterioration', 'pothole'},
        'building': {'crack', 'surface deterioration'},
        'public building': {'crack', 'surface deterioration'},
        'public building / retaining wall': {'crack', 'surface deterioration'},
        'retaining wall': {'crack', 'surface deterioration'}
    }

    VALID_INFRASTRUCTURE_TYPES = [
        'Road / Pavement',
        'Bridge',
        'Bridge / Viaduct',
        'Building',
        'Public Building / Retaining Wall'
    ]

    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
    MAX_IMAGE_SIZE_BYTES = 16 * 1024 * 1024  # 16 MB

    @classmethod
    def normalize_key(cls, value: str) -> str:
        """Normalizes infrastructure or defect string for taxonomy matching."""
        if not value:
            return ''
        return value.strip().lower()

    @classmethod
    def validate_submission_inputs(cls, asset_type: str, location: str, description: str = '') -> Tuple[bool, List[str]]:
        """
        Validates form inputs before AI processing.
        Returns (is_valid, error_messages).
        """
        errors = []

        if not location or len(location.strip()) < 3:
            errors.append("Defect location is required and must contain at least 3 characters.")

        if not asset_type or not asset_type.strip():
            errors.append("Infrastructure asset type is required.")

        return (len(errors) == 0, errors)

    @classmethod
    def check_defect_compatibility(cls, asset_type: str, defect_class: str) -> Dict[str, Any]:
        """
        Evaluates whether a detected defect class is typical or unusual for the given infrastructure type.
        """
        norm_asset = cls.normalize_key(asset_type)
        norm_defect = cls.normalize_key(defect_class)

        # Lookup allowed defects for the given asset type
        allowed = cls.ALLOWED_DEFECTS.get(norm_asset)
        
        # Fallback partial matching if exact string isn't in dictionary keys
        if allowed is None:
            if 'road' in norm_asset or 'pave' in norm_asset:
                allowed = cls.ALLOWED_DEFECTS['road']
            elif 'bridge' in norm_asset or 'viaduct' in norm_asset:
                allowed = cls.ALLOWED_DEFECTS['bridge']
            elif 'build' in norm_asset or 'wall' in norm_asset:
                allowed = cls.ALLOWED_DEFECTS['building']
            else:
                allowed = {'crack', 'pothole', 'surface deterioration'}

        is_typical = norm_defect in allowed

        if is_typical:
            return {
                'is_unusual': False,
                'flag_type': 'STANDARD_COMBINATION',
                'flag_reason': None,
                'message': f"Defect '{defect_class}' is standard for infrastructure type '{asset_type}'."
            }
        else:
            return {
                'is_unusual': True,
                'flag_type': 'UNUSUAL_COMBINATION',
                'flag_reason': f"Unusual combination: '{defect_class}' defect detected on '{asset_type}' infrastructure.",
                'message': (
                    f"Notice: '{defect_class}' is atypical for '{asset_type}'. "
                    "The report has been retained and flagged for certified civil engineer review."
                )
            }

    @classmethod
    def evaluate_ai_anomalies(cls, confidence_score: float, area_percentage: float) -> List[Dict[str, str]]:
        """
        Checks for edge cases in AI pre-assessment such as low confidence or extreme defect extent.
        """
        anomalies = []

        if confidence_score is not None and confidence_score < 0.40:
            anomalies.append({
                'flag_type': 'LOW_CONFIDENCE',
                'flag_reason': f"Low AI detection confidence ({round(confidence_score * 100, 1)}%). Requires engineer verification."
            })

        if area_percentage is not None and area_percentage > 55.0:
            anomalies.append({
                'flag_type': 'EXTREME_EXTENT',
                'flag_reason': f"Defect extent exceeds 55% of image area ({area_percentage}%). Urgent engineer evaluation prioritized."
            })

        return anomalies

    @classmethod
    def validate_report(cls, asset_type: str, location: str, detection_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Performs holistic backend integrity validation combining input checks,
        defect-infrastructure compatibility, and AI confidence/extent criteria.
        """
        defect_class = detection_result.get('defect_class', 'Crack')
        confidence_score = float(detection_result.get('confidence_score', 0.85))
        area_percentage = float(detection_result.get('area_percentage', 10.0))
        relative_severity = detection_result.get('relative_severity', 'Medium')

        flags = []
        is_unusual = False

        # 1. Defect vs Infrastructure pairing check
        compat = cls.check_defect_compatibility(asset_type, defect_class)
        if compat['is_unusual']:
            is_unusual = True
            flags.append({
                'type': compat['flag_type'],
                'reason': compat['flag_reason'],
                'description': compat['message']
            })

        # 2. Check for AI anomalies (low confidence / extreme coverage)
        anomalies = cls.evaluate_ai_anomalies(confidence_score, area_percentage)
        for anomaly in anomalies:
            is_unusual = True
            flags.append({
                'type': anomaly['flag_type'],
                'reason': anomaly['flag_reason'],
                'description': anomaly['flag_reason']
            })

        # Determine recommended status and triage priority
        if is_unusual:
            recommended_status = 'Flagged for Review'
            priority = 'Urgent Review' if relative_severity == 'Critical' else 'Review Required'
        else:
            recommended_status = 'Pending'
            priority = 'Critical' if relative_severity == 'Critical' else 'Standard'

        # Generate human-readable advisory notes for engineer and citizen
        if is_unusual:
            notes = " ; ".join([f['reason'] for f in flags])
        else:
            notes = f"Standard submission verified: {defect_class} on {asset_type} ({relative_severity} severity)."

        return {
            'is_valid': True,
            'is_unusual': is_unusual,
            'flags': flags,
            'flag_reasons': [f['reason'] for f in flags],
            'recommended_status': recommended_status,
            'priority': priority,
            'advisory_notes': notes,
            'compatibility': compat
        }

# Global singleton
validation_service = ValidationService()
__all__ = ['ValidationService', 'validation_service']
