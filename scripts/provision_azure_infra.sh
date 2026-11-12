#!/usr/bin/env bash
# ==============================================================================
# InfraVision — One-Time Azure Infrastructure & GitHub OIDC Provisioning Script
# Designed to run directly inside Azure Cloud Shell (Bash) in the Azure Portal.
# Reuses existing infrastructure in uaenorth and configures a dedicated
# user-assigned managed identity (infravision-github-deploy) for GitHub OIDC,
# avoiding Microsoft Entra tenant-level application registration limits.
# ==============================================================================
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-infravision-rg}"
CONTAINER_APPS_ENV="${CONTAINER_APPS_ENV:-infravision-env}"
BLOB_CONTAINER="${BLOB_CONTAINER:-defect-images}"
MANAGED_IDENTITY_NAME="${MANAGED_IDENTITY_NAME:-infravision-identity}"
DEPLOY_IDENTITY_NAME="${DEPLOY_IDENTITY_NAME:-infravision-github-deploy}"
GITHUB_REPO="${GITHUB_REPO:-EugeneOny1/-civil-infrastructure-monitoring---CS-PROJECT-II}"
LOCATION="${LOCATION:-uaenorth}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-}"
ALLOW_NON_STUDENT="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource-group) RESOURCE_GROUP="$2"; shift 2 ;;
    --env-name) CONTAINER_APPS_ENV="$2"; shift 2 ;;
    --blob-container) BLOB_CONTAINER="$2"; shift 2 ;;
    --storage-account) STORAGE_ACCOUNT="$2"; shift 2 ;;
    --runtime-identity) MANAGED_IDENTITY_NAME="$2"; shift 2 ;;
    --deploy-identity) DEPLOY_IDENTITY_NAME="$2"; shift 2 ;;
    --location) LOCATION="$2"; shift 2 ;;
    --github-repo) GITHUB_REPO="$2"; shift 2 ;;
    --allow-non-student) ALLOW_NON_STUDENT="true"; shift ;;
    -h|--help)
      cat <<'EOF'
Usage: bash scripts/provision_azure_infra.sh [options]

Options:
  --resource-group <name>     Azure Resource Group (default: infravision-rg)
  --env-name <name>           ACA Consumption environment (default: infravision-env)
  --blob-container <name>     Private Blob container (default: defect-images)
  --storage-account <name>    Existing or target Storage Account name
  --runtime-identity <name>   Application runtime identity for Blob Storage (default: infravision-identity)
  --deploy-identity <name>    GitHub Actions deployment identity (default: infravision-github-deploy)
  --location <region>         Azure region (default: uaenorth)
  --github-repo <owner/repo>  GitHub repository for OIDC trust
  --allow-non-student         Allow subscriptions whose name does not match 'Student'
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

echo "================================================================="
echo "  InfraVision — Azure Cloud Shell Provisioner & OIDC Setup"
echo "================================================================="

if ! command -v az >/dev/null 2>&1; then
  echo "ERROR: Azure CLI ('az') not found. Run this script in Azure Cloud Shell (Bash)." >&2
  exit 1
fi

SUB_ID="$(az account show --query "id" -o tsv | tr -d '\r')"
SUB_NAME="$(az account show --query "name" -o tsv | tr -d '\r')"
TENANT_ID="$(az account show --query "tenantId" -o tsv | tr -d '\r')"

if [[ "${ALLOW_NON_STUDENT}" != "true" && ! "${SUB_NAME}" =~ [Ss]tudent ]]; then
  echo "ERROR: Active subscription '${SUB_NAME}' (${SUB_ID}) does not match 'Azure for Students'." >&2
  echo "Switch with: az account set --subscription <student-subscription-id>" >&2
  echo "Or pass --allow-non-student to override." >&2
  exit 1
fi
echo "[OK] Subscription: ${SUB_NAME} (${SUB_ID})"

# 1. Detect or reuse region
if [[ -z "${LOCATION}" ]]; then
  RG_LOC="$(az group show --name "${RESOURCE_GROUP}" --query "location" -o tsv 2>/dev/null | tr -d '\r' || true)"
  if [[ -n "${RG_LOC}" ]]; then
    LOCATION="${RG_LOC}"
  else
    LOCATION="uaenorth"
  fi
fi

