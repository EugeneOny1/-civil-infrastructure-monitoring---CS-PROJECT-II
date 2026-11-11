"""
AI Inference Service for Civil Infrastructure Structural Defect Detection.
Architecture: SSD-MobileNetV2 (Single Shot MultiBox Detector)
Export Format: TensorFlow SavedModel
Target Defect Classes:
  1: Crack
  2: Pothole
  3: Surface deterioration

Framework: TensorFlow Object Detection API
Serving Signature: serving_default
Expected Input: RGB image, dtype: uint8, shape: [1, height, width, 3]
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from PIL import Image

# Import TensorFlow
try:
    import tensorflow as tf
    HAS_TENSORFLOW = True
except ImportError:
    HAS_TENSORFLOW = False

# Optional OpenCV support
try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False


from .severity import severity_service


class InferenceService:
    """
    Canonical AI Inference Service for Civil Infrastructure Structural Defect Detection.
    Loads and serves the trained SSD-MobileNetV2 TensorFlow SavedModel graph.
    """

    CLASS_NAMES = {
        1: 'Crack',
        2: 'Pothole',
        3: 'Surface deterioration'
    }

    DEFAULT_CONFIDENCE_THRESHOLD = 0.30
    DEFAULT_MODEL_VERSION = 'ssd_mobilenet_v2_lr00625_step8000_v2'
    DEFAULT_MODEL_NAME = 'SSD-MobileNetV2'

    # Prototype visual severity thresholds (relative bounding box area to image area)
    SEVERITY_LOW_THRESHOLD = 0.05       # < 5%
    SEVERITY_CRITICAL_THRESHOLD = 0.15 # >= 15%

    # Class-aware duplicate suppression IoU threshold
    DEFAULT_IOU_THRESHOLD = 0.50

    def __init__(self, model_path=None, confidence_threshold=None, model_version=None, iou_threshold=None):
        self.model_name = self.DEFAULT_MODEL_NAME
        self.model_version = model_version or os.getenv('MODEL_VERSION', self.DEFAULT_MODEL_VERSION)
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else float(os.getenv('DETECTION_CONFIDENCE_THRESHOLD', str(self.DEFAULT_CONFIDENCE_THRESHOLD)))
        )
        self.iou_threshold = (
            iou_threshold
            if iou_threshold is not None
            else float(os.getenv('DUPLICATE_IOU_THRESHOLD', str(self.DEFAULT_IOU_THRESHOLD)))
        )
        self.model_path = model_path or os.getenv('MODEL_PATH')
        self.saved_model = None
        self.serving_fn = None
        self.is_loaded = False
        self.load_error = None
        self.load_model(self.model_path)

    def _resolve_model_path(self, candidate_path=None):
        """
        Resolves the SavedModel directory from candidate paths, configuration,
        or repository relative defaults.
        """
        service_dir = Path(__file__).resolve().parent
        app_dir = service_dir.parent
        backend_dir = app_dir.parent
        root_dir = backend_dir.parent

        candidates = []
        if candidate_path:
            candidates.append(Path(candidate_path))
            if not Path(candidate_path).is_absolute():
                candidates.append(backend_dir / candidate_path)
                candidates.append(root_dir / candidate_path)

        # Environment variable
        env_path = os.getenv('MODEL_PATH')
        if env_path:
            candidates.append(Path(env_path))
            if not Path(env_path).is_absolute():
                candidates.append(backend_dir / env_path)
                candidates.append(root_dir / env_path)

        # Standard repository conventions
        candidates.extend([
            backend_dir / 'models' / 'structural_defect_detector',
            app_dir / 'models' / 'structural_defect_detector',
            root_dir / 'backend' / 'models' / 'structural_defect_detector',
            root_dir / 'models' / 'structural_defect_detector'
        ])

        for path in candidates:
            if path.exists() and (path / 'saved_model.pb').exists():
                return str(path.resolve())

        return candidate_path or str(backend_dir / 'models' / 'structural_defect_detector')

    def load_model(self, model_path=None):
        """
        Loads the TensorFlow SavedModel ONCE during initialization using tf.saved_model.load.
        Retrieves the serving_default signature for inference execution.
        """
        resolved_path = self._resolve_model_path(model_path)
        self.model_path = resolved_path

        if not HAS_TENSORFLOW:
            err_msg = "TensorFlow is not installed in the current environment."
            print(f"[InferenceService] ERROR: {err_msg}")
            self.is_loaded = False
            self.load_error = err_msg
            return False

        if not os.path.exists(resolved_path) or not os.path.exists(os.path.join(resolved_path, 'saved_model.pb')):
            err_msg = f"SavedModel not found at '{resolved_path}' (missing saved_model.pb)."
            print(f"[InferenceService] ERROR: {err_msg}")
            self.is_loaded = False
            self.load_error = err_msg
            return False

        try:
            print(f"[InferenceService] Loading TensorFlow SavedModel from: {resolved_path}")
            loaded_model = tf.saved_model.load(resolved_path)
            self.saved_model = loaded_model

            available_signatures = list(loaded_model.signatures.keys())
            if 'serving_default' in loaded_model.signatures:
                self.serving_fn = loaded_model.signatures['serving_default']
            else:
                sig_keys = available_signatures
                if sig_keys:
                    self.serving_fn = loaded_model.signatures[sig_keys[0]]
                else:
                    self.serving_fn = loaded_model

            self.is_loaded = True
            self.load_error = None
            print(f"[InferenceService] Structural defect SavedModel loaded successfully. Serving signature available: {available_signatures}")
            return True

        except Exception as e:
            self.is_loaded = False
            self.load_error = str(e)
            self.saved_model = None
            self.serving_fn = None
            print(f"[InferenceService] ERROR loading SavedModel: {e}")
            return False

    def preprocess_image(self, image_input):
        """
        Safely validates, decodes, and converts uploaded image to RGB uint8 tensor.
        Preserves original image width and height without manual resizing.

        Returns:
            rgb_arr (np.ndarray): uint8 RGB image array [H, W, 3]
            dimensions (tuple): (original_width, original_height)
        """
        if isinstance(image_input, (str, Path)):
            if not os.path.exists(str(image_input)):
                raise FileNotFoundError(f"Image file does not exist: {image_input}")
            try:
                with Image.open(str(image_input)) as img:
                    img.verify()
                with Image.open(str(image_input)) as img:
                    rgb_img = img.convert('RGB')
                    orig_w, orig_h = rgb_img.size
                    rgb_arr = np.array(rgb_img, dtype=np.uint8)
                    return rgb_arr, (orig_w, orig_h)
            except Exception as e:
                raise ValueError(f"Corrupted or invalid image file: {e}")

        elif hasattr(image_input, 'read'):
            try:
                with Image.open(image_input) as img:
                    rgb_img = img.convert('RGB')
                    orig_w, orig_h = rgb_img.size
                    rgb_arr = np.array(rgb_img, dtype=np.uint8)
                    return rgb_arr, (orig_w, orig_h)
            except Exception as e:
                raise ValueError(f"Unable to decode image stream: {e}")

        elif isinstance(image_input, np.ndarray):
            if image_input.ndim != 3 or image_input.shape[2] != 3:
                raise ValueError(f"Expected 3-channel RGB NumPy array, got shape {image_input.shape}")
            orig_h, orig_w = image_input.shape[:2]
            return image_input.astype(np.uint8), (orig_w, orig_h)

        else:
            raise TypeError(f"Unsupported image input type: {type(image_input)}")

    @classmethod
    def calculate_relative_severity(cls, relative_area, low_thresh=None, critical_thresh=None):
        """
        Delegates visual severity heuristic to centralized SeverityService.
        Documented: 'Relative visual severity based on detected bounding-box area.'
        It is NOT:
        - structural integrity certification
        - structural failure probability
        - engineering safety assessment
        - model confidence
        """
        return severity_service.calculate_severity_for_area(
            relative_area,
            low_thresh=low_thresh if low_thresh is not None else cls.SEVERITY_LOW_THRESHOLD,
            critical_thresh=critical_thresh if critical_thresh is not None else cls.SEVERITY_CRITICAL_THRESHOLD
        )

    @staticmethod
    def calculate_box_iou(box_a, box_b) -> float:
        """
        Calculates Intersection-over-Union (IoU) between two bounding boxes.
        Accepts normalized [ymin, xmin, ymax, xmax] or dicts with xmin, ymin, xmax, ymax.
        """
        if isinstance(box_a, (list, tuple)):
            y1_a, x1_a, y2_a, x2_a = box_a
        else:
            x1_a, y1_a = box_a['xmin'], box_a['ymin']
            x2_a, y2_a = box_a['xmax'], box_a['ymax']

        if isinstance(box_b, (list, tuple)):
            y1_b, x1_b, y2_b, x2_b = box_b
        else:
            x1_b, y1_b = box_b['xmin'], box_b['ymin']
            x2_b, y2_b = box_b['xmax'], box_b['ymax']

        inter_x1 = max(x1_a, x1_b)
        inter_y1 = max(y1_a, y1_b)
        inter_x2 = min(x2_a, x2_b)
        inter_y2 = min(y2_a, y2_b)

        inter_w = max(0.0, inter_x2 - inter_x1)
        inter_h = max(0.0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h

        area_a = max(0.0, x2_a - x1_a) * max(0.0, y2_a - y1_a)
        area_b = max(0.0, x2_b - x1_b) * max(0.0, y2_b - y1_b)
        union_area = area_a + area_b - inter_area

        if union_area <= 0.0:
            return 0.0
        return float(inter_area / union_area)

    @classmethod
    def suppress_class_aware_duplicates(cls, detections: List[Dict[str, Any]], iou_threshold: float = None) -> List[Dict[str, Any]]:
        """
        Applies class-aware Non-Maximum Suppression (NMS) duplicate suppression:
        - Same class + high overlap (IoU >= threshold) -> duplicate suppressed (keeps higher confidence).
        - Different classes (e.g. Crack vs Pothole or Surface deterioration) -> preserved
          even if their boxes overlap, providing primary and alternative defect evidence for review.
        """
        if not detections:
            return []

        threshold = iou_threshold if iou_threshold is not None else cls.DEFAULT_IOU_THRESHOLD

        # Sort detections descending by confidence score
        sorted_dets = sorted(detections, key=lambda d: d.get('confidence', 0.0), reverse=True)

        surviving = []
        for det in sorted_dets:
            det_class = det.get('class_id')
            det_box = det.get('normalized_box')
            keep = True
            for accepted in surviving:
                # Class-aware: only suppress if they belong to the SAME defect class
                if accepted.get('class_id') == det_class:
                    iou = cls.calculate_box_iou(det_box, accepted.get('normalized_box'))
                    if iou >= threshold:
                        keep = False
                        break
            if keep:
                surviving.append(det)

        return surviving

    @classmethod
    def detect_cross_class_overlaps(cls, detections: List[Dict[str, Any]], overlap_threshold: float = 0.35) -> List[Dict[str, Any]]:
        """
        Identifies co-located detections belonging to DIFFERENT defect classes.
        Both predictions are retained for engineer inspection rather than suppressed.
        """
        overlaps = []
        if not detections or len(detections) < 2:
            return overlaps

        for i in range(len(detections)):
            for j in range(i + 1, len(detections)):
                det_a = detections[i]
                det_b = detections[j]
                if det_a.get('class_id') != det_b.get('class_id'):
                    box_a = det_a.get('normalized_box')
                    box_b = det_b.get('normalized_box')
                    iou = cls.calculate_box_iou(box_a, box_b)
                    if iou >= overlap_threshold:
                        overlaps.append({
                            'primary_defect': det_a.get('class_name'),
                            'primary_confidence': det_a.get('confidence'),
                            'alternative_defect': det_b.get('class_name'),
                            'alternative_confidence': det_b.get('confidence'),
                            'iou': round(iou, 4),
                            'note': 'Cross-class co-located detection preserved for professional engineer review.'
                        })
        return overlaps

    @classmethod
    def group_crack_regions(cls, detections: List[Dict[str, Any]], distance_threshold: float = 0.08) -> List[Dict[str, Any]]:
        """
        Conservative presentation-layer grouping for connected crack detections.
        Groups adjacent/overlapping Crack segments into an envelope display region
        while preserving all raw neural network detections and confidence scores for audit.
        """
        crack_dets = [d for d in detections if d.get('class_name') == 'Crack']
        if len(crack_dets) <= 1:
            return []

        def boxes_adjacent_or_overlapping(box_a, box_b, dist_thresh):
            y1_a, x1_a, y2_a, x2_a = box_a
            y1_b, x1_b, y2_b, x2_b = box_b
            dx = max(0.0, max(x1_a, x1_b) - min(x2_a, x2_b))
            dy = max(0.0, max(y1_a, y1_b) - min(y2_a, y2_b))
            return dx <= dist_thresh and dy <= dist_thresh

        visited = set()
        clusters = []

        for i, det_a in enumerate(crack_dets):
            if i in visited:
                continue
            cluster = [det_a]
            visited.add(i)
            queue = [det_a]

            while queue:
                current = queue.pop(0)
                box_curr = current.get('normalized_box')
                for j, det_b in enumerate(crack_dets):
                    if j not in visited:
                        box_b = det_b.get('normalized_box')
                        if boxes_adjacent_or_overlapping(box_curr, box_b, distance_threshold):
                            visited.add(j)
                            cluster.append(det_b)
                            queue.append(det_b)

            if len(cluster) > 1:
                clusters.append(cluster)

        regions = []
        for cluster in clusters:
            all_boxes = [d.get('normalized_box') for d in cluster]
            min_y = min(b[0] for b in all_boxes)
            min_x = min(b[1] for b in all_boxes)
            max_y = max(b[2] for b in all_boxes)
            max_x = max(b[3] for b in all_boxes)

            all_px = [d.get('bounding_box') for d in cluster]
            min_px_x = min(b['xmin'] for b in all_px)
            min_px_y = min(b['ymin'] for b in all_px)
            max_px_x = max(b['xmax'] for b in all_px)
            max_px_y = max(b['ymax'] for b in all_px)

            regions.append({
                'region_type': 'crack_cluster',
                'label': f"Crack region — {len(cluster)} detected crack segments",
                'segment_count': len(cluster),
                'normalized_envelope': [round(min_y, 4), round(min_x, 4), round(max_y, 4), round(max_x, 4)],
                'pixel_envelope': {
                    'xmin': min_px_x,
                    'ymin': min_px_y,
                    'xmax': max_px_x,
                    'ymax': max_px_y
                },
                'segments': cluster
            })

        return regions

    def detect_defects(self, image_input, confidence_threshold=None, iou_threshold=None):
        """
        Executes structural defect detection using the loaded TensorFlow SavedModel.
        
        Args:
            image_input: File path, file-like object, or NumPy RGB array.
            confidence_threshold: Optional override for detection confidence threshold.
            iou_threshold: Optional override for class-aware duplicate suppression IoU threshold.

        Returns:
            Dictionary containing primary defect summary, full surviving detections list,
            detected classes list, pixel coordinates, relative visual severity, and metadata.
        """
        if not self.is_loaded or self.serving_fn is None:
            err = self.load_error or "SavedModel is not loaded."
            raise RuntimeError(f"Defect detector SavedModel is unavailable: {err}")

        conf_thresh = (
            confidence_threshold
            if confidence_threshold is not None
            else self.confidence_threshold
        )
        nms_iou = (
            iou_threshold
            if iou_threshold is not None
            else self.iou_threshold
        )

        rgb_arr, (orig_w, orig_h) = self.preprocess_image(image_input)

        # Expected model input: uint8 tensor [1, height, width, 3]
        input_tensor = tf.convert_to_tensor(rgb_arr[np.newaxis, ...], dtype=tf.uint8)

        # Execute SavedModel serving signature
        try:
            output_dict = self.serving_fn(input_tensor=input_tensor)
        except Exception as e:
            raise RuntimeError(f"TensorFlow SavedModel inference execution failed: {e}")

        # Extract output tensors
        raw_boxes = output_dict['detection_boxes'][0].numpy()
        raw_scores = output_dict['detection_scores'][0].numpy()
        raw_classes = output_dict['detection_classes'][0].numpy().astype(int)
        num_dets = int(output_dict.get('num_detections', [len(raw_scores)])[0].numpy()) if 'num_detections' in output_dict else len(raw_scores)

        raw_detections = []
        for i in range(min(num_dets, len(raw_scores))):
            score = float(raw_scores[i])
            if score < conf_thresh:
                continue

            class_id = int(raw_classes[i])
            class_name = self.CLASS_NAMES.get(class_id, 'Crack')

            ymin_norm = float(max(0.0, min(1.0, raw_boxes[i][0])))
            xmin_norm = float(max(0.0, min(1.0, raw_boxes[i][1])))
            ymax_norm = float(max(0.0, min(1.0, raw_boxes[i][2])))
            xmax_norm = float(max(0.0, min(1.0, raw_boxes[i][3])))

            # Convert to original image pixel coordinates
            xmin_px = int(round(xmin_norm * orig_w))
            ymin_px = int(round(ymin_norm * orig_h))
            xmax_px = int(round(xmax_norm * orig_w))
            ymax_px = int(round(ymax_norm * orig_h))

            # Ensure coordinates are properly clipped within valid image boundaries
            xmin_px = max(0, min(orig_w, xmin_px))
            ymin_px = max(0, min(orig_h, ymin_px))
            xmax_px = max(0, min(orig_w, max(xmin_px, xmax_px)))
            ymax_px = max(0, min(orig_h, max(ymin_px, ymax_px)))

            # Relative area calculation
            box_width = xmax_norm - xmin_norm
            box_height = ymax_norm - ymin_norm
            relative_area = round(float(box_width * box_height), 4)

            # Visual severity for individual detection
            item_severity = self.calculate_relative_severity(relative_area)

            det_entry = {
                'class_id': class_id,
                'class_name': class_name,
                'defect_class': class_name,  # for backwards compatibility
                'confidence': round(score, 4),
                'confidence_score': round(score, 4),  # for backwards compatibility
                'bounding_box': {
                    'xmin': xmin_px,
                    'ymin': ymin_px,
                    'xmax': xmax_px,
                    'ymax': ymax_px
                },
                'normalized_box': [round(ymin_norm, 4), round(xmin_norm, 4), round(ymax_norm, 4), round(xmax_norm, 4)],
                'pixel_box': {  # for backwards compatibility
                    'ymin': ymin_px,
                    'xmin': xmin_px,
                    'ymax': ymax_px,
                    'xmax': xmax_px
                },
                'relative_area': relative_area,
                'area_ratio': relative_area,  # for backwards compatibility
                'severity': item_severity,
                'validation_status': 'valid'
            }
            raw_detections.append(det_entry)

        # Apply class-aware duplicate suppression (preserves overlapping different classes e.g. Crack + Pothole)
        detections = self.suppress_class_aware_duplicates(raw_detections, iou_threshold=nms_iou)
        cross_class_overlaps = self.detect_cross_class_overlaps(detections)
        crack_regions = self.group_crack_regions(detections)

        # Calculate canonical Relative Visual Severity Index (RVSI) over cleaned detections
        rvsi_res = severity_service.calculate_rvsi(
            detections,
            image_width=orig_w,
            image_height=orig_h
        )

        # Attach item-level RVSI details to each preserved detection
        for d in detections:
            d['rvsi_score'] = severity_service.calculate_rvsi([d], image_width=orig_w, image_height=orig_h)['rvsi_score']

        # Handle zero detections or aggregate assessment
        if detections:
            primary = detections[0]
            primary_class_id = primary['class_id']
            primary_class_name = primary['class_name']
            primary_confidence = primary['confidence']
            primary_box_px = primary['bounding_box']
            primary_box_norm = primary['normalized_box']

            # Unique detected defect classes across all preserved detections
            detected_classes = list(dict.fromkeys(d['class_name'] for d in detections))
            overall_severity = rvsi_res['relative_severity']
            effective_area = rvsi_res['area_extent']
            area_percentage = round(effective_area * 100.0, 2)
        else:
            primary_class_id = None
            primary_class_name = 'None Detected'
            primary_confidence = 0.0
            primary_box_px = None
            primary_box_norm = [0.0, 0.0, 0.0, 0.0]
            overall_severity = 'Low'
            area_percentage = 0.0
            detected_classes = []
            effective_area = 0.0

        return {
            'model_name': self.model_name,
            'model_version': self.model_version,
            'threshold_applied': conf_thresh,
            'score_threshold': conf_thresh,
            'iou_threshold_applied': nms_iou,
            'nms_iou_threshold': nms_iou,
            'postprocessing_version': severity_service.POSTPROCESSING_VERSION,
            'class_id': primary_class_id,
            'class_name': primary_class_name,
            'defect_class': primary_class_name,  # for backwards compatibility
            'detected_classes': detected_classes,
            'confidence': primary_confidence,
            'confidence_score': primary_confidence,  # for backwards compatibility
            'bounding_box': primary_box_norm,  # normalized [ymin, xmin, ymax, xmax] for backwards compatibility
            'bounding_box_pixels': primary_box_px,
            'relative_severity': overall_severity,
            'severity': overall_severity,
            'rvsi_score': rvsi_res['rvsi_score'],
            'area_extent': rvsi_res['area_extent'],
            'spatial_span': rvsi_res['spatial_span'],
            'multiplicity': rvsi_res['multiplicity'],
            'rvsi': rvsi_res,
            'rvsi_method': rvsi_res['rvsi_method'],
            'rvsi_version': rvsi_res['rvsi_version'],
            'severity_threshold_source': rvsi_res['severity_threshold_source'],
            'relative_area': effective_area,
            'area_ratio': effective_area,  # for backwards compatibility
            'area_percentage': area_percentage,
            'detections': detections,
            'cross_class_overlaps': cross_class_overlaps,
            'crack_regions': crack_regions,
            'raw_detection_count': len(raw_detections),
            'cleaned_detection_count': len(detections),
            'suppressed_count': len(raw_detections) - len(detections),
            'image_dimensions': {'width': orig_w, 'height': orig_h},
            'disclaimer': severity_service.RVSI_DISCLAIMER
        }


# Global singleton instance loaded once at application/service startup
inference_service = InferenceService()

__all__ = ['InferenceService', 'inference_service']
