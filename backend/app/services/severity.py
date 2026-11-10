"""
Visual Severity Assessment Service for Civil Infrastructure Monitoring System.
Implements:
1. Relative Visual Severity Index (RVSI) heuristic based on detected bounding-box geometry:
   - Union bounding-box area extent (no overlap double-counting)
   - Spatial span (normalized diagonal)
   - Multiplicity (count of credible detections)
2. Multi-image report evidence aggregation (0.70 * max + 0.30 * mean)
3. Physical Engineering Assessment support (e.g. FHWA LTPP pothole depth classification)

CRITICAL NOTICE & CONCEPT SEPARATION:
InfraVision strictly distinguishes three separate concepts:
1. AI Model Confidence:
   How certain the detector is (0.0 to 1.0). NOT a component of RVSI.
2. Relative Visual Severity (RVSI):
   Image-derived monitoring & prioritization evidence (0 to 100).
   NEVER present as a structural safety rating or engineering certification.
3. Physical Engineering Assessment:
   Measurement-derived professional assessment (e.g. FHWA LTPP depth rule).
   Subject to licensed engineer validation.
"""

import math
import os
from typing import Dict, Any, List, Union, Optional


class SeverityService:
    """
    Computes image-derived defect extent and maps bounding boxes
    to standardized relative visual severity categories and RVSI scores.
    """

    SEVERITY_LOW = 'Low'
    SEVERITY_MODERATE = 'Moderate'
    SEVERITY_MEDIUM = 'Moderate'  # Alias for compatibility
    SEVERITY_CRITICAL = 'Critical'
    SEVERITY_HIGH = 'Critical'   # Alias for compatibility

    # Prototype visual severity thresholds based on bounding-box area relative to image (legacy fallback)
    DEFAULT_LOW_THRESHOLD = float(os.getenv('SEVERITY_LOW_THRESHOLD', '0.05'))       # < 5%
    DEFAULT_CRITICAL_THRESHOLD = float(os.getenv('SEVERITY_CRITICAL_THRESHOLD', '0.15')) # >= 15%

    # RVSI configuration thresholds
    DEFAULT_RVSI_LOW_UPPER = float(os.getenv('RVSI_LOW_UPPER', '20.0'))        # < 20.0 -> Low
    DEFAULT_RVSI_MODERATE_UPPER = float(os.getenv('RVSI_MODERATE_UPPER', '45.0')) # 20.0 - 45.0 -> Moderate, >= 45.0 -> Critical
    DEFAULT_RVSI_THRESHOLD_SOURCE = os.getenv('RVSI_THRESHOLD_SOURCE', 'calibrated') # 'calibrated' | 'legacy_fallback'

    RVSI_METHOD_NAME = "Relative Visual Severity Index"
    RVSI_VERSION = "1.0"
    AGGREGATION_METHOD = "0.70_max_plus_0.30_mean"
    AGGREGATION_VERSION = "1.0"
    POSTPROCESSING_VERSION = "1.0"

    RVSI_DISCLAIMER = (
        "Relative Visual Severity: Image-derived monitoring priority based on visible defect extent "
        "and distribution. This is not a structural safety rating and remains subject to professional verification."
    )

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
    def _extract_normalized_coords(cls, box: Union[List, tuple, dict], image_width: int = None, image_height: int = None) -> Optional[List[float]]:
        """
        Extracts normalized [ymin, xmin, ymax, xmax] coordinates from various representations.
        Clamps coordinates to [0.0, 1.0].
        """
        if isinstance(box, dict):
            # Check for normalized_box first
            if 'normalized_box' in box and isinstance(box['normalized_box'], (list, tuple)) and len(box['normalized_box']) >= 4:
                return cls._extract_normalized_coords(box['normalized_box'])
            # Check for pixel bounding_box dict
            px_box = box.get('bounding_box') or box
            if isinstance(px_box, dict) and 'xmin' in px_box and 'ymin' in px_box:
                xmin = float(px_box.get('xmin', 0.0))
                ymin = float(px_box.get('ymin', 0.0))
                xmax = float(px_box.get('xmax', 0.0))
                ymax = float(px_box.get('ymax', 0.0))
                if image_width and image_height and image_width > 0 and image_height > 0:
                    return [
                        max(0.0, min(1.0, ymin / image_height)),
                        max(0.0, min(1.0, xmin / image_width)),
                        max(0.0, min(1.0, ymax / image_height)),
                        max(0.0, min(1.0, xmax / image_width))
                    ]
            return None

        if isinstance(box, (list, tuple)) and len(box) >= 4:
            ymin, xmin, ymax, xmax = float(box[0]), float(box[1]), float(box[2]), float(box[3])
            y1 = max(0.0, min(1.0, min(ymin, ymax)))
            x1 = max(0.0, min(1.0, min(xmin, xmax)))
            y2 = max(0.0, min(1.0, max(ymin, ymax)))
            x2 = max(0.0, min(1.0, max(xmin, xmax)))
            return [y1, x1, y2, x2]

        return None

    @classmethod
    def calculate_boxes_union_area(cls, boxes: List[Union[List, tuple, dict]], image_width: int = None, image_height: int = None) -> float:
        """
        Computes the exact geometric union area of normalized bounding boxes [ymin, xmin, ymax, xmax]
        using a 1D sweep-line algorithm (Klee's measure in 2D).
        Guarantees NO double-counting of overlapping regions between bounding boxes.
        Returns a float in [0.0, 1.0].
        """
        norm_boxes = []
        for b in boxes:
            coords = cls._extract_normalized_coords(b, image_width=image_width, image_height=image_height)
            if coords:
                y1, x1, y2, x2 = coords
                if x2 > x1 and y2 > y1:
                    norm_boxes.append((x1, y1, x2, y2))

        if not norm_boxes:
            return 0.0

        # Unique sorted x-coordinates
        x_events = sorted(list(set([b[0] for b in norm_boxes] + [b[2] for b in norm_boxes])))
        total_union_area = 0.0

        for i in range(len(x_events) - 1):
            x_left = x_events[i]
            x_right = x_events[i + 1]
            dx = x_right - x_left
            if dx <= 1e-9:
                continue

            # Active boxes spanning this x-slab
            y_intervals = []
            for (bx1, by1, bx2, by2) in norm_boxes:
                if bx1 <= x_left and bx2 >= x_right:
                    y_intervals.append((by1, by2))

            if not y_intervals:
                continue

            # 1D union of y-intervals
            y_intervals.sort(key=lambda item: item[0])
            merged_intervals = []
            curr_start, curr_end = y_intervals[0]

            for s, e in y_intervals[1:]:
                if s <= curr_end:
                    curr_end = max(curr_end, e)
                else:
                    merged_intervals.append((curr_start, curr_end))
                    curr_start, curr_end = s, e
            merged_intervals.append((curr_start, curr_end))

            dy = sum(e - s for s, e in merged_intervals)
            total_union_area += dx * dy

        return round(float(max(0.0, min(1.0, total_union_area))), 4)

    @classmethod
    def calculate_rvsi(
        cls,
        detections: List[Union[Dict[str, Any], List, tuple]],
        image_width: int = None,
        image_height: int = None,
        low_upper: float = None,
        moderate_upper: float = None,
        threshold_source: str = None
    ) -> Dict[str, Any]:
        """
        Computes the Relative Visual Severity Index (RVSI) from cleaned credible detections.

        Mathematical formulation:
            rvsi = 100 * (0.50 * sqrt(area_extent) + 0.35 * spatial_span + 0.15 * multiplicity)
            clamped to [0.0, 100.0].

        Components:
        - area_extent: union bounding-box area / image_area, clamped to [0, 1] (no double counting).
        - spatial_span: max_i sqrt(w_i^2 + h_i^2) / sqrt(2), clamped to [0, 1].
        - multiplicity: min(detection_count / 5.0, 1.0).

        Model confidence is NOT a component of RVSI.
        """
        low_up = low_upper if low_upper is not None else cls.DEFAULT_RVSI_LOW_UPPER
        mod_up = moderate_upper if moderate_upper is not None else cls.DEFAULT_RVSI_MODERATE_UPPER
        source = threshold_source or cls.DEFAULT_RVSI_THRESHOLD_SOURCE

        if not detections:
            return {
                'rvsi_score': 0.0,
                'relative_severity': cls.SEVERITY_LOW,
                'area_extent': 0.0,
                'spatial_span': 0.0,
                'multiplicity': 0.0,
                'detection_count': 0,
                'rvsi_method': cls.RVSI_METHOD_NAME,
                'rvsi_version': cls.RVSI_VERSION,
                'severity_threshold_source': source,
                'thresholds': {'low_upper': low_up, 'moderate_upper': mod_up},
                'disclaimer': cls.RVSI_DISCLAIMER
            }

        # 1. Geometric union area (no double-counting)
        area_extent = cls.calculate_boxes_union_area(detections, image_width=image_width, image_height=image_height)

        # 2. Spatial span calculation
        max_span = 0.0
        sqrt_2 = math.sqrt(2.0)
        valid_coords_count = 0

        for d in detections:
            coords = cls._extract_normalized_coords(d, image_width=image_width, image_height=image_height)
            if coords:
                y1, x1, y2, x2 = coords
                w = max(0.0, x2 - x1)
                h = max(0.0, y2 - y1)
                diag = math.sqrt(w * w + h * h)
                norm_span = min(1.0, max(0.0, diag / sqrt_2))
                if norm_span > max_span:
                    max_span = norm_span
                valid_coords_count += 1

        spatial_span = round(float(max_span), 4)

        # 3. Multiplicity calculation
        cleaned_count = valid_coords_count if valid_coords_count > 0 else len(detections)
        multiplicity = round(float(min(cleaned_count / 5.0, 1.0)), 4)

        # 4. Canonical RVSI score calculation
        # rvsi = 100 * (0.50 * sqrt(area_extent) + 0.35 * spatial_span + 0.15 * multiplicity)
        sqrt_area = math.sqrt(area_extent)
        raw_rvsi = 100.0 * (0.50 * sqrt_area + 0.35 * spatial_span + 0.15 * multiplicity)
        rvsi_score = round(float(max(0.0, min(100.0, raw_rvsi))), 1)

        # 5. Category classification
        if rvsi_score < low_up:
            category = cls.SEVERITY_LOW
        elif rvsi_score < mod_up:
            category = cls.SEVERITY_MODERATE
        else:
            category = cls.SEVERITY_CRITICAL

        return {
            'rvsi_score': rvsi_score,
            'relative_severity': category,
            'area_extent': area_extent,
            'spatial_span': spatial_span,
            'multiplicity': multiplicity,
            'detection_count': cleaned_count,
            'rvsi_method': cls.RVSI_METHOD_NAME,
            'rvsi_version': cls.RVSI_VERSION,
            'severity_threshold_source': source,
            'thresholds': {'low_upper': low_up, 'moderate_upper': mod_up},
            'disclaimer': cls.RVSI_DISCLAIMER
        }

    @classmethod
    def get_rvsi_category(cls, rvsi_score: float, low_upper: float = None, moderate_upper: float = None) -> str:
        """
        Maps an RVSI score (0-100) to its category: Low, Moderate, or Critical.
        """
        low_up = low_upper if low_upper is not None else cls.DEFAULT_RVSI_LOW_UPPER
        mod_up = moderate_upper if moderate_upper is not None else cls.DEFAULT_RVSI_MODERATE_UPPER

        if rvsi_score < low_up:
            return cls.SEVERITY_LOW
        elif rvsi_score < mod_up:
            return cls.SEVERITY_MODERATE
        else:
            return cls.SEVERITY_CRITICAL

    @classmethod
    def calculate_report_rvsi(cls, image_rvsi_scores: List[float]) -> Dict[str, Any]:
        """
        Aggregates multiple image RVSI scores into a single report-level RVSI score:
        - Single-image report: report_rvsi = image_rvsi
        - Multi-image report (>= 2 images): report_rvsi = 0.70 * max(scores) + 0.30 * mean(scores)
        """
        if not image_rvsi_scores:
            return {
                'report_rvsi': 0.0,
                'relative_severity': cls.SEVERITY_LOW,
                'image_rvsi_scores': [],
                'aggregation_method': 'single_image',
                'aggregation_version': cls.AGGREGATION_VERSION
            }

        cleaned_scores = [float(s) for s in image_rvsi_scores if s is not None]
        if not cleaned_scores:
            cleaned_scores = [0.0]

        if len(cleaned_scores) == 1:
            score = round(cleaned_scores[0], 1)
            method = 'single_image'
        else:
            max_val = max(cleaned_scores)
            mean_val = sum(cleaned_scores) / len(cleaned_scores)
            raw_score = 0.70 * max_val + 0.30 * mean_val
            score = round(max(0.0, min(100.0, raw_score)), 1)
            method = cls.AGGREGATION_METHOD

        category = cls.get_rvsi_category(score)

        return {
            'report_rvsi': score,
            'relative_severity': category,
            'image_rvsi_scores': [round(s, 1) for s in cleaned_scores],
            'aggregation_method': method,
            'aggregation_version': cls.AGGREGATION_VERSION
        }

    # ─────────────────────────────────────────────────────────────
    # PHYSICAL ENGINEERING ASSESSMENT SUPPORT
    # ─────────────────────────────────────────────────────────────

    @classmethod
    def normalize_measurement(cls, value: Union[int, float, str], unit: str) -> Optional[float]:
        """
        Normalizes a physical linear measurement to millimeters (mm).
        Supports: mm, cm, m, inch.
        Returns float in mm or None if invalid.
        """
        if value is None:
            return None
        try:
            val_f = float(value)
        except (ValueError, TypeError):
            return None

        if val_f < 0.0:
            return None

        u = (unit or 'mm').strip().lower()
        if u in ['mm', 'millimeter', 'millimeters']:
            return round(val_f, 2)
        elif u in ['cm', 'centimeter', 'centimeters']:
            return round(val_f * 10.0, 2)
        elif u in ['m', 'meter', 'meters']:
            return round(val_f * 1000.0, 2)
        elif u in ['in', 'inch', 'inches']:
            return round(val_f * 25.4, 2)
        else:
            return round(val_f, 2)

    @classmethod
    def assess_pothole_fhwa(cls, depth_value: Union[int, float], unit: str = 'mm') -> Optional[Dict[str, Any]]:
        """
        Evaluates physical engineering severity of a pothole based on measured depth
        per the FHWA Long-Term Pavement Performance (LTPP) distress manual:
        - Depth < 25 mm  (< 1.0 in) -> 'Low'
        - 25 mm <= Depth <= 50 mm (1.0 to 2.0 in) -> 'Moderate'
        - Depth > 50 mm  (> 2.0 in) -> 'High'

        Requires a valid physical measurement. Monocular images CANNOT infer depth.
        """
        depth_mm = cls.normalize_measurement(depth_value, unit)
        if depth_mm is None:
            return None

        if depth_mm < 25.0:
            category = 'Low'
        elif depth_mm <= 50.0:
            category = 'Moderate'
        else:
            category = 'High'

        return {
            'standard': 'FHWA_LTPP',
            'rule': 'Pothole depth classification (<25mm Low, 25-50mm Moderate, >50mm High)',
            'measured_depth_mm': depth_mm,
            'category': category,
            'physical_severity': category,
            'is_physical_assessment': True
        }

    # ─────────────────────────────────────────────────────────────
    # BACKWARDS COMPATIBILITY
    # ─────────────────────────────────────────────────────────────

    @classmethod
    def evaluate_relative_severity(cls, detections: List[Dict[str, Any]], low_thresh: float = None, critical_thresh: float = None) -> Dict[str, Any]:
        """
        Evaluates cumulative defect extent from detection bounding boxes.
        Maintains backwards compatibility with legacy callers while integrating RVSI.
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
                'rvsi_score': 0.0,
                'thresholds': {'low': low_t, 'critical': crit_t}
            }

        rvsi_res = cls.calculate_rvsi(detections)
        union_area = rvsi_res['area_extent']
        severity = cls.calculate_severity_for_area(union_area, low_thresh=low_t, critical_thresh=crit_t)

        return {
            'severity': severity,
            'relative_severity': severity,
            'relative_area': union_area,
            'area_ratio': union_area,
            'area_percentage': round(union_area * 100.0, 2),
            'rvsi_score': rvsi_res['rvsi_score'],
            'rvsi': rvsi_res,
            'thresholds': {'low': low_t, 'critical': crit_t}
        }


# Global singleton service
severity_service = SeverityService()
__all__ = ['SeverityService', 'severity_service']
