"""
Database Migration Script:
Idempotent migration to align all infrastructure reports with canonical lifecycle:
Received -> Verified -> Under Review -> Resolved
And ensure lead engineer accountability and inspection notebook initialization.
"""

import os
import sys
from datetime import datetime, timezone

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.app.services.database import db_service
from backend.app.models.report import InfrastructureReport
from backend.app.routes.reviews import get_default_notebook_template

def run_migration():
    print("[Migration] Starting lifecycle and engineer accountability migration...")
    
    # Locate default verified engineer (Eng. Regina)
    users = db_service.find('users')
    regina = None
    default_eng = None
    for u in users:
        if 'regina' in u.get('email', '').lower() or 'regina' in u.get('name', '').lower():
            regina = u
        if u.get('role') == 'engineer' and not default_eng:
            default_eng = u
            
    lead_user = regina or default_eng or {
        '_id': 'usr_eng_regina',
        'name': 'Eng.Regina',
        'email': 'regina@kenha.co.ke'
    }
    lead_id = str(lead_user.get('_id') or lead_user.get('user_id'))
    lead_name = lead_user.get('name', 'Eng.Regina')
    lead_email = lead_user.get('email', 'regina@kenha.co.ke')

    reports = db_service.find('infrastructure_reports')
    print(f"[Migration] Found {len(reports)} infrastructure reports.")

    updated_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for rep in reports:
        rep_id = rep['_id']
        raw_status = rep.get('status')
        canonical = InfrastructureReport.normalize_lifecycle_status(raw_status)
        meta = rep.get('metadata') or {}
        changed = False

        if rep.get('status') != canonical:
            changed = True

        # Assign lead and notebook if verified, under review, or resolved
        if canonical in [InfrastructureReport.STATUS_VERIFIED, InfrastructureReport.STATUS_UNDER_REVIEW, InfrastructureReport.STATUS_RESOLVED]:
            if not meta.get('original_verifying_engineer'):
                meta['original_verifying_engineer'] = {
                    'user_id': lead_id,
                    'name': lead_name,
                    'email': lead_email,
                    'verified_at': meta.get('assigned_at') or rep.get('created_at') or now_iso
                }
                changed = True

            if not meta.get('current_lead_engineer'):
                meta['current_lead_engineer'] = {
                    'user_id': lead_id,
                    'name': lead_name,
                    'email': lead_email,
                    'assigned_at': meta.get('assigned_at') or rep.get('created_at') or now_iso
                }
                changed = True

            if not meta.get('assigned_engineer_id'):
                meta['assigned_engineer_id'] = lead_id
                meta['assigned_engineer_name'] = lead_name
                meta['assigned_engineer_email'] = lead_email
                changed = True

            if 'collaborators' not in meta:
                meta['collaborators'] = []
                changed = True

            if not meta.get('inspection_notebook') or not meta['inspection_notebook'].get('checklist'):
                meta['inspection_notebook'] = get_default_notebook_template(rep.get('asset_type') or meta.get('asset_type'))
                changed = True

        if changed:
            db_service.update_one('infrastructure_reports', {'_id': rep_id}, {
                'status': canonical,
                'metadata': meta,
                'last_updated_at': now_iso
            })
            updated_count += 1

    print(f"[Migration] Successfully migrated {updated_count} reports.")

if __name__ == '__main__':
    run_migration()

