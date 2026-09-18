# Exported Machine Learning Models

Place your trained weights and exported model graphs exported from Google Colab in this directory:

- `ssd_mobilenet_v2.tflite` (Recommended for lightweight, fast CPU inference on the Flask backend)
- `saved_model/` (TensorFlow SavedModel directory exported by `exporter_main_v2.py`)
- `checkpoint/` (Model checkpoints saved during fine-tuning)

When model files are placed in this folder, the backend's `ai_service.py` (`AIModel` class) automatically detects them and switches from development simulation to live inference.
