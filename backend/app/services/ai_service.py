"""
Forwarding shim for AI model / inference service.
Consolidated into backend.app.services.inference.
"""
from .inference import InferenceService, inference_service

AIModel = InferenceService
ai_model = inference_service

__all__ = ['AIModel', 'ai_model', 'InferenceService', 'inference_service']
