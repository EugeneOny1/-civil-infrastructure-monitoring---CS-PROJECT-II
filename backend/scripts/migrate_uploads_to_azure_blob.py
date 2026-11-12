"""
Non-destructive, idempotent historical report image audit and Azure Blob migration utility.

Determines which files in local upload directories are referenced by real MongoDB
infrastructure_reports / submitted_images records vs sample seed images vs
unreferenced temporary/test duplicates, and migrates ONLY required evidence images
to private Azure Blob Storage under 'reports/<filename>' without altering DB
references or deleting local files.

Usage:
  1. Dry-run classification audit (default, read-only):
     python backend/scripts/migrate_uploads_to_azure_blob.py

  2. Migrate DB-referenced evidence images non-destructively:
     python backend/scripts/migrate_uploads_to_azure_blob.py --execute \
       --azure-account-url https://<account>.blob.core.windows.net

  3. Include sample seed_* images (equivalent to -SyncSeedImages):
     python backend/scripts/migrate_uploads_to_azure_blob.py --execute --include-seed \
       --azure-account-url https://<account>.blob.core.windows.net
"""

import argparse
import mimetypes
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PRIMARY_UPLOADS = REPO_ROOT / 'backend' / 'uploads'
DEFAULT_SECONDARY_UPLOADS = REPO_ROOT / 'uploads'


def extract_image_filenames(obj) -> Set[str]:
    """Recursively extracts unique image filenames referenced by MongoDB report/image records."""
    names: Set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ('filename', 'image_path', 'image_url', 'url', 'file_path', 'annotated_image_path') and isinstance(value, str) and value.strip():
                names.add(Path(value.split('?')[0]).name)
            else:
                names.update(extract_image_filenames(value))
    elif isinstance(obj, list):
        for item in obj:
            names.update(extract_image_filenames(item))
    return names


def collect_db_referenced_filenames(mongo_uri: str, db_name: str) -> Set[str]:
    """Queries infrastructure_reports and submitted_images for all referenced image filenames."""
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client[db_name]
    reports = list(db['infrastructure_reports'].find({}, {'_id': 1, 'image_path': 1, 'image_url': 1, 'images': 1, 'metadata': 1}))
    submitted = list(db['submitted_images'].find({}, {'_id': 1, 'image_path': 1, 'url': 1}))
    return extract_image_filenames(reports) | extract_image_filenames(submitted)


def classify_local_uploads(
    referenced_names: Set[str],
    primary_dir: Path = DEFAULT_PRIMARY_UPLOADS,
    secondary_dir: Optional[Path] = DEFAULT_SECONDARY_UPLOADS,
) -> Dict[str, object]:
    """
    Classifies local files into:
    - migration_candidates: DB-referenced filenames resolved on disk (primary preferred over secondary)
    - seed_files: sample 'seed_*' files
    - unreferenced_files: temporary, test, or duplicate local files excluded from migration
    - missing_from_disk: DB-referenced filenames not found locally
    """
    primary_files = {p.name: p for p in primary_dir.iterdir() if p.is_file()} if primary_dir.is_dir() else {}
    secondary_files = {p.name: p for p in secondary_dir.iterdir() if p.is_file()} if secondary_dir and secondary_dir.is_dir() else {}

    migration_candidates: Dict[str, Path] = {}
    missing_from_disk: List[str] = []

    for fname in sorted(referenced_names):
        if fname in primary_files:
            migration_candidates[fname] = primary_files[fname]
        elif fname in secondary_files:
            migration_candidates[fname] = secondary_files[fname]
        else:
            missing_from_disk.append(fname)

    seed_files: Dict[str, Path] = {}
    for fname, fpath in sorted(primary_files.items()):
        if fname.startswith('seed_') and fname not in migration_candidates:
            seed_files[fname] = fpath
    for fname, fpath in sorted(secondary_files.items()):
        if fname.startswith('seed_') and fname not in migration_candidates and fname not in seed_files:
            seed_files[fname] = fpath

    primary_unreferenced = sorted(set(primary_files.keys()) - referenced_names - set(seed_files.keys()))
    secondary_duplicates_of_primary = sorted(set(secondary_files.keys()) & set(primary_files.keys()))

    return {
        'primary_total': len(primary_files),
        'secondary_total': len(secondary_files),
        'secondary_duplicates_of_primary': len(secondary_duplicates_of_primary),
        'migration_candidates': migration_candidates,
        'seed_files': seed_files,
        'unreferenced_primary': primary_unreferenced,
        'missing_from_disk': sorted(missing_from_disk),
    }


def _create_azure_container_client(
    account_url: str,
    container_name: str,
    connection_string: str = '',
):
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    if connection_string:
        svc_client = BlobServiceClient.from_connection_string(connection_string)
    elif account_url:
        svc_client = BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())
    else:
        raise RuntimeError('Either --azure-account-url or --azure-connection-string must be provided for --execute.')
    return svc_client.get_container_client(container_name)