# 2. Detect or compute deterministic storage account & log analytics workspace
SUFFIX="$(python3 -c "import hashlib; print(hashlib.sha256('${SUB_ID}|${RESOURCE_GROUP}'.encode()).hexdigest()[:8])")"
if [[ -z "${STORAGE_ACCOUNT}" ]]; then
  EXISTING_ST="$(az storage account list --resource-group "${RESOURCE_GROUP}" --query "[0].name" -o tsv 2>/dev/null | tr -d '\r' || true)"
  if [[ -n "${EXISTING_ST}" ]]; then
    STORAGE_ACCOUNT="${EXISTING_ST}"
  else
    STORAGE_ACCOUNT="infravisionst${SUFFIX}"
  fi
fi
LOG_WORKSPACE="infravision-logs-${SUFFIX}"

echo "  Region               : ${LOCATION}"
echo "  Resource Group       : ${RESOURCE_GROUP}"
echo "  Storage Account      : ${STORAGE_ACCOUNT} (Standard_LRS, private container '${BLOB_CONTAINER}')"
echo "  Runtime Identity     : ${MANAGED_IDENTITY_NAME} (Blob access)"
echo "  Deployment Identity  : ${DEPLOY_IDENTITY_NAME} (GitHub OIDC & ACA Contributor)"
echo "  Log Analytics        : ${LOG_WORKSPACE} (30-day retention)"
echo "  ACA Environment      : ${CONTAINER_APPS_ENV} (Consumption workload profile)"
echo "  GitHub OIDC Trust    : ${GITHUB_REPO}"
echo ""

# 1. Register minimal required Azure Resource Providers & CLI extension
az extension add --name containerapp --upgrade --only-show-errors >/dev/null
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.Storage Microsoft.ManagedIdentity; do
  STATE="$(az provider show --namespace "${ns}" --query "registrationState" -o tsv 2>/dev/null | tr -d '\r' || true)"
  if [[ "${STATE}" != "Registered" ]]; then
    echo "Registering provider ${ns}..."
    az provider register --namespace "${ns}" --wait >/dev/null
  else
    echo "[OK] Provider ${ns} registered."
  fi
done

# 2. Resource Group (create if missing; reuse if existing)
if [[ "$(az group exists --name "${RESOURCE_GROUP}" -o tsv | tr -d '\r')" != "true" ]]; then
  az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" --only-show-errors >/dev/null
  echo "[OK] Created Resource Group ${RESOURCE_GROUP} (${LOCATION})."
else
  echo "[OK] Resource Group ${RESOURCE_GROUP} exists (${LOCATION})."
fi

# 3. Private Blob Storage Account + Container (reuse existing)
if ! az storage account show --name "${STORAGE_ACCOUNT}" --resource-group "${RESOURCE_GROUP}" >/dev/null 2>&1; then
  az storage account create \
    --name "${STORAGE_ACCOUNT}" \
    --resource-group "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --allow-blob-public-access false \
    --https-only true \
    --min-tls-version TLS1_2 \
    --only-show-errors >/dev/null
  echo "[OK] Created Storage Account ${STORAGE_ACCOUNT}."
else
  echo "[OK] Storage Account ${STORAGE_ACCOUNT} exists."
fi

BLOB_ENDPOINT="$(az storage account show --name "${STORAGE_ACCOUNT}" --resource-group "${RESOURCE_GROUP}" --query "primaryEndpoints.blob" -o tsv | tr -d '\r' | sed 's:/*$::')"
STORAGE_SCOPE="$(az storage account show --name "${STORAGE_ACCOUNT}" --resource-group "${RESOURCE_GROUP}" --query "id" -o tsv | tr -d '\r')"
ST_KEY="$(az storage account keys list --resource-group "${RESOURCE_GROUP}" --account-name "${STORAGE_ACCOUNT}" --query "[0].value" -o tsv | tr -d '\r')"

if [[ "$(az storage container exists --name "${BLOB_CONTAINER}" --account-name "${STORAGE_ACCOUNT}" --account-key "${ST_KEY}" --query "exists" -o tsv | tr -d '\r')" != "true" ]]; then
  az storage container create \
    --name "${BLOB_CONTAINER}" \
    --account-name "${STORAGE_ACCOUNT}" \
    --account-key "${ST_KEY}" \
    --public-access off \
    --only-show-errors >/dev/null
  echo "[OK] Created private Blob container '${BLOB_CONTAINER}'."
else
  echo "[OK] Private Blob container '${BLOB_CONTAINER}' exists."
fi

