"""
Validation Service for Civil Infrastructure Monitoring System.
Implements Backend Integrity Checks, Input Sanitization, and Domain Logic Validation.

Enforces rules for defect-infrastructure pairings:
- Road / Pavement: Crack, Pothole, Surface deterioration
- Bridge / Viaduct: Crack, Surface deterioration, Pothole
- Building / Retaining Wall: Crack, Surface deterioration

Special Handling:
Unusual combinations (such as a 'Pothole' reported on a 'Building') are NOT hard-rejected
because edge cases can occur and AI models can make errors. Instead, unusual reports are
flagged with validation_status = 'unusual' and assigned the status 'Flagged for Review',
placing them into the certified engineer's priority queue for human-in-the-loop review.
"""

from typing import Dict, Any, List, Tuple


class ValidationService:
    """
    Centralized backend domain validation service for infrastructure defect compatibility
    and submission integrity.
    """

    STATUS_VALID = 'valid'
    STATUS_UNUSUAL = 'unusual'
    STATUS_INVALID = 'invalid'

    # Centralized taxonomy rules: standard engineering defects mapped to infrastructure categories
    ALLOWED_DEFECTS = {
        'road': {
            'Crack',
            'Pothole',
            'Surface deterioration',
        },
        'building': {
            'Crack',
            'Surface deterioration',
        },
        'bridge': {
            'Crack',
            'Surface deterioration',
            'Pothole',
        },
    }

    # Taxonomy aliases for tolerant user input matching
    ASSET_TYPE_ALIASES = {
        'road': 'road',
        'road / pavement': 'road',
        'pavement': 'road',
        'highway': 'road',
        'street': 'road',
        'bridge': 'bridge',
        'bridge / viaduct': 'bridge',
        'viaduct': 'bridge',
        'building': 'building',
        'public building': 'building',
        'public building / retaining wall': 'building',
        'retaining wall': 'building',
        'retaining wall / perimeter': 'building',
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
    def get_canonical_asset_category(cls, asset_type: str) -> str:
        """Resolves an infrastructure type string to its canonical taxonomy category."""
        norm = cls.normalize_key(asset_type)
        if norm in cls.ASSET_TYPE_ALIASES:
            return cls.ASSET_TYPE_ALIASES[norm]

        if 'road' in norm or 'pave' in norm or 'street' in norm:
            return 'road'
        elif 'bridge' in norm or 'viaduct' in norm:
            return 'bridge'
        elif 'build' in norm or 'wall' in norm:
            return 'building'

        return norm

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
        Evaluates whether a detected defect class is typical, unusual, or invalid
        for the given infrastructure type.

        States:
        - valid: Standard defect for this infrastructure type.
        - unusual: Atypical combination (e.g. Building + Pothole) requiring engineer review. NOT hard-rejected.
        - invalid: Unrecognized, missing, or malformed inputs.
        """
        if not asset_type or not asset_type.strip():
            return {
                'validation_status': cls.STATUS_INVALID,
                'validation_message': 'Infrastructure asset type is missing or invalid.',
                'is_valid': False,
                'is_unusual': False,
                'flag_type': 'INVALID_INPUT',
                'flag_reason': 'Infrastructure asset type is required.'
            }

        if not defect_class or defect_class in ('None Detected', 'None', ''):
            return {
                'validation_status': cls.STATUS_VALID,
                'validation_message': 'No defect detected. Submission valid.',
                'is_valid': True,
                'is_unusual': False,
                'flag_type': 'STANDARD_COMBINATION',
                'flag_reason': None
            }

        category = cls.get_canonical_asset_category(asset_type)
        allowed_set = cls.ALLOWED_DEFECTS.get(category)

        # If completely unknown infrastructure category, accept with review recommendation
        if allowed_set is None:
            return {
                'validation_status': cls.STATUS_UNUSUAL,
                'validation_message': f"Defect '{defect_class}' on unclassified infrastructure '{asset_type}'. Engineer review recommended.",
                'is_valid': True,
                'is_unusual': True,
                'flag_type': 'UNCLASSIFIED_INFRASTRUCTURE',
                'flag_reason': f"Unclassified infrastructure category: '{asset_type}'."
            }

        # Case-insensitive comparison against allowed defect taxonomy
        norm_defect = cls.normalize_key(defect_class)
        allowed_normalized = {cls.normalize_key(d) for d in allowed_set}

        if norm_defect in allowed_normalized:
            return {
                'validation_status': cls.STATUS_VALID,
                'validation_message': f"Defect '{defect_class}' is standard for infrastructure type '{asset_type}'.",
                'is_valid': True,
                'is_unusual': False,
                'flag_type': 'STANDARD_COMBINATION',
                'flag_reason': None
            }
        else:
            # Building + Pothole: Unusual, NOT rejected. Retained for certified engineer review.
            message = (
                f"{defect_class} is unusual for the selected infrastructure type ({asset_type}). "
                "Engineer review is recommended."
            )
            return {
                'validation_status': cls.STATUS_UNUSUAL,
                'validation_message': message,
                'is_valid': True,
                'is_unusual': True,
                'flag_type': 'UNUSUAL_COMBINATION',
                'flag_reason': f"Unusual combination: '{defect_class}' defect on '{asset_type}' infrastructure.",
                'advisory': message
            }

    @classmethod
    def evaluate_ai_anomalies(cls, confidence_score: float, area_percentage: float) -> List[Dict[str, str]]:
        """
        Checks for edge cases in AI pre-assessment such as low confidence or extreme defect extent.
        """
        anomalies = []

        if confidence_score is not None and 0.0 < confidence_score < 0.40:
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
        Enriches individual detection items with their validation status.
        """
        defect_class = detection_result.get('defect_class') or detection_result.get('class_name') or 'Crack'
        confidence_score = float(detection_result.get('confidence_score') or detection_result.get('confidence') or 0.0)
        area_percentage = float(detection_result.get('area_percentage') or 0.0)
        relative_severity = detection_result.get('relative_severity') or detection_result.get('severity') or 'Moderate'

        flags = []
        is_unusual = False

        # 1. Defect vs Infrastructure pairing check
        compat = cls.check_defect_compatibility(asset_type, defect_class)
        if compat['is_unusual']:
            is_unusual = True
            flags.append({
                'type': compat['flag_type'],
                'reason': compat['flag_reason'],
                'description': compat['validation_message']
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

        # Enrich detections list if present
        detections = detection_result.get('detections', [])
        for det in detections:
            d_class = det.get('class_name') or det.get('defect_class')
            d_compat = cls.check_defect_compatibility(asset_type, d_class)
            det['validation_status'] = d_compat['validation_status']
            det['validation_message'] = d_compat['validation_message']

        # Determine recommended status and triage priority
        if is_unusual:
            recommended_status = 'Flagged for Review'
            priority = 'Urgent Review' if relative_severity == 'Critical' else 'Review Required'
            overall_validation_status = cls.STATUS_UNUSUAL
            overall_validation_message = compat.get('validation_message') or " ; ".join([f['reason'] for f in flags])
        else:
            recommended_status = 'Pending'
            priority = 'Critical' if relative_severity == 'Critical' else 'Standard'
            overall_validation_status = cls.STATUS_VALID
            overall_validation_message = compat.get('validation_message') or f"Standard submission verified: {defect_class} on {asset_type} ({relative_severity} severity)."

        # Advisory notes for UI and logs
        notes = " ; ".join([f['reason'] for f in flags]) if flags else overall_validation_message

        return {
            'is_valid': compat.get('is_valid', True),
            'is_unusual': is_unusual,
            'validation_status': overall_validation_status,
            'validation_message': overall_validation_message,
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