def upload_files_to_azure(
    files_map: Dict[str, Path],
    container_client,
    overwrite: bool = False,
) -> Dict[str, int]:
    """Uploads files to 'reports/<filename>' non-destructively (skips existing unless overwrite=True)."""
    from azure.storage.blob import ContentSettings

    stats = {'uploaded': 0, 'skipped_existing': 0, 'failed': 0}
    for fname, fpath in sorted(files_map.items()):
        blob_name = f'reports/{fname}'
        blob_client = container_client.get_blob_client(blob_name)
        try:
            if not overwrite and blob_client.exists():
                stats['skipped_existing'] += 1
                continue
            mime_type, _ = mimetypes.guess_type(str(fpath))
            content_settings = ContentSettings(content_type=mime_type or 'application/octet-stream')
            with open(fpath, 'rb') as stream:
                blob_client.upload_blob(stream, overwrite=overwrite, content_settings=content_settings)
            stats['uploaded'] += 1
        except Exception as exc:
            print(f"  [ERROR] Failed uploading {blob_name}: {exc}", file=sys.stderr)
            stats['failed'] += 1
    return stats


def run_audit_and_migration(
    mongo_uri: str,
    db_name: str,
    execute: bool = False,
    include_seed: bool = False,
    overwrite: bool = False,
    azure_account_url: str = '',
    azure_container: str = 'defect-images',
    azure_connection_string: str = '',
) -> int:
    referenced = collect_db_referenced_filenames(mongo_uri, db_name)
    summary = classify_local_uploads(referenced)

    migration_candidates: Dict[str, Path] = summary['migration_candidates']
    seed_files: Dict[str, Path] = summary['seed_files']
    unreferenced_primary: List[str] = summary['unreferenced_primary']
    missing_from_disk: List[str] = summary['missing_from_disk']

    print("=================================================================")
    print("  InfraVision — Historical Evidence Image Audit & Migration")
    print("=================================================================")
    print(f"Primary folder (backend/uploads) : {summary['primary_total']} files")
    print(f"Secondary folder (uploads)       : {summary['secondary_total']} files ({summary['secondary_duplicates_of_primary']} duplicate primary filenames)")
    print(f"MongoDB referenced evidence      : {len(referenced)} unique filenames ({len(migration_candidates)} found locally)")
    print(f"Sample seed_* files              : {len(seed_files)} ({', '.join(sorted(seed_files.keys()))})")
    print(f"Unreferenced test/temp files     : {len(unreferenced_primary)} (EXCLUDED from upload)")
    print(f"Missing referenced files         : {len(missing_from_disk)}")

    if missing_from_disk:
        print(f"  Warning: missing files: {missing_from_disk[:10]}")

    to_upload: Dict[str, Path] = dict(migration_candidates)
    if include_seed:
        to_upload.update(seed_files)

    print(f"Selected for Azure Blob ('reports/<name>'): {len(to_upload)} files (include_seed={include_seed})")

    if not execute:
        print("Dry-run complete. No files were uploaded or modified.")
        return 0

    container_client = _create_azure_container_client(
        account_url=azure_account_url,
        container_name=azure_container,
        connection_string=azure_connection_string,
    )
    stats = upload_files_to_azure(to_upload, container_client, overwrite=overwrite)
    print(
        f"Migration complete -> uploaded={stats['uploaded']}, "
        f"skipped_existing={stats['skipped_existing']}, failed={stats['failed']}"
    )
    return 1 if stats['failed'] > 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-destructive report image audit and Azure Blob migration utility.")
    parser.add_argument('--mongo-uri', default=os.getenv('MONGO_URI', 'mongodb://localhost:27017/civil_infrastructure'))
    parser.add_argument('--db-name', default=os.getenv('DB_NAME', 'civil_infrastructure'))
    parser.add_argument('--execute', action='store_true', help='Upload selected files to Azure Blob Storage (default is read-only audit).')
    parser.add_argument('--include-seed', action='store_true', help='Also upload sample seed_* files (like -SyncSeedImages).')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing blobs (default skips existing blobs).')
    parser.add_argument('--azure-account-url', default=os.getenv('AZURE_STORAGE_ACCOUNT_URL', ''))
    parser.add_argument('--azure-container', default=os.getenv('AZURE_STORAGE_CONTAINER', 'defect-images'))
    parser.add_argument('--azure-connection-string', default=os.getenv('AZURE_STORAGE_CONNECTION_STRING', ''))
    args = parser.parse_args()
    return run_audit_and_migration(
        mongo_uri=args.mongo_uri,
        db_name=args.db_name,
        execute=args.execute,
        include_seed=args.include_seed,
        overwrite=args.overwrite,
        azure_account_url=args.azure_account_url.strip(),
        azure_container=args.azure_container.strip(),
        azure_connection_string=args.azure_connection_string.strip(),
    )


if __name__ == '__main__':
    raise SystemExit(main())
