#!/usr/bin/env bash
# ==============================================================================
# InfraVision - Google Cloud Run Deployment Script
# Single-Service Production Deployment: Frontend + Flask + SSD-MobileNetV2
# ==============================================================================

set -euo pipefail

# Configuration Defaults (can be overridden via environment)
SERVICE_NAME="${SERVICE_NAME:-infravision}"
REGION="${REGION:-us-central1}"
MEMORY="${MEMORY:-4Gi}"
CPU="${CPU:-2}"
CONCURRENCY="${CONCURRENCY:-4}"
TIMEOUT="${TIMEOUT:-300s}"
MIN_INSTANCES="${MIN_INSTANCES:-1}"
MAX_INSTANCES="${MAX_INSTANCES:-10}"

echo "================================================================="
echo "  InfraVision: Google Cloud Run Single-Service Deployment        "
echo "  Architecture: Frontend + Flask Backend + SSD-MobileNetV2 V2    "
echo "================================================================="

# Check that gcloud is authenticated
if ! command -v gcloud &> /dev/null; then
    echo "ERROR: 'gcloud' CLI is required. Please install Google Cloud SDK."
    exit 1
fi

PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "")
if [ -z "$PROJECT_ID" ]; then
    echo "ERROR: No active GCP project configured. Run 'gcloud config set project <PROJECT_ID>'."
    exit 1
fi

echo "Active Project: $PROJECT_ID"
echo "Service Name:   $SERVICE_NAME"
echo "Target Region:  $REGION"
echo ""

# Enable required Google Cloud APIs
echo "[1/3] Enabling required Google Cloud APIs (Cloud Run, Cloud Build, Artifact Registry)..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com

# Deploy directly from source via Google Cloud Build & Cloud Run
echo "[2/3] Building container image and deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --memory "$MEMORY" \
    --cpu "$CPU" \
    --concurrency "$CONCURRENCY" \
    --min-instances "$MIN_INSTANCES" \
    --max-instances "$MAX_INSTANCES" \
    --timeout "$TIMEOUT" \
    --execution-environment gen2 \
    --cpu-boost \
    --port 8080 \
    --set-env-vars FLASK_ENV=production,DEBUG=False,STORAGE_BACKEND=local

echo ""
echo "[3/3] Deployment initiated. Fetching service URL..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format 'value(status.url)' 2>/dev/null || echo "")

echo "================================================================="
echo "  Deployment Complete!                                           "
echo "  Service URL: $SERVICE_URL                                      "
echo "  Liveness Probe: ${SERVICE_URL}/health                          "
echo "  System Telemetry: ${SERVICE_URL}/api/health                    "
echo "================================================================="
