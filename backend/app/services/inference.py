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
    DEFAULT_MODEL_VERSION = 'ssd_mobilenet_v2_lr00125_step5000_v1'
    DEFAULT_MODEL_NAME = 'SSD-MobileNetV2'

    # Prototype visual severity thresholds (relative bounding box area to image area)
    SEVERITY_LOW_THRESHOLD = 0.05       # < 5%
    SEVERITY_CRITICAL_THRESHOLD = 0.15 # >= 15%

    def __init__(self, model_path=None, confidence_threshold=None, model_version=None):
        self.model_name = self.DEFAULT_MODEL_NAME
        self.model_version = model_version or os.getenv('MODEL_VERSION', self.DEFAULT_MODEL_VERSION)
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else float(os.getenv('DETECTION_CONFIDENCE_THRESHOLD', str(self.DEFAULT_CONFIDENCE_THRESHOLD)))
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

            if 'serving_default' in loaded_model.signatures:
                self.serving_fn = loaded_model.signatures['serving_default']
            else:
                sig_keys = list(loaded_model.signatures.keys())
                if sig_keys:
                    self.serving_fn = loaded_model.signatures[sig_keys[0]]
                else:
                    self.serving_fn = loaded_model

            self.is_loaded = True
            self.load_error = None
            print("[InferenceService] Structural defect SavedModel loaded successfully.")
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
        Prototype visual severity heuristic based on detected bounding-box area extent.
        Documented: "Relative visual severity based on detected bounding-box area."
        It is NOT:
        - structural integrity certification
        - structural failure probability
        - engineering safety assessment
        - model confidence
        """
        low_t = low_thresh if low_thresh is not None else cls.SEVERITY_LOW_THRESHOLD
        crit_t = critical_thresh if critical_thresh is not None else cls.SEVERITY_CRITICAL_THRESHOLD

        if relative_area >= crit_t:
            return 'Critical'
        elif relative_area >= low_t:
            return 'Moderate'
        else:
            return 'Low'

    def detect_defects(self, image_input, confidence_threshold=None):
        """
        Executes structural defect detection using the loaded TensorFlow SavedModel.
        
        Args:
            image_input: File path, file-like object, or NumPy RGB array.
            confidence_threshold: Optional override for detection confidence threshold.

        Returns:
            Dictionary containing primary defect summary, full detections list,
            pixel coordinates, relative visual severity, and metadata.
        """
        if not self.is_loaded or self.serving_fn is None:
            err = self.load_error or "SavedModel is not loaded."
            raise RuntimeError(f"Defect detector SavedModel is unavailable: {err}")

        conf_thresh = (
            confidence_threshold
            if confidence_threshold is not None
            else self.confidence_threshold
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

        detections = []
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
            detections.append(det_entry)

        # Handle zero detections or aggregate assessment
        if detections:
            primary = detections[0]
            primary_class_id = primary['class_id']
            primary_class_name = primary['class_name']
            primary_confidence = primary['confidence']
            primary_box_px = primary['bounding_box']
            primary_box_norm = primary['normalized_box']

            # Cumulative area extent for overall image
            total_relative_area = min(1.0, sum(d['relative_area'] for d in detections))
            overall_severity = self.calculate_relative_severity(total_relative_area)
            area_percentage = round(total_relative_area * 100.0, 2)
        else:
            primary_class_id = None
            primary_class_name = 'None Detected'
            primary_confidence = 0.0
            primary_box_px = None
            primary_box_norm = [0.0, 0.0, 0.0, 0.0]
            total_relative_area = 0.0
            overall_severity = 'Low'
            area_percentage = 0.0

        return {
            'model_name': self.model_name,
            'model_version': self.model_version,
            'threshold_applied': conf_thresh,
            'class_id': primary_class_id,
            'class_name': primary_class_name,
            'defect_class': primary_class_name,  # for backwards compatibility
            'confidence': primary_confidence,
            'confidence_score': primary_confidence,  # for backwards compatibility
            'bounding_box': primary_box_norm,  # normalized [ymin, xmin, ymax, xmax] for backwards compatibility
            'bounding_box_pixels': primary_box_px,
            'relative_severity': overall_severity,
            'severity': overall_severity,
            'relative_area': total_relative_area,
            'area_percentage': area_percentage,
            'detections': detections,
            'image_dimensions': {'width': orig_w, 'height': orig_h},
            'disclaimer': (
                "Relative visual severity based on detected bounding-box area. "
                "Automated preliminary estimate subject to certified civil engineer review."
            )
        }


# Global singleton instance loaded once at application/service startup
inference_service = InferenceService()

__all__ = ['InferenceService', 'inference_service']
