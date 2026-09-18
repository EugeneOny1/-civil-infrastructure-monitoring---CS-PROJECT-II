import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app

def allowed_file(filename):
    """Verifies that the uploaded file has a permissible image extension."""
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'webp'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed

def save_uploaded_image(file_storage):
    """
    Saves an uploaded file storage object to the configured uploads folder with a unique name.
    Returns: (saved_relative_filename, absolute_path, original_filename, file_size)
    """
    if not file_storage or not allowed_file(file_storage.filename):
        raise ValueError("Invalid file or unsupported image format. Allowed: PNG, JPG, JPEG, WEBP.")

    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)

    orig_name = secure_filename(file_storage.filename)
    ext = orig_name.rsplit('.', 1)[1].lower() if '.' in orig_name else 'jpg'
    unique_filename = f"infra_{uuid.uuid4().hex[:12]}.{ext}"
    dest_path = os.path.join(upload_folder, unique_filename)

    file_storage.save(dest_path)
    file_size = os.path.getsize(dest_path)

    return unique_filename, dest_path, orig_name, file_size
