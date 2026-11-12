# ==============================================================================
# InfraVision: Civil Infrastructure Defect Monitoring System
# Production Dockerfile for Azure Container Apps & Google Cloud Run
# Serving: Static Frontend + Flask REST API + V2.1 SSD-MobileNetV2 SavedModel
# ==============================================================================

FROM python:3.11-slim

# Prevent Python from writing .pyc files and force unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PORT=8080 \
    MODEL_PATH=/app/backend/models/structural_defect_detector \
    MODEL_VERSION=ssd_mobilenet_v2_lr00015_step1500_v2_1 \
    UPLOAD_FOLDER=/tmp/uploads

# Install minimal OS runtime packages for OpenCV, PIL, and SSL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set container working directory
WORKDIR /app

# Copy dependency manifest first for efficient Docker layer caching
COPY requirements.txt /app/requirements.txt

# Install production dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application backend, frontend, and WSGI entrypoint
COPY backend /app/backend
COPY frontend /app/frontend
COPY wsgi.py /app/wsgi.py

# Ensure ephemeral upload directory exists with proper permissions
RUN mkdir -p /tmp/uploads && chmod 777 /tmp/uploads

# Expose container default port
EXPOSE 8080

# Health check probe for container runtime liveness
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ready || exit 1

# Production startup using Gunicorn:
# - workers 1: Prevents duplicate loading of the TensorFlow SavedModel in memory
# - threads 4: Handles concurrent I/O, API queries, and static asset streaming efficiently
# - timeout 300: Accommodates SSD-MobileNetV2 deep inference on larger defect images
CMD exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 300 wsgi:app
