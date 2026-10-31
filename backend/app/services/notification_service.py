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
    def create_notification(user_id: str, report_id: str, event_type: str, title: str, message: str, metadata: dict = None) -> dict:
        """
        Creates and stores a targeted notification for a user.
        """
        if not user_id:
            return None

        notif_id = f"notif_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        doc = {
            '_id': notif_id,
            'notification_id': notif_id,
            'user_id': str(user_id),
            'report_id': str(report_id) if report_id else None,
            'event_type': str(event_type),
            'title': str(title),
            'message': str(message).strip(),
            'is_read': False,
            'created_at': now_iso,
            'metadata': metadata or {}
        }

        db_service.insert('citizen_notifications', doc)
        return doc

    @staticmethod
    def broadcast_notification(audience: str, title: str, message: str, sender_id: str = None, report_id: str = None, event_type: str = 'system_announcement', metadata: dict = None) -> int:
        """
        Dispatches an operational notification to active users matching the target audience.
        Audience options: 'all', 'citizen', 'engineer', 'admin'.
        """
        user_query = {'is_active': {'$ne': False}}
        if audience and audience.lower() != 'all':
            aud = audience.lower().rstrip('s')
            user_query['role'] = aud

        target_users = db_service.find('users', user_query)
        if not target_users:
            return 0

        now_iso = datetime.now(timezone.utc).isoformat()
        docs = []
        for u in target_users:
            u_id = str(u.get('_id') or u.get('user_id'))
            if not u_id:
                continue
            notif_id = f"notif_{uuid.uuid4().hex[:12]}"
            docs.append({
                '_id': notif_id,
                'notification_id': notif_id,
                'user_id': u_id,
                'report_id': str(report_id) if report_id else None,
                'event_type': str(event_type),
                'title': str(title),
                'message': str(message).strip(),
                'is_read': False,
                'created_at': now_iso,
                'sender_id': str(sender_id) if sender_id else None,
                'metadata': metadata or {}
            })

        if docs:
            db_service.db['citizen_notifications'].insert_many(docs)
        return len(docs)

    @staticmethod
    def create_safety_advisory(advisory_doc: dict) -> dict:
        """
        Stores an Engineer-issued Safety Advisory and notifies citizens & engineers.
        """
        advisory_id = advisory_doc.get('advisory_id') or f"adv_{uuid.uuid4().hex[:10]}"
        advisory_doc['_id'] = advisory_id
        advisory_doc['advisory_id'] = advisory_id

        db_service.insert('safety_advisories', advisory_doc)

        report_id = advisory_doc.get('report_id')
        category = advisory_doc.get('category', 'Safety Advisory')
        location = advisory_doc.get('location_name', 'Monitored Infrastructure')
        note = advisory_doc.get('professional_note', '')
        eng_name = advisory_doc.get('issued_by_name', 'Civil Engineer')

        title = f"⚠️ Safety Advisory: {category}"
        msg = f"Defect at {location}: {category}. {note if note else 'Exercise caution in the affected vicinity.'} (Issued by {eng_name})"

        # Broadcast advisory to active citizens and engineers
        NotificationService.broadcast_notification(
            audience='all',
            title=title,
            message=msg,
            sender_id=advisory_doc.get('issued_by_id'),
            report_id=report_id,
            event_type='safety_advisory',
            metadata={'category': category, 'location': location, 'advisory_id': advisory_id}
        )
        return advisory_doc

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
