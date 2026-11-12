"""
Durable Storage Service for InfraVision Infrastructure Defect Monitoring.
Supports pluggable storage backends controlled via STORAGE_BACKEND environment variable:
- 'local': Local filesystem storage for development and testing
- 'azure': Private Azure Blob Storage for durable multi-replica persistence (Managed Identity / connection string fallback)
- 'gcs': Google Cloud Storage object store (preserved for Cloud Run compatibility)

Follows the Single Responsibility Principle and isolates cloud storage logic
from route handlers.
"""

import os
import io
import uuid
import mimetypes
from pathlib import Path
from typing import Tuple, Optional
from werkzeug.utils import secure_filename
from flask import current_app, send_from_directory, send_file, Response, jsonify, make_response
from PIL import Image


class StorageService:
    """
    Manages persistent storage and serving of infrastructure defect images.
    Provides transparent abstraction across local disk, Azure Blob Storage, and GCS.
    """

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

    def __init__(
        self,
        backend: Optional[str] = None,
        bucket_name: Optional[str] = None,
        azure_account_url: Optional[str] = None,
        azure_container_name: Optional[str] = None,
        azure_client_id: Optional[str] = None,
        azure_connection_string: Optional[str] = None,
    ):
        self._backend = backend
        self._bucket_name = bucket_name
        self._azure_account_url = azure_account_url
        self._azure_container_name = azure_container_name
        self._azure_client_id = azure_client_id
        self._azure_connection_string = azure_connection_string
        self._gcs_client = None
        self._gcs_bucket = None
        self._azure_container_client = None
        self._azure_client_key = None
        self._initialized = False

    def _get_cfg(self, key: str, default: str = '') -> str:
        if current_app:
            val = current_app.config.get(key)
            if val is not None and str(val).strip() != '':
                return str(val).strip()
        return os.getenv(key, default).strip()

    @property
    def backend(self) -> str:
        if self._backend:
            return self._backend.lower()
        return self._get_cfg('STORAGE_BACKEND', 'local').lower()

    @property
    def bucket_name(self) -> str:
        if self._bucket_name is not None:
            return self._bucket_name
        return self._get_cfg('GCS_BUCKET_NAME', '')

    @property
    def azure_account_url(self) -> str:
        if self._azure_account_url is not None:
            return self._azure_account_url
        return self._get_cfg('AZURE_STORAGE_ACCOUNT_URL', '')

    @property
    def azure_container_name(self) -> str:
        if self._azure_container_name is not None:
            return self._azure_container_name
        return self._get_cfg('AZURE_STORAGE_CONTAINER', 'defect-images') or 'defect-images'

    @property
    def azure_client_id(self) -> str:
        if self._azure_client_id is not None:
            return self._azure_client_id
        return self._get_cfg('AZURE_CLIENT_ID', '')

    @property
    def azure_connection_string(self) -> str:
        if self._azure_connection_string is not None:
            return self._azure_connection_string
        return self._get_cfg('AZURE_STORAGE_CONNECTION_STRING', '')

    def _get_gcs_bucket(self):
        """Lazy initialization of Google Cloud Storage bucket."""
        if self._gcs_bucket is not None:
            return self._gcs_bucket

        try:
            from google.cloud import storage as gcs_storage
            client = gcs_storage.Client()
            self._gcs_client = client
            bucket_name = self.bucket_name
            if not bucket_name:
                print("[StorageService] WARNING: GCS_BUCKET_NAME is not set. Falling back to local storage.")
                return None
            self._gcs_bucket = client.bucket(bucket_name)
            print(f"[StorageService] Connected to Google Cloud Storage bucket: {bucket_name}")
            return self._gcs_bucket
        except Exception as e:
            print(f"[StorageService] ERROR connecting to GCS: {e}. Falling back to local storage.")
            return None

    def _get_azure_container_client(self):
        """
        Lazy initialization of private Azure Blob Storage container client.
        Prefers Azure Managed Identity via AZURE_STORAGE_ACCOUNT_URL + AZURE_CLIENT_ID.
        Falls back to AZURE_STORAGE_CONNECTION_STRING only when explicitly configured.
        """
        account_url = self.azure_account_url
        container_name = self.azure_container_name
        client_id = self.azure_client_id
        conn_str = self.azure_connection_string

        cache_key = (account_url, container_name, client_id, bool(conn_str))
        if self._azure_container_client is not None and self._azure_client_key == cache_key:
            return self._azure_container_client

        try:
            from azure.storage.blob import BlobServiceClient
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise RuntimeError(
                "Azure Blob Storage packages (azure-storage-blob, azure-identity) are required when STORAGE_BACKEND=azure."
            ) from exc

        if account_url:
            cred_kwargs = {}
            if client_id:
                cred_kwargs['managed_identity_client_id'] = client_id
            credential = DefaultAzureCredential(**cred_kwargs)
            service_client = BlobServiceClient(account_url=account_url, credential=credential)
        elif conn_str:
            service_client = BlobServiceClient.from_connection_string(conn_str)
        else:
            raise RuntimeError(
                "Azure Blob Storage configuration missing: set AZURE_STORAGE_ACCOUNT_URL (with Managed Identity) or AZURE_STORAGE_CONNECTION_STRING."
            )

        container_client = service_client.get_container_client(container_name)
        self._azure_container_client = container_client
        self._azure_client_key = cache_key
        return container_client

    @staticmethod
    def cleanup_local_temp_file(local_path: Optional[str]) -> None:
        """Removes a temporary local file safely after cloud upload and inference."""
        if not local_path:
            return
        try:
            if os.path.exists(local_path) and os.path.isfile(local_path):
                os.remove(local_path)
        except OSError:
            pass

    def is_allowed_file(self, filename: str) -> bool:
        """Verifies permissible image extensions."""
        if not filename or '.' not in filename:
            return False
        ext = filename.rsplit('.', 1)[1].lower()
        allowed = current_app.config.get('ALLOWED_EXTENSIONS', self.ALLOWED_EXTENSIONS) if current_app else self.ALLOWED_EXTENSIONS
        return ext in allowed

    def save_file(self, file_storage) -> Tuple[str, str, str, int, str]:
        """
        Validates and persists an uploaded defect image.

        Saves temporarily to UPLOAD_FOLDER first so SSD-MobileNetV2 inference can
        read it directly. When STORAGE_BACKEND='azure', uploads to private Azure Blob Storage
        explicitly (raising RuntimeError without silent local fallback on failure).
        """
        if not file_storage or not file_storage.filename or not self.is_allowed_file(file_storage.filename):
            raise ValueError("Invalid file or unsupported image format. Permitted formats: PNG, JPG, JPEG, WEBP.")

        if current_app:
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        else:
            upload_folder = os.getenv('UPLOAD_FOLDER', 'uploads')

        if not os.path.isabs(upload_folder):
            base_dir = Path(__file__).resolve().parent.parent.parent
            upload_folder = str((base_dir / upload_folder).resolve())

        os.makedirs(upload_folder, exist_ok=True)

        orig_name = secure_filename(file_storage.filename)
        ext = orig_name.rsplit('.', 1)[1].lower() if '.' in orig_name else 'jpg'
        unique_filename = f"infra_{uuid.uuid4().hex[:12]}.{ext}"
        dest_path = os.path.join(upload_folder, unique_filename)

        # Save to local disk first for PIL validation and SavedModel inference
        file_storage.save(dest_path)

        # Validate image data integrity using PIL
        try:
            with Image.open(dest_path) as img:
                img.verify()
            with Image.open(dest_path) as img:
                _ = img.size
        except Exception as e:
            self.cleanup_local_temp_file(dest_path)
            raise ValueError(f"Uploaded file is not a valid or readable image: {e}")

        file_size = os.path.getsize(dest_path)
        storage_url = f"/api/reports/images/{unique_filename}"
        content_type = mimetypes.guess_type(dest_path)[0] or 'image/jpeg'

        # Durable Azure Blob Storage persistence (explicit failure: never silently fall back)
        if self.backend == 'azure':
            try:
                from azure.storage.blob import ContentSettings
                container_client = self._get_azure_container_client()
                blob_client = container_client.get_blob_client(f"reports/{unique_filename}")
                with open(dest_path, 'rb') as data:
                    blob_client.upload_blob(
                        data,
                        overwrite=True,
                        content_settings=ContentSettings(content_type=content_type)
                    )
            except Exception as azure_err:
                self.cleanup_local_temp_file(dest_path)
                raise RuntimeError(f"Failed uploading {unique_filename} to Azure Blob Storage: {azure_err}") from azure_err

        # Google Cloud Storage support preserved for Cloud Run compatibility
        elif self.backend == 'gcs':
            bucket = self._get_gcs_bucket()
            if bucket:
                try:
                    blob = bucket.blob(f"reports/{unique_filename}")
                    blob.upload_from_filename(dest_path, content_type=content_type)
                    print(f"[StorageService] Successfully uploaded {unique_filename} to GCS bucket: {self.bucket_name}")
                except Exception as gcs_err:
                    print(f"[StorageService] WARNING: Failed uploading {unique_filename} to GCS: {gcs_err}. Retained locally.")

        return unique_filename, dest_path, orig_name, file_size, storage_url

    def _apply_serve_headers(self, resp: Response) -> Response:
        is_prod = bool(current_app and not current_app.debug and not current_app.testing)
        if is_prod or self.backend in ('azure', 'gcs'):
            resp.headers['Cache-Control'] = 'private, max-age=3600'
            cors_cfg = current_app.config.get('CORS_ORIGINS', []) if current_app else []
            if cors_cfg == '*':
                resp.headers['Access-Control-Allow-Origin'] = '*'
        else:
            resp.headers['Access-Control-Allow-Origin'] = '*'
            resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp

    def serve_file(self, filename: str) -> Response:
        """
        Serves an infrastructure defect image by filename.
        Resolves safely from local canonical directory, workspace fallback directory,
        private Azure Blob Storage container, or GCS bucket.
        """
        # Security: sanitize and reject directory traversal
        if not filename or '..' in filename or filename.startswith('/') or filename.startswith('\\'):
            return make_response(jsonify({'error': 'Invalid evidence image path.'}), 400)

        clean_filename = filename.replace('\\', '/')
        for prefix in ('backend/uploads/', 'uploads/', 'reports/'):
            if clean_filename.lower().startswith(prefix):
                clean_filename = clean_filename[len(prefix):]

        clean_filename = os.path.basename(clean_filename)
        if not clean_filename:
            return make_response(jsonify({'error': 'Invalid evidence image filename.'}), 400)

        if current_app:
            canonical_upload_dir = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
        else:
            canonical_upload_dir = os.path.abspath('uploads')

        # 1. Check local canonical directory (dev mode or warm replica cache)
        local_file_path = os.path.join(canonical_upload_dir, clean_filename)
        if os.path.exists(local_file_path):
            return self._apply_serve_headers(send_from_directory(canonical_upload_dir, clean_filename))

        # 2. Check fallback local directory (workspace uploads)
        root_uploads_dir = os.path.abspath(os.path.join(canonical_upload_dir, '..', '..', 'uploads'))
        fallback_path = os.path.join(root_uploads_dir, clean_filename)
        if os.path.exists(fallback_path):
            return self._apply_serve_headers(send_from_directory(root_uploads_dir, clean_filename))

        # 3. Check private Azure Blob Storage when configured
        if self.backend == 'azure' or self.azure_account_url or self.azure_connection_string:
            try:
                container_client = self._get_azure_container_client()
                blob_client = None
                for key in (f"reports/{clean_filename}", clean_filename):
                    candidate = container_client.get_blob_client(key)
                    if candidate.exists():
                        blob_client = candidate
                        break

                if blob_client is not None:
                    content = blob_client.download_blob().readall()
                    mtype = mimetypes.guess_type(clean_filename)[0] or 'image/jpeg'
                    try:
                        props = blob_client.get_blob_properties()
                        if props and props.content_settings and props.content_settings.content_type:
                            mtype = props.content_settings.content_type
                    except Exception:
                        pass
                    resp = send_file(io.BytesIO(content), mimetype=mtype)
                    return self._apply_serve_headers(resp)
            except Exception as e:
                print(f"[StorageService] ERROR retrieving blob '{clean_filename}' from Azure Blob Storage: {e}")

        # 4. Check Google Cloud Storage if configured
        if self.backend == 'gcs' or self.bucket_name:
            bucket = self._get_gcs_bucket()
            if bucket:
                try:
                    blob = bucket.blob(f"reports/{clean_filename}")
                    if not blob.exists():
                        blob = bucket.blob(clean_filename)

                    if blob.exists():
                        os.makedirs(canonical_upload_dir, exist_ok=True)
                        try:
                            blob.download_to_filename(local_file_path)
                            resp = send_from_directory(canonical_upload_dir, clean_filename)
                        except Exception:
                            content = blob.download_as_bytes()
                            mtype = blob.content_type or mimetypes.guess_type(clean_filename)[0] or 'image/jpeg'
                            resp = send_file(io.BytesIO(content), mimetype=mtype)
                        return self._apply_serve_headers(resp)
                except Exception as e:
                    print(f"[StorageService] ERROR retrieving blob '{clean_filename}' from GCS: {e}")

        return make_response(jsonify({'error': 'Evidence image unavailable in storage.'}), 404)


# Canonical service singleton instance
storage_service = StorageService()
