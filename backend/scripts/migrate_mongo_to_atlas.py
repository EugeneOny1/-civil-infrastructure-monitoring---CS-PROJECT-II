"""
Non-destructive, idempotent MongoDB to MongoDB Atlas audit and migration utility.

Usage:
  1. Dry-run audit (read-only, default):
     python backend/scripts/migrate_mongo_to_atlas.py --target-uri "mongodb+srv://..."

  2. Safe non-destructive migration (inserts missing documents via $setOnInsert):
     python backend/scripts/migrate_mongo_to_atlas.py --target-uri "mongodb+srv://..." --execute

Notes:
  - Preserves existing local MongoDB records untouched.
  - Preserves any existing records already present in MongoDB Atlas unless --overwrite is explicitly set.
  - Never prints credentials from MongoDB connection strings.
"""

import argparse
import os
import sys
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

from pymongo import ASCENDING, DESCENDING, MongoClient, ReplaceOne, UpdateOne

CORE_COLLECTIONS: Tuple[str, ...] = (
    'users',
    'infrastructure_assets',
    'infrastructure_reports',
    'submitted_images',
    'ai_assessments',
    'professional_reviews',
    'safety_advisories',
    'citizen_notifications',
    'system_state',
)

OPTIONAL_COLLECTIONS: Tuple[str, ...] = (
    'archived_test_reports',
    'archived_test_submitted_images',
    'archived_test_ai_assessments',
    'weather_cache',
)


def redact_uri(uri: str) -> str:
    """Returns a credential-free host/database representation of a MongoDB URI."""
    if not uri:
        return '<empty>'
    if '@' in uri:
        scheme = uri.split('://', 1)[0] if '://' in uri else 'mongodb'
        return f'{scheme}://***@{uri.split("@", 1)[1]}'
    parts = urlsplit(uri)
    return f'{parts.scheme}://{parts.netloc}{parts.path}' if parts.scheme else uri


def inspect_collections(
    source_db,
    target_db,
    collections: Iterable[str],
) -> List[Dict[str, object]]:
    """Collects non-destructive document counts for source and target databases."""
    source_existing = set(source_db.list_collection_names())
    target_existing = set(target_db.list_collection_names()) if target_db is not None else set()
    rows: List[Dict[str, object]] = []
    for name in collections:
        src_count = source_db[name].count_documents({}) if name in source_existing else 0
        tgt_count = (
            target_db[name].count_documents({})
            if target_db is not None and name in target_existing
            else 0
        )
        rows.append({
            'collection': name,
            'source_count': src_count,
            'target_count': tgt_count,
        })
    return rows


def migrate_collection(
    source_col,
    target_col,
    overwrite: bool = False,
    batch_size: int = 200,
) -> Dict[str, int]:
    """Copies documents from source_col to target_col without overwriting by default."""
    stats = {'examined': 0, 'inserted': 0, 'updated': 0, 'skipped_existing': 0}
    ops = []

    def _flush():
        if not ops:
            return
        res = target_col.bulk_write(ops, ordered=False)
        stats['inserted'] += int(res.upserted_count)
        if overwrite:
            stats['updated'] += int(res.modified_count)
        else:
            stats['skipped_existing'] += max(0, len(ops) - int(res.upserted_count))
        ops.clear()

    for doc in source_col.find({}):
        stats['examined'] += 1
        if overwrite:
            ops.append(ReplaceOne({'_id': doc['_id']}, doc, upsert=True))
        else:
            ops.append(UpdateOne({'_id': doc['_id']}, {'$setOnInsert': doc}, upsert=True))
        if len(ops) >= batch_size:
            _flush()

    _flush()
    return stats


def ensure_production_indexes(target_db) -> None:
    """Ensures required production query indexes exist on Atlas."""
    target_db['users'].create_index([('email', ASCENDING)], unique=True)
    target_db['infrastructure_reports'].create_index([('user_id', ASCENDING)])
    target_db['infrastructure_reports'].create_index([('date_submitted', DESCENDING)])


def run_migration(
    source_uri: str,
    target_uri: Optional[str],
    db_name: str,
    execute: bool = False,
    include_archived: bool = False,
    overwrite: bool = False,
) -> int:
    collections = list(CORE_COLLECTIONS)
    if include_archived:
        collections.extend(OPTIONAL_COLLECTIONS)

    src_client = MongoClient(source_uri, serverSelectionTimeoutMS=5000)
    src_client.admin.command('ping')
    src_db = src_client[db_name]

    tgt_client = None
    tgt_db = None
    if target_uri:
        tgt_client = MongoClient(target_uri, serverSelectionTimeoutMS=8000)
        tgt_client.admin.command('ping')
        tgt_db = tgt_client[db_name]

    print(f"Source MongoDB : {redact_uri(source_uri)} (db={db_name})")
    print(f"Target Atlas   : {redact_uri(target_uri) if target_uri else '<dry-run: no target supplied>'} (db={db_name})")
    print(f"Mode           : {'EXECUTE (non-destructive $setOnInsert)' if execute and not overwrite else 'EXECUTE (overwrite enabled)' if execute else 'DRY-RUN AUDIT'}")
    print("-" * 72)

    rows = inspect_collections(src_db, tgt_db, collections)
    for row in rows:
        print(f"  {row['collection']:<32} source={row['source_count']:<5} target={row['target_count']}")

    if not execute:
        print("-" * 72)
        print("Dry-run complete. No documents were modified.")
        return 0

    if tgt_db is None:
        print("ERROR: --target-uri (or ATLAS_MONGO_URI) is required with --execute.", file=sys.stderr)
        return 1

    if 'localhost' in (target_uri or '') or '127.0.0.1' in (target_uri or ''):
        print("ERROR: Refusing --execute against a localhost target URI.", file=sys.stderr)
        return 1

    print("-" * 72)
    for row in rows:
        col_name = str(row['collection'])
        if int(row['source_count']) == 0:
            continue
        res = migrate_collection(src_db[col_name], tgt_db[col_name], overwrite=overwrite)
        print(
            f"  Migrated {col_name:<30} examined={res['examined']} "
            f"inserted={res['inserted']} updated={res['updated']} skipped_existing={res['skipped_existing']}"
        )

    ensure_production_indexes(tgt_db)
    print("[OK] Ensured production MongoDB indexes.")

    print("-" * 72)
    print("Post-migration count verification:")
    post_rows = inspect_collections(src_db, tgt_db, collections)
    for row in post_rows:
        print(f"  {row['collection']:<32} source={row['source_count']:<5} target={row['target_count']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-destructive local MongoDB to MongoDB Atlas migration tool.")
    parser.add_argument('--source-uri', default=os.getenv('MONGO_URI', 'mongodb://localhost:27017/civil_infrastructure'))
    parser.add_argument('--target-uri', default=os.getenv('ATLAS_MONGO_URI', os.getenv('TARGET_MONGO_URI', '')))
    parser.add_argument('--db-name', default=os.getenv('DB_NAME', 'civil_infrastructure'))
    parser.add_argument('--execute', action='store_true', help='Perform non-destructive migration (default is dry-run audit).')
    parser.add_argument('--include-archived', action='store_true', help='Also include archived_test_* and weather_cache collections.')
    parser.add_argument('--overwrite', action='store_true', help='Replace existing target documents with matching _id (default skips existing).')
    args = parser.parse_args()
    return run_migration(
        source_uri=args.source_uri,
        target_uri=args.target_uri.strip() or None,
        db_name=args.db_name,
        execute=args.execute,
        include_archived=args.include_archived,
        overwrite=args.overwrite,
    )


if __name__ == '__main__':
    raise SystemExit(main())

