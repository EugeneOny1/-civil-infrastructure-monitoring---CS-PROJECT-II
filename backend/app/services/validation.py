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
        defect-infrastructure compatibility across ALL detected classes, and AI telemetry.
        Enriches individual detection items with their validation status.

        Decouples:
        - Report Lifecycle: canonical status is 'Received'
        - Validation Status: 'valid' | 'unusual' | 'invalid'
        - Engineer Review Status: requires_engineer_review (boolean)
        """
        detections = detection_result.get('detections', [])
        primary_defect = detection_result.get('defect_class') or detection_result.get('class_name') or 'Crack'
        confidence_score = float(detection_result.get('confidence_score') or detection_result.get('confidence') or 0.0)
        area_percentage = float(detection_result.get('area_percentage') or 0.0)
        relative_severity = detection_result.get('relative_severity') or detection_result.get('severity') or 'Moderate'

        flags = []
        unusual_detected_classes = []

        # 1. Defect vs Infrastructure pairing check across ALL detected classes
        classes_to_check = set()
        if detections:
            for det in detections:
                c_name = det.get('class_name') or det.get('defect_class')
                if c_name:
                    classes_to_check.add(c_name)
        else:
            classes_to_check.add(primary_defect)

        for d_class in classes_to_check:
            compat = cls.check_defect_compatibility(asset_type, d_class)
            if compat['is_unusual']:
                unusual_detected_classes.append(d_class)
                flags.append({
                    'type': compat['flag_type'],
                    'reason': compat['flag_reason'],
                    'description': compat['validation_message']
                })

        # Enrich each detection object
        for det in detections:
            d_class = det.get('class_name') or det.get('defect_class')
            d_compat = cls.check_defect_compatibility(asset_type, d_class)
            det['validation_status'] = d_compat['validation_status']
            det['validation_message'] = d_compat['validation_message']

        # Determine if pairing is unusual
        is_unusual_pairing = len(unusual_detected_classes) > 0

        # 2. Informational AI telemetry anomalies (flagged for review without altering standard pairing validity)
        anomalies = cls.evaluate_ai_anomalies(confidence_score, area_percentage)
        for anomaly in anomalies:
            flags.append({
                'type': anomaly['flag_type'],
                'reason': anomaly['flag_reason'],
                'description': anomaly['flag_reason']
            })

        # Decouple validation status from lifecycle:
        # validation_status is 'unusual' only if an unusual pairing exists (e.g. Building + Pothole)
        overall_validation_status = cls.STATUS_UNUSUAL if is_unusual_pairing else cls.STATUS_VALID
        
        # requires_engineer_review is set if unusual, critical, or anomalous
        requires_engineer_review = is_unusual_pairing or (relative_severity == 'Critical') or (len(anomalies) > 0)

        # Canonical initial report lifecycle status is ALWAYS 'Received'
        canonical_lifecycle_status = 'Received'

        if is_unusual_pairing:
            priority = 'Urgent Review' if relative_severity == 'Critical' else 'Review Required'
            overall_validation_message = (
                f"Atypical combination detected: {', '.join(unusual_detected_classes)} on {asset_type}. "
                "Retained for certified civil engineer review."
            )
        else:
            priority = 'Critical' if relative_severity == 'Critical' else 'Standard'
            overall_validation_message = f"Valid defect pairing: {', '.join(classes_to_check)} on {asset_type} ({relative_severity} visual severity)."

        notes = " ; ".join([f['reason'] for f in flags]) if flags else overall_validation_message

        return {
            'is_valid': True,
            'is_unusual': is_unusual_pairing,
            'requires_engineer_review': requires_engineer_review,
            'validation_status': overall_validation_status,
            'validation_message': overall_validation_message,
            'flags': flags,
            'flag_reasons': [f['reason'] for f in flags],
            'recommended_status': canonical_lifecycle_status,
            'priority': priority,
            'advisory_notes': notes,
            'unusual_classes': unusual_detected_classes,
            'checked_classes': list(classes_to_check)
        }


# Global singleton
validation_service = ValidationService()
__all__ = ['ValidationService', 'validation_service']