# Helper function to assign RBAC roles safely with propagation retries
assign_rbac_retry() {
  local assignee="$1"
  local role="$2"
  local scope="$3"
  local existing
  existing="$(az role assignment list --assignee "${assignee}" --role "${role}" --scope "${scope}" --query "[0].id" -o tsv 2>/dev/null | tr -d '\r' || true)"
  if [[ -n "${existing}" ]]; then
    echo "[OK] RBAC '${role}' already assigned on target scope."
    return 0
  fi
  for attempt in $(seq 1 8); do
    if az role assignment create \
      --assignee-object-id "${assignee}" \
      --assignee-principal-type ServicePrincipal \
      --role "${role}" \
      --scope "${scope}" \
      --only-show-errors >/dev/null 2>&1; then
      echo "[OK] Assigned '${role}' cleanly."
      return 0
    fi
    echo "  Waiting for Entra directory propagation (${attempt}/8)..."
    sleep 10
  done
  echo "ERROR: Could not assign role '${role}' after retries." >&2
  return 1
}

# 4. Runtime User-Assigned Managed Identity + Storage Blob Data Contributor RBAC
if ! az identity show --name "${MANAGED_IDENTITY_NAME}" --resource-group "${RESOURCE_GROUP}" >/dev/null 2>&1; then
  az identity create --name "${MANAGED_IDENTITY_NAME}" --resource-group "${RESOURCE_GROUP}" --location "${LOCATION}" --only-show-errors >/dev/null
  echo "[OK] Created Runtime Managed Identity ${MANAGED_IDENTITY_NAME}."
else
  echo "[OK] Runtime Managed Identity ${MANAGED_IDENTITY_NAME} exists."
fi

RUNTIME_CLIENT_ID="$(az identity show --name "${MANAGED_IDENTITY_NAME}" --resource-group "${RESOURCE_GROUP}" --query "clientId" -o tsv | tr -d '\r')"
RUNTIME_PRINCIPAL_ID="$(az identity show --name "${MANAGED_IDENTITY_NAME}" --resource-group "${RESOURCE_GROUP}" --query "principalId" -o tsv | tr -d '\r')"

assign_rbac_retry "${RUNTIME_PRINCIPAL_ID}" "Storage Blob Data Contributor" "${STORAGE_SCOPE}"

# 5. Log Analytics + Azure Container Apps Consumption Environment
if ! az containerapp env show --name "${CONTAINER_APPS_ENV}" --resource-group "${RESOURCE_GROUP}" >/dev/null 2>&1; then
  if ! az monitor log-analytics workspace show --workspace-name "${LOG_WORKSPACE}" --resource-group "${RESOURCE_GROUP}" >/dev/null 2>&1; then
    az monitor log-analytics workspace create \
      --resource-group "${RESOURCE_GROUP}" \
      --workspace-name "${LOG_WORKSPACE}" \
      --location "${LOCATION}" \
      --retention-time 30 \
      --only-show-errors >/dev/null
  fi
  WS_ID="$(az monitor log-analytics workspace show --workspace-name "${LOG_WORKSPACE}" --resource-group "${RESOURCE_GROUP}" --query "customerId" -o tsv | tr -d '\r')"
  WS_KEY="$(az monitor log-analytics workspace get-shared-keys --resource-group "${RESOURCE_GROUP}" --workspace-name "${LOG_WORKSPACE}" --query "primarySharedKey" -o tsv | tr -d '\r')"
  az containerapp env create \
    --name "${CONTAINER_APPS_ENV}" \
    --resource-group "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --logs-workspace-id "${WS_ID}" \
    --logs-workspace-key "${WS_KEY}" \
    --only-show-errors >/dev/null
  echo "[OK] Created ACA Consumption environment ${CONTAINER_APPS_ENV}."
else
  echo "[OK] ACA Consumption environment ${CONTAINER_APPS_ENV} exists."
fi

# 6. Configure Deployment Managed Identity & GitHub Actions OIDC Trust
# Creates a dedicated User-Assigned Managed Identity (infravision-github-deploy) with Contributor role on infravision-rg.
# Uses az identity federated-credential (ARM resource group level) rather than Microsoft Entra directory app registrations.
if ! az identity show --name "${DEPLOY_IDENTITY_NAME}" --resource-group "${RESOURCE_GROUP}" >/dev/null 2>&1; then
  az identity create --name "${DEPLOY_IDENTITY_NAME}" --resource-group "${RESOURCE_GROUP}" --location "${LOCATION}" --only-show-errors >/dev/null
  echo "[OK] Created Deployment Managed Identity ${DEPLOY_IDENTITY_NAME}."
else
  echo "[OK] Deployment Managed Identity ${DEPLOY_IDENTITY_NAME} exists."
