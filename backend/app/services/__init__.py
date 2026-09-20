from .database import db_service, DatabaseService
from .inference import inference_service, InferenceService

# Backwards compatibility aliases
ai_model = inference_service
AIModel = InferenceService

__all__ = [
    'db_service',
    'DatabaseService',
    'inference_service',
    'InferenceService',
    'ai_model',
    'AIModel'
]
