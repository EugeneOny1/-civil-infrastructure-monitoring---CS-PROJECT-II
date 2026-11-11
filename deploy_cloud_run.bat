@echo off
REM ==============================================================================
REM InfraVision - Google Cloud Run Deployment Script (Windows)
REM Single-Service Production Deployment: Frontend + Flask + SSD-MobileNetV2
REM ==============================================================================

setlocal enabledelayedexpansion

set SERVICE_NAME=infravision
set REGION=us-central1
set MEMORY=4Gi
set CPU=2
set CONCURRENCY=4
set TIMEOUT=300s
set MIN_INSTANCES=1
set MAX_INSTANCES=10

echo =================================================================
echo   InfraVision: Google Cloud Run Single-Service Deployment
echo   Architecture: Frontend + Flask Backend + SSD-MobileNetV2 V2
echo =================================================================

REM Check gcloud CLI
where gcloud >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: 'gcloud' CLI is required. Please install Google Cloud SDK.
    exit /b 1
)

for /f "tokens=*" %%i in ('gcloud config get-value project 2^>nul') do set PROJECT_ID=%%i
if "%PROJECT_ID%"=="" (
    echo ERROR: No active GCP project configured. Run 'gcloud config set project ^<PROJECT_ID^>'.
    exit /b 1
)

echo Active Project: %PROJECT_ID%
echo Service Name:   %SERVICE_NAME%
echo Target Region:  %REGION%
echo.

echo [1/3] Enabling required Google Cloud APIs...
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

echo [2/3] Building container image and deploying to Cloud Run...
gcloud run deploy %SERVICE_NAME% ^
    --source . ^
    --region %REGION% ^
    --platform managed ^
    --allow-unauthenticated ^
    --memory %MEMORY% ^
    --cpu %CPU% ^
    --concurrency %CONCURRENCY% ^
    --min-instances %MIN_INSTANCES% ^
    --max-instances %MAX_INSTANCES% ^
    --timeout %TIMEOUT% ^
    --execution-environment gen2 ^
    --cpu-boost ^
    --port 8080 ^
    --set-env-vars FLASK_ENV=production,DEBUG=False,STORAGE_BACKEND=local

echo.
echo [3/3] Deployment complete. Fetching service URL...
for /f "tokens=*" %%u in ('gcloud run services describe %SERVICE_NAME% --region %REGION% --format "value(status.url)" 2^>nul') do set SERVICE_URL=%%u

echo =================================================================
echo   Deployment Complete!
echo   Service URL: !SERVICE_URL!
echo   Liveness Probe: !SERVICE_URL!/health
echo   System Telemetry: !SERVICE_URL!/api/health
echo =================================================================
endlocal
