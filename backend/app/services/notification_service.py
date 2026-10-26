"""
Notification Service for Citizen Report Feedback & Engineer Audit Trail
-----------------------------------------------------------------------
Generates concise, meaningful report lifecycle notifications for citizens:
- Engineer verification
- Engineer defect classification override
- Engineer severity modification
- Engineer review feedback / advisory notes
- Defect report resolution
"""

import uuid
from datetime import datetime, timezone
from .database import db_service

class NotificationService:
    @staticmethod
    def create_notification(user_id: str, report_id: str, event_type: str, title: str, message: str) -> dict:
        """
        Creates and stores a targeted notification for a citizen reporter.
        """
        if not user_id:
            return None

        notif_id = f"notif_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        doc = {
            '_id': notif_id,
            'notification_id': notif_id,
            'user_id': str(user_id),
            'report_id': str(report_id),
            'event_type': str(event_type),
            'title': str(title),
            'message': str(message).strip(),
            'is_read': False,
            'created_at': now_iso
        }

        db_service.insert('citizen_notifications', doc)
        return doc

    @staticmethod
    def get_user_notifications(user_id: str, unread_only: bool = False) -> list:
        """
        Retrieves notifications for a specific user ordered by newest first.
        """
        if not user_id:
            return []

        query = {'user_id': str(user_id)}
        if unread_only:
            query['is_read'] = False

        return db_service.find('citizen_notifications', query, sort_key='created_at', reverse=True)

    @staticmethod
    def mark_as_read(user_id: str, notification_id: str) -> bool:
        """
        Marks an individual notification as read.
        """
        query = {'_id': str(notification_id), 'user_id': str(user_id)}
        existing = db_service.find_one('citizen_notifications', query)
        if not existing:
            # Also try notification_id field
            query = {'notification_id': str(notification_id), 'user_id': str(user_id)}
            existing = db_service.find_one('citizen_notifications', query)

        if existing:
            db_service.update_one('citizen_notifications', {'_id': existing['_id']}, {'is_read': True})
            return True
        return False

    @staticmethod
    def mark_all_as_read(user_id: str) -> int:
        """
        Marks all unread notifications for a user as read.
        """
        if not user_id:
            return 0
        res = db_service.db['citizen_notifications'].update_many(
            {'user_id': str(user_id), 'is_read': False},
            {'$set': {'is_read': True}}
        )
        return res.modified_count

notification_service = NotificationService()
