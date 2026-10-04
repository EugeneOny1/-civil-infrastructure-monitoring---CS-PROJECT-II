"""
Forwarding shim for relative severity service.
Points directly to backend.app.services.severity.
"""
from .severity import SeverityService, severity_service

__all__ = ['SeverityService', 'severity_service']

