"""
Data Isolation Script for Infrastructure Reports and Dependent Documents.
Archives 62 clearly identified synthetic automated-test duplicate reports and their
associated submitted_images, ai_assessments, and review records into dedicated archive collections:
- archived_test_reports
- archived_test_submitted_images
- archived_test_ai_assessments
- archived_test_professional_reviews

Preserves all 27 legitimate reports and 4 canonical baseline test scenarios (31 total reports) intact.
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.services.database import db_service

LEGITIMATE_REPORT_IDS = {
    'REP-2026-0001',                            # Canonical seed report
    '8a4810bb-4114-41b2-870d-f43c52bebb1d',    # User report - Waiyaki Way
    '9a2fae3f-f756-4c3c-ab0a-7d352cbd42df',    # User report - Waiyaki Way
    '42ce53c9-b701-47e8-8e34-7d21a838a5c4',    # User report - Ole Sangale Rd
    '936465c0-458f-4950-b5c1-5bbdb0cafbd5',    # User report - Kenyatta Avenue
    '3d679229-0c8f-4522-8b8f-bc2625dcbe82',    # User report - Harambee Avenue
    'c5f1920c-67b5-4674-951f-7393bc6bb6d4',    # Tag Location verification report
}

BASELINE_TEST_SCENARIOS = {
    '03f79869-ea41-4af7-a2ef-c6e8f601a228',    # Baseline test defect submission
    'f39e21a1-fe46-47bb-a31a-d3013aefbd43',    # Baseline unusual pairing test
    '076f20fa-8a36-48f8-bdde-753b1c3b60cf',    # Baseline clean surface test
    'ce95f9b5-8bc6-49e9-affd-e18407445019',    # Baseline engineer survey test
}

def run_archive_isolation(dry_run=False):
    db = db_service.db
    if db is None:
        raise RuntimeError("Failed to connect to MongoDB.")

    all_reports = list(db['infrastructure_reports'].find({}))
    total_count = len(all_reports)

    legitimate = []
    baseline_tests = []
    cleanup_set = []

    for r in all_reports:
        rid = str(r.get('_id'))
        if rid in LEGITIMATE_REPORT_IDS:
            legitimate.append(r)
        elif rid in BASELINE_TEST_SCENARIOS:
            baseline_tests.append(r)
        else:
            desc = r.get('description', '')
            uid = r.get('user_id', '')
            # Match specifically the synthetic automated test loop duplicates
            if uid == 'usr_cit_01' and any(s in desc for s in ['Integration test defect submission', 'Unusual defect pairing test', 'Clean surface test']):
                cleanup_set.append(r)
            else:
                # Retain as legitimate
                legitimate.append(r)

    print("==================================================================")
    print(f"DRY-RUN RECONCILIATION AUDIT (Database: {db.name})")
    print("==================================================================")
    print(f"Total reports currently in active collection: {total_count}")
    print(f"Legitimate reports to retain:                 {len(legitimate)}")
    print(f"Baseline test scenarios to retain:            {len(baseline_tests)}")
    print(f"Total reports retained:                       {len(legitimate) + len(baseline_tests)}")
    print(f"Synthetic test duplicates to archive:         {len(cleanup_set)}")
    print("==================================================================")

    # Verification checks
    if total_count != 93:
        raise ValueError(f"Aborting: Expected exactly 93 reports, but found {total_count}.")
    if len(cleanup_set) != 62:
        raise ValueError(f"Aborting: Expected exactly 62 cleanup duplicates, but identified {len(cleanup_set)}.")
    if len(legitimate) + len(baseline_tests) != 31:
        raise ValueError(f"Aborting: Expected exactly 31 retained reports, but identified {len(legitimate) + len(baseline_tests)}.")

    cleanup_ids = [str(r['_id']) for r in cleanup_set]
    
    # Identify dependent records
    matching_images = list(db['submitted_images'].find({'report_id': {'$in': cleanup_ids}}))
    matching_image_ids = [str(img['_id']) for img in matching_images]

    matching_assessments = list(db['ai_assessments'].find({
        '$or': [
            {'report_id': {'$in': cleanup_ids}},
            {'image_id': {'$in': matching_image_ids}}
        ]
    }))

    matching_reviews = list(db['professional_reviews'].find({'report_id': {'$in': cleanup_ids}}))

    print("DEPENDENT RECORDS IDENTIFIED:")
    print(f"  - submitted_images:    {len(matching_images)}")
    print(f"  - ai_assessments:      {len(matching_assessments)}")
    print(f"  - professional_reviews:{len(matching_reviews)}")
    print("==================================================================")

    if dry_run:
        print("Dry run complete. No modifications made.")
        return

    print("EXECUTING ARCHIVE ISOLATION...")
    archive_timestamp = datetime.now(timezone.utc).isoformat()

    # 1. Archive & remove reports
    for doc in cleanup_set:
        archived_doc = dict(doc)
        archived_doc['_archived_at'] = archive_timestamp
        archived_doc['_archive_reason'] = 'automated_integration_test_duplicate'
        db['archived_test_reports'].replace_one({'_id': doc['_id']}, archived_doc, upsert=True)
    del_rep_res = db['infrastructure_reports'].delete_many({'_id': {'$in': [r['_id'] for r in cleanup_set]}})
    print(f"  -> Moved {del_rep_res.deleted_count} reports to 'archived_test_reports'")

    # 2. Archive & remove submitted_images
    if matching_images:
        for doc in matching_images:
            archived_doc = dict(doc)
            archived_doc['_archived_at'] = archive_timestamp
            archived_doc['_archive_reason'] = 'automated_integration_test_duplicate'
            db['archived_test_submitted_images'].replace_one({'_id': doc['_id']}, archived_doc, upsert=True)
        del_img_res = db['submitted_images'].delete_many({'_id': {'$in': [img['_id'] for img in matching_images]}})
        print(f"  -> Moved {del_img_res.deleted_count} images to 'archived_test_submitted_images'")

    # 3. Archive & remove ai_assessments
    if matching_assessments:
        for doc in matching_assessments:
            archived_doc = dict(doc)
            archived_doc['_archived_at'] = archive_timestamp
            archived_doc['_archive_reason'] = 'automated_integration_test_duplicate'
            db['archived_test_ai_assessments'].replace_one({'_id': doc['_id']}, archived_doc, upsert=True)
        del_ass_res = db['ai_assessments'].delete_many({'_id': {'$in': [ass['_id'] for ass in matching_assessments]}})
        print(f"  -> Moved {del_ass_res.deleted_count} assessments to 'archived_test_ai_assessments'")

    # 4. Archive & remove professional_reviews (if any)
    if matching_reviews:
        for doc in matching_reviews:
            archived_doc = dict(doc)
            archived_doc['_archived_at'] = archive_timestamp
            archived_doc['_archive_reason'] = 'automated_integration_test_duplicate'
            db['archived_test_professional_reviews'].replace_one({'_id': doc['_id']}, archived_doc, upsert=True)
        del_rev_res = db['professional_reviews'].delete_many({'_id': {'$in': [rev['_id'] for rev in matching_reviews]}})
        print(f"  -> Moved {del_rev_res.deleted_count} reviews to 'archived_test_professional_reviews'")

    # Final post-cleanup verification
    remaining_reports = list(db['infrastructure_reports'].find({}))
    remaining_count = len(remaining_reports)
    remaining_ids = set(str(r['_id']) for r in remaining_reports)

    print("==================================================================")
    print("POST-CLEANUP VERIFICATION AUDIT")
    print("==================================================================")
    print(f"Active report count before: {total_count}")
    print(f"Active report count after:  {remaining_count}")
    print(f"Archived reports count:     {len(cleanup_ids)}")
    print(f"Archived in DB collection:  {db['archived_test_reports'].count_documents({})}")

    # Verify all 31 expected retained IDs exist
    expected_retained_ids = set(str(r['_id']) for r in (legitimate + baseline_tests))
    missing = expected_retained_ids - remaining_ids
    if missing:
        raise RuntimeError(f"ALERT: Missing expected retained reports: {missing}")
    print(f"ALL {len(expected_retained_ids)} RETAINED REPORTS ARE INTACT AND ACCOUNTED FOR.")

    # Verify none of the archived IDs exist in active reports
    leaked = set(cleanup_ids).intersection(remaining_ids)
    if leaked:
        raise RuntimeError(f"ALERT: Cleanup IDs still found in active reports: {leaked}")
    print("ZERO DUPLICATE REPORT LEAKAGE: All 62 archived IDs successfully removed from active collection.")

    # Save exact archived IDs to JSON for auditable verification
    out_file = BASE_DIR / 'scripts' / 'archived_test_report_ids.json'
    with open(out_file, 'w') as f:
        json.dump({
            'archived_at': archive_timestamp,
            'total_archived': len(cleanup_ids),
            'archived_report_ids': cleanup_ids,
            'active_before': total_count,
            'active_after': remaining_count,
            'retained_legitimate_count': len(legitimate),
            'retained_baseline_count': len(baseline_tests)
        }, f, indent=2)
    print(f"Saved auditable list of 62 archived report IDs to: {out_file}")

    print("\nEXACT 62 ARCHIVED REPORT IDS:")
    for idx, rid in enumerate(cleanup_ids, start=1):
        print(f"  {idx:02d}. {rid}")
    print("==================================================================")

if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    run_archive_isolation(dry_run=dry_run)
