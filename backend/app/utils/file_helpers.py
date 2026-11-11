import os
from werkzeug.utils import secure_filename
from flask import current_app
from ..services.storage import storage_service


def allowed_file(filename):
    """Verifies that the uploaded file has a permissible image extension."""
    return storage_service.is_allowed_file(filename)


def save_uploaded_image(file_storage):
    """
    Saves an uploaded file storage object to the configured uploads folder with a unique name,
    and synchronizes to durable cloud storage (GCS) if configured.
    Validates that file content is genuine and uncorrupted image data.
    Returns: (saved_relative_filename, absolute_path, original_filename, file_size)
    """
    unique_filename, dest_path, orig_name, file_size, _ = storage_service.save_file(file_storage)
    return unique_filename, dest_path, orig_name, file_size
