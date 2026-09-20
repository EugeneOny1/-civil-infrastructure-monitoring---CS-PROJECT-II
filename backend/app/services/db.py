"""
Forwarding shim for database service.
Consolidated into backend.app.services.database.
"""
from .database import DatabaseService, db_service

__all__ = ['DatabaseService', 'db_service']
