from .database import db_service, DatabaseService
from .inference import inference_service, InferenceService
from .validation import validation_service, ValidationService
from .severity import severity_service, SeverityService

# Backwards compatibility aliases
ai_model = inference_service
AIModel = InferenceService

__all__ = [
    'db_service',
    'DatabaseService',
    'inference_service',
    'InferenceService',
    'validation_service',
    'ValidationService',
    'severity_service',
    'SeverityService',
    'ai_model',
    'AIModel'
]

