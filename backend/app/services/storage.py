"""
Durable Storage Service for InfraVision Infrastructure Defect Monitoring.
Supports dual storage backends controlled via environment configuration:
- 'local': Local filesystem storage for development and testing
- 'gcs': Google Cloud Storage object store for ephemeral container runtimes (Google Cloud Run)

Follows the Single Responsibility Principle and isolates cloud storage logic
from route handlers.
"""

import os
import io
import uuid
import mimetypes
from pathlib import Path
from typing import Tuple, Optional, BinaryIO
from werkzeug.utils import secure_filename
from flask import current_app, send_from_directory, send_file, Response, jsonify, make_response
from PIL import Image


class StorageService:
    """
    Manages persistent storage and serving of infrastructure defect images.
    Provides transparent abstraction across local disk and Google Cloud Storage (GCS).
    """

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

    def __init__(self, backend: Optional[str] = None, bucket_name: Optional[str] = None):
        self._backend = backend
        self._bucket_name = bucket_name
        self._gcs_client = None
        self._gcs_bucket = None
        self._initialized = False

    @property
    def backend(self) -> str:
        if self._backend:
            return self._backend.lower()
        if current_app:
            return current_app.config.get('STORAGE_BACKEND', 'local').lower()
        return os.getenv('STORAGE_BACKEND', 'local').lower()

    @property
    def bucket_name(self) -> str:
        if self._bucket_name:
            return self._bucket_name
        if current_app:
            return current_app.config.get('GCS_BUCKET_NAME', '')
        return os.getenv('GCS_BUCKET_NAME', '')

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
        
        Saves locally first so that the image is available for immediate SSD-MobileNetV2
        inference. If backend is 'gcs', uploads the validated image to the Google Cloud
        Storage bucket.

        Returns:
            Tuple of:
            - unique_filename (canonical reference key, e.g. infra_a1b2c3d4e5f6.jpg)
            - local_path (absolute local path for SSD-MobileNetV2 inference)
            - orig_name (sanitized original filename)
            - file_size (size in bytes)
            - storage_url (canonical API or cloud access URL)
        """
        if not file_storage or not file_storage.filename or not self.is_allowed_file(file_storage.filename):
            raise ValueError("Invalid file or unsupported image format. Permitted formats: PNG, JPG, JPEG, WEBP.")

        # Determine local upload directory
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

        # Save to local disk first
        file_storage.save(dest_path)

        # Validate image data integrity using PIL
        try:
            with Image.open(dest_path) as img:
                img.verify()
            with Image.open(dest_path) as img:
                _ = img.size
        except Exception as e:
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
            raise ValueError(f"Uploaded file is not a valid or readable image: {e}")

        file_size = os.path.getsize(dest_path)
        storage_url = f"/api/reports/images/{unique_filename}"

        # If GCS backend is active, upload object to Cloud Storage
        if self.backend == 'gcs':
            bucket = self._get_gcs_bucket()
            if bucket:
                try:
                    blob = bucket.blob(f"reports/{unique_filename}")
                    content_type = mimetypes.guess_type(dest_path)[0] or 'image/jpeg'
                    blob.upload_from_filename(dest_path, content_type=content_type)
                    print(f"[StorageService] Successfully uploaded {unique_filename} to GCS bucket: {self.bucket_name}")
                except Exception as gcs_err:
                    print(f"[StorageService] WARNING: Failed uploading {unique_filename} to GCS: {gcs_err}. Retained locally.")

        return unique_filename, dest_path, orig_name, file_size, storage_url

    def serve_file(self, filename: str) -> Response:
        """
        Serves an infrastructure defect image by filename.
        Safely resolves from:
        1. Local canonical upload folder
        2. Local fallback folder (workspace uploads)
        3. Google Cloud Storage bucket (if GCS backend configured), streaming directly
           or caching locally for fast subsequent access.
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

        # 1. Check local canonical directory
        if current_app:
            canonical_upload_dir = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
        else:
            canonical_upload_dir = os.path.abspath('uploads')

        local_file_path = os.path.join(canonical_upload_dir, clean_filename)
        if os.path.exists(local_file_path):
            resp = send_from_directory(canonical_upload_dir, clean_filename)
            resp.headers['Access-Control-Allow-Origin'] = '*'
            resp.headers['Cache-Control'] = 'public, max-age=86400'
            return resp

        # 2. Check fallback local directory (root workspace uploads)
        root_uploads_dir = os.path.abspath(os.path.join(canonical_upload_dir, '..', '..', 'uploads'))
        fallback_path = os.path.join(root_uploads_dir, clean_filename)
        if os.path.exists(fallback_path):
            resp = send_from_directory(root_uploads_dir, clean_filename)
            resp.headers['Access-Control-Allow-Origin'] = '*'
            resp.headers['Cache-Control'] = 'public, max-age=86400'
            return resp

        # 3. Check Google Cloud Storage if configured
        if self.backend == 'gcs' or self.bucket_name:
            bucket = self._get_gcs_bucket()
            if bucket:
                try:
                    blob = bucket.blob(f"reports/{clean_filename}")
                    if not blob.exists():
                        blob = bucket.blob(clean_filename)

                    if blob.exists():
                        # Download to local canonical cache for fast subsequent access
                        os.makedirs(canonical_upload_dir, exist_ok=True)
                        try:
                            blob.download_to_filename(local_file_path)
                            resp = send_from_directory(canonical_upload_dir, clean_filename)
                        except Exception:
                            # Direct streaming fallback if writing to local disk fails
                            content = blob.download_as_bytes()
                            mtype = blob.content_type or mimetypes.guess_type(clean_filename)[0] or 'image/jpeg'
                            resp = send_file(io.BytesIO(content), mimetype=mtype)

                        resp.headers['Access-Control-Allow-Origin'] = '*'
                        resp.headers['Cache-Control'] = 'public, max-age=86400'
                        return resp
                except Exception as e:
                    print(f"[StorageService] ERROR retrieving blob '{clean_filename}' from GCS: {e}")

        return make_response(jsonify({'error': 'Evidence image unavailable in storage.'}), 404)


# Canonical service singleton instance
storage_service = StorageService()
