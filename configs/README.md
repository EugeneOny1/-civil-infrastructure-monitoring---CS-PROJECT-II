# Model Training & Pipeline Configurations

This directory stores configuration files for the TensorFlow Object Detection pipeline:

- `ssd_mobilenet_v2_pipeline.config`: The pipeline configuration specifying:
  - Input resolution: 300x300 (or 640x640)
  - Backbone: MobileNetV2
  - Number of defect classes: 3 (`Crack`, `Pothole`, `Surface Deterioration`)
  - Label map: `label_map.pbtxt`
  - Optimizer: Momentum / Adam with cosine decay learning rate
  - Data augmentation: Random horizontal/vertical flip, contrast adjustment, brightness normalization.