fi

DEPLOY_CLIENT_ID="$(az identity show --name "${DEPLOY_IDENTITY_NAME}" --resource-group "${RESOURCE_GROUP}" --query "clientId" -o tsv | tr -d '\r')"
DEPLOY_PRINCIPAL_ID="$(az identity show --name "${DEPLOY_IDENTITY_NAME}" --resource-group "${RESOURCE_GROUP}" --query "principalId" -o tsv | tr -d '\r')"

# Assign Contributor role ONLY at the infravision-rg resource group scope
RG_SCOPE="/subscriptions/${SUB_ID}/resourceGroups/${RESOURCE_GROUP}"
assign_rbac_retry "${DEPLOY_PRINCIPAL_ID}" "Contributor" "${RG_SCOPE}"

ensure_identity_federated_cred() {
  local cred_name="$1"
  local subject="$2"
  if az identity federated-credential show --name "${cred_name}" --identity-name "${DEPLOY_IDENTITY_NAME}" --resource-group "${RESOURCE_GROUP}" >/dev/null 2>&1; then
    echo "[OK] Federated credential '${cred_name}' already exists on ${DEPLOY_IDENTITY_NAME}."
    return 0
  fi
  az identity federated-credential create \
    --name "${cred_name}" \
    --identity-name "${DEPLOY_IDENTITY_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --issuer "https://token.actions.githubusercontent.com" \
    --subject "${subject}" \
    --audiences "api://AzureADTokenExchange" \
    --only-show-errors >/dev/null
  echo "[OK] Created federated credential '${cred_name}' (${subject}) on ${DEPLOY_IDENTITY_NAME}."
}

ensure_identity_federated_cred "github-app-dev" "repo:${GITHUB_REPO}:ref:refs/heads/app-development"
ensure_identity_federated_cred "github-main" "repo:${GITHUB_REPO}:ref:refs/heads/main"

echo ""
echo "================================================================="
echo "  ONE-TIME AZURE INFRASTRUCTURE & OIDC PROVISIONED"
echo "================================================================="
echo "Add these GitHub Actions Repository VARIABLES (Settings -> Secrets and variables -> Actions -> Variables):"
echo "  AZURE_CLIENT_ID           = ${DEPLOY_CLIENT_ID}"
echo "  AZURE_TENANT_ID           = ${TENANT_ID}"
echo "  AZURE_SUBSCRIPTION_ID     = ${SUB_ID}"
echo "  AZURE_LOCATION            = ${LOCATION}"
echo "  AZURE_STORAGE_ACCOUNT_URL = ${BLOB_ENDPOINT}"
echo "  AZURE_RUNTIME_CLIENT_ID   = ${RUNTIME_CLIENT_ID}"
echo "  AZURE_IDENTITY_CLIENT_ID  = ${RUNTIME_CLIENT_ID}"
echo ""
echo "Add these GitHub Actions Repository SECRETS (Settings -> Secrets and variables -> Actions -> Secrets):"
echo "  MONGO_URI       = <Your MongoDB Atlas mongodb+srv://... connection string>"
echo "  GHCR_PULL_TOKEN = <GitHub PAT with read:packages so Azure pulls private GHCR images>"
echo "  SECRET_KEY      = <Optional strong random key (auto-generated on initial deploy if omitted)>"
echo "  JWT_SECRET_KEY  = <Optional strong random JWT key (auto-generated on initial deploy if omitted)>"
echo ""
echo "Verification & Roles:"
echo "  Resource Group       : ${RESOURCE_GROUP} (${LOCATION})"
echo "  Storage Account      : ${STORAGE_ACCOUNT} (Container: ${BLOB_CONTAINER})"
echo "  Runtime Identity     : ${MANAGED_IDENTITY_NAME} (Role: Storage Blob Data Contributor on Storage)"
echo "                         Client ID: ${RUNTIME_CLIENT_ID} (used by ACA container for Blob access)"
echo "  Deployment Identity  : ${DEPLOY_IDENTITY_NAME} (Role: Contributor on ${RESOURCE_GROUP})"
echo "                         Client ID: ${DEPLOY_CLIENT_ID} (used by GitHub Actions azure/login)"
echo "  Federated Subjects   : repo:${GITHUB_REPO}:ref:refs/heads/app-development"
echo "                         repo:${GITHUB_REPO}:ref:refs/heads/main"
echo "  Container Apps Env   : ${CONTAINER_APPS_ENV}"
echo "================================================================="
