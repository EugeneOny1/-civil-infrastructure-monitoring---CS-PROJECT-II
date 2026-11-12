<#
.SYNOPSIS
    Idempotent Azure Container Apps Production Deployment Script for InfraVision.

.DESCRIPTION
    Automates preflight verification, local Docker build/verification (linux/amd64),
    Azure for Students eligibility verification, private Blob Storage provisioning,
    Managed Identity RBAC assignment, private Container Registry push (GHCR or ACR),
    and Azure Container Apps deployment with TensorFlow readiness/startup/liveness probes.

.EXAMPLE
    .\deploy_azure.ps1 -Plan
    Shows preflight checks, planned Azure resources, and cost estimates without provisioning.

.EXAMPLE
    .\deploy_azure.ps1
    Deploys using private GitHub Container Registry ($0 recurring registry fee) after confirmation.

.EXAMPLE
    .\deploy_azure.ps1 -RegistryMode acr
    Deploys using Azure Container Registry Basic (~$5/month) with Managed Identity AcrPull after confirmation.
#>

[CmdletBinding()]
param(
    [switch]$Plan,
    [ValidateSet('ghcr', 'acr')]
    [string]$RegistryMode = 'ghcr',
    [string]$ResourceGroup = 'infravision-rg',
    [string]$ContainerAppsEnv = 'infravision-env',
    [string]$ContainerAppName = 'infravision',
    [string]$BlobContainerName = 'defect-images',
    [string]$Location = '',
    [string]$ImageTag = '',
    [string]$GitHubOwner = '',
    [string]$GitHubUser = '',
    [string]$MongoUri = '',
    [switch]$SyncSeedImages,
    [switch]$Yes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StateFile = Join-Path $RepoRoot '.azure-deploy-state.json'
$EnvFile = Join-Path $RepoRoot 'backend\.env'
$ExpectedModelVersion = 'ssd_mobilenet_v2_lr00015_step1500_v2_1'
$ExpectedSavedModelSha256 = '384977d303af3e293dfbff4ae922cd0e7fd8a72b9a9713bb08b9378fc2f205a9'

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "=================================================================" -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host "=================================================================" -ForegroundColor Cyan
}

function Invoke-CheckedCommand {
    param(
        [string]$Description,
        [scriptblock]$Command
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($Description) with exit code $LASTEXITCODE."
    }
}

function Read-DotEnvMap {
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path $Path)) {
        return $map
    }
    foreach ($rawLine in Get-Content -Path $Path -Encoding UTF8) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        $idx = $line.IndexOf('=')
        if ($idx -lt 1) { continue }
        $k = $line.Substring(0, $idx).Trim()
        $v = $line.Substring($idx + 1).Trim()
        if (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))) {
            if ($v.Length -ge 2) { $v = $v.Substring(1, $v.Length - 2) }
        }
        $map[$k] = $v
    }
    return $map
}

function ConvertFrom-SecureStringPlain {
    param([Security.SecureString]$Secure)
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function New-DeterministicSuffix {
    param([string]$Seed)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Seed)
        $hash = $sha.ComputeHash($bytes)
        return ([System.BitConverter]::ToString($hash) -replace '-', '').ToLower().Substring(0, 8)
    } finally {
        $sha.Dispose()
    }
}

function Get-OrInitDeploymentState {
    param([string]$SubscriptionId)
    $state = @{}
    if (Test-Path $StateFile) {
        $raw = Get-Content -Path $StateFile -Raw -Encoding UTF8
        if ($raw.Trim()) {
            $parsed = $raw | ConvertFrom-Json
            foreach ($prop in $parsed.PSObject.Properties) {
                $state[$prop.Name] = $prop.Value
            }
        }
    }
    $suffix = New-DeterministicSuffix -Seed "$SubscriptionId|$ResourceGroup"
    if (-not $state.ContainsKey('StorageAccountName') -or -not $state['StorageAccountName']) {
        $state['StorageAccountName'] = "infravisionst$suffix"
    }
    if (-not $state.ContainsKey('AcrName') -or -not $state['AcrName']) {
        $state['AcrName'] = "infravisionacr$suffix"
    }
    if (-not $state.ContainsKey('ManagedIdentityName') -or -not $state['ManagedIdentityName']) {
        $state['ManagedIdentityName'] = 'infravision-identity'
    }
    if (-not $state.ContainsKey('LogAnalyticsName') -or -not $state['LogAnalyticsName']) {
        $state['LogAnalyticsName'] = "infravision-logs-$suffix"
    }
    return $state
}

function Save-DeploymentState {
    param([hashtable]$State)
    ($State | ConvertTo-Json -Depth 4) | Set-Content -Path $StateFile -Encoding UTF8
}

function Verify-SavedModelProvenance {
    $modelDir = Join-Path $RepoRoot 'backend\models\structural_defect_detector'
    $pbPath = Join-Path $modelDir 'saved_model.pb'
    $varIndex = Join-Path $modelDir 'variables\variables.index'
    $varData = Join-Path $modelDir 'variables\variables.data-00000-of-00001'
    foreach ($reqFile in @($pbPath, $varIndex, $varData)) {
        if (-not (Test-Path $reqFile)) {
            throw "Required production SavedModel file missing: $reqFile"
        }
    }
    $actualSha = (Get-FileHash -Path $pbPath -Algorithm SHA256).Hash.ToLower()
    if ($actualSha -ne $ExpectedSavedModelSha256) {
        throw "SavedModel SHA-256 mismatch! Expected V2.1 ($ExpectedSavedModelSha256), got $actualSha."
    }
    Write-Host "[OK] Verified V2.1 SavedModel provenance ($ExpectedModelVersion, sha256=$($actualSha.Substring(0,12))...)." -ForegroundColor Green
}

function Ensure-RbacWithRetry {
    param(
        [string]$AssigneeObjectId,
        [string]$RoleName,
        [string]$Scope
    )
    $existing = az role assignment list --assignee $AssigneeObjectId --role $RoleName --scope $Scope --query "[0].id" -o tsv 2>$null
    if ($existing) {
        Write-Host "[OK] RBAC role '$RoleName' already assigned." -ForegroundColor Green
        return
    }
    Write-Host "Assigning RBAC role '$RoleName' (waiting for Managed Identity directory propagation if needed)..." -ForegroundColor Yellow
    $maxAttempts = 8
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        az role assignment create --assignee-object-id $AssigneeObjectId --assignee-principal-type ServicePrincipal --role $RoleName --scope $Scope --only-show-errors | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Assigned '$RoleName' cleanly." -ForegroundColor Green
            return
        }
        Write-Host "  RBAC propagation retry $attempt/$maxAttempts in 10s..." -ForegroundColor DarkYellow
        Start-Sleep -Seconds 10
    }
    throw "Failed assigning RBAC role '$RoleName' after $maxAttempts attempts."
}

Write-Section "InfraVision - Azure Container Apps Deployment"

# 1. Verify local tooling
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI is not installed or not in PATH. Install Docker Desktop (https://www.docker.com/products/docker-desktop/) and start the Docker daemon before running this script."
}
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI ('az') is not installed. Download and install from https://aka.ms/installazurecliwindowsx64, open a new PowerShell terminal, and run 'az login'."
}

Invoke-CheckedCommand "Verify Docker daemon" { docker info --format '{{.ServerVersion}}' | Out-Null }
Write-Host "[OK] Docker CLI and daemon reachable." -ForegroundColor Green

# 2. Verify Azure Authentication & Azure for Students Subscription
$acctJson = az account show -o json 2>$null
if ($LASTEXITCODE -ne 0 -or -not $acctJson) {
    throw "Azure CLI is not authenticated. Run 'az login' and re-run .\deploy_azure.ps1."
}
$account = $acctJson | ConvertFrom-Json
$subName = [string]$account.name
$subId = [string]$account.id
if ($subName -notmatch 'Student') {
    Write-Host "[WARNING] Active Azure subscription: '$subName' ($subId)." -ForegroundColor Red
    throw "Active subscription does not appear to be 'Azure for Students'. Switch with 'az account set --subscription <student-sub-id>' before proceeding."
}
Write-Host "[OK] Verified Azure for Students subscription: $subName ($subId)" -ForegroundColor Green

# 3. Verify V2.1 SavedModel Integrity & Determine Immutable Image Tag
Verify-SavedModelProvenance

$gitSha = 'local'
if (Get-Command git -ErrorAction SilentlyContinue) {
    $shaOut = (git -C $RepoRoot rev-parse --short HEAD 2>$null)
    if ($LASTEXITCODE -eq 0 -and $shaOut) { $gitSha = $shaOut.Trim() }
}
if (-not $ImageTag) {
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddHHmm')
    $ImageTag = "v2.1-$gitSha-$stamp"
}

# 4. Load Non-Secret Config Safely & Check Production Secrets
$envMap = Read-DotEnvMap -Path $EnvFile
$effectiveMongoUri = if ($MongoUri) { $MongoUri.Trim() } elseif ($envMap.ContainsKey('MONGO_URI')) { $envMap['MONGO_URI'] } else { '' }
$isLocalMongo = ($effectiveMongoUri -match 'localhost|127\.0\.0\.1') -or (-not $effectiveMongoUri)

if (-not $Plan -and $isLocalMongo) {
    Write-Host "Local MONGO_URI points to localhost or is empty (cannot be reached from Azure Container Apps)." -ForegroundColor Yellow
    $secMongo = Read-Host -Prompt "Enter your MongoDB Atlas production MONGO_URI (mongodb+srv://...)" -AsSecureString
    $effectiveMongoUri = (ConvertFrom-SecureStringPlain -Secure $secMongo).Trim()
    if (-not $effectiveMongoUri -or ($effectiveMongoUri -match 'localhost|127\.0\.0\.1')) {
        throw "A reachable cloud MongoDB Atlas URI is required for Azure deployment."
    }
}

$secretKey = if ($envMap.ContainsKey('SECRET_KEY') -and $envMap['SECRET_KEY'] -and $envMap['SECRET_KEY'] -notmatch 'local-development') {
    $envMap['SECRET_KEY']
} else {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buf = New-Object byte[] 32
    $rng.GetBytes($buf)
    [Convert]::ToBase64String($buf)
}
$jwtSecret = if ($envMap.ContainsKey('JWT_SECRET_KEY') -and $envMap['JWT_SECRET_KEY'] -and $envMap['JWT_SECRET_KEY'] -notmatch 'local-development') {
    $envMap['JWT_SECRET_KEY']
} else {
    $secretKey
}

$dbName = if ($envMap.ContainsKey('DB_NAME') -and $envMap['DB_NAME']) { $envMap['DB_NAME'] } else { 'civil_infrastructure' }
$confThresh = if ($envMap.ContainsKey('DETECTION_CONFIDENCE_THRESHOLD') -and $envMap['DETECTION_CONFIDENCE_THRESHOLD']) { $envMap['DETECTION_CONFIDENCE_THRESHOLD'] } else { '0.30' }
$smtpHost = if ($envMap.ContainsKey('SMTP_HOST')) { $envMap['SMTP_HOST'] } else { '' }
$smtpPort = if ($envMap.ContainsKey('SMTP_PORT') -and $envMap['SMTP_PORT']) { $envMap['SMTP_PORT'] } else { '587' }
$smtpUser = if ($envMap.ContainsKey('SMTP_USER')) { $envMap['SMTP_USER'] } else { '' }
$smtpPass = if ($envMap.ContainsKey('SMTP_PASSWORD')) { $envMap['SMTP_PASSWORD'] } else { '' }
$smtpSender = if ($envMap.ContainsKey('SMTP_SENDER') -and $envMap['SMTP_SENDER']) { $envMap['SMTP_SENDER'] } else { $smtpUser }
$googleClientId = if ($envMap.ContainsKey('GOOGLE_CLIENT_ID')) { $envMap['GOOGLE_CLIENT_ID'] } else { '' }

# 5. Determine Supported Region & Deterministic Resource Names
$state = Get-OrInitDeploymentState -SubscriptionId $subId
if (-not $Location) {
    $rgLoc = (az group show --name $ResourceGroup --query "location" -o tsv 2>$null)
    if ($rgLoc) {
        $Location = $rgLoc.Trim()
    } else {
        $availableLocs = az account list-locations --query "[].name" -o tsv 2>$null
        $preferredRegions = @('uaenorth', 'southafricanorth', 'westeurope', 'northeurope', 'francecentral', 'eastus', 'eastus2')
        foreach ($candidate in $preferredRegions) {
            if ($availableLocs -contains $candidate) {
                $Location = $candidate
                break
            }
        }
        if (-not $Location) {
            $Location = 'uaenorth'
        }
    }
}

$storageAcct = $state['StorageAccountName']
$identityName = $state['ManagedIdentityName']
$logWsName = $state['LogAnalyticsName']
$acrName = $state['AcrName']

if (-not $GitHubOwner) {
    $originUrl = (git -C $RepoRoot remote get-url origin 2>$null)
    if ($originUrl -match 'github\.com[:/]([^/]+)/') {
        $GitHubOwner = $Matches[1].ToLower()
    }
}
if (-not $GitHubUser) { $GitHubUser = $GitHubOwner }

$fullImage = if ($RegistryMode -eq 'ghcr') {
    if (-not $GitHubOwner) { throw "Specify -GitHubOwner when using -RegistryMode ghcr." }
    "ghcr.io/$GitHubOwner/infravision:$ImageTag"
} else {
    "$acrName.azurecr.io/infravision:$ImageTag"
}

# 6. Preflight Plan & Cost Disclosure
Write-Section "Deployment Plan & Estimated Cost Breakdown (Azure for Students)"
Write-Host "  Subscription         : $subName ($subId)"
Write-Host "  Target Region        : $Location"
Write-Host "  Resource Group       : $ResourceGroup"
Write-Host "  ACA Environment      : $ContainerAppsEnv (Consumption workload profile)"
Write-Host "  Container App        : $ContainerAppName (2.0 vCPU, 4.0 GiB, minReplicas=0, maxReplicas=2, HTTP concurrency=4)"
Write-Host "  Image Reference      : $fullImage"
Write-Host "  AI Model             : $ExpectedModelVersion"
Write-Host "  Blob Storage Account : $storageAcct (Standard_LRS, private container '$BlobContainerName', public access OFF)"
Write-Host "  Managed Identity     : $identityName (Storage Blob Data Contributor)"
Write-Host "  MongoDB Atlas Target : $(if ($isLocalMongo) { 'PENDING (must supply Atlas mongodb+srv:// URI)' } else { 'Configured via Atlas URI (redacted)' })"
Write-Host ""
Write-Host "  Estimated Monthly Usage (charged against your `$100 Azure for Students credit):" -ForegroundColor Yellow
if ($RegistryMode -eq 'ghcr') {
    Write-Host "   - GitHub Container Registry (Private): `$0.00 / month (requires PAT with read:packages/write:packages)"
} else {
    Write-Host "   - Azure Container Registry (Basic)   : ~`$5.00 / month (~`$0.167/day recurring)"
}
Write-Host "   - Azure Container Apps (Consumption) : `$0 idle cost at minReplicas=0; pay-per-use active requests"
Write-Host "   - Azure Blob Storage (Standard_LRS)  : ~`$0.02 / GB per month (~<`$1.00/mo for initial evidence images)"
Write-Host "   - Log Analytics (30-day minimal)     : ~`$0 - `$2 / month (5 GB/mo free ingestion allowance)"

if ($Plan) {
    Write-Host ""
    Write-Host "[PLAN COMPLETE] No Azure resources were created or modified." -ForegroundColor Green
    exit 0
}

if (-not $Yes) {
    $confirm = Read-Host -Prompt "Proceed to provision/update these resources under '$subName'? (y/N)"
    if ($confirm.Trim().ToLower() -notin @('y', 'yes')) {
        Write-Host "Deployment cancelled by user before creating cloud resources." -ForegroundColor Yellow
        exit 0
    }
}

# Persist deterministic resource names only after user approval
Save-DeploymentState -State $state

# 7. Ensure Container Apps Extension & Register Providers
Write-Section "[1/7] Registering Azure Resource Providers & Extensions"
$hasCaExt = az extension list --query "[?name=='containerapp'].name" -o tsv 2>$null
if (-not $hasCaExt) {
    Invoke-CheckedCommand "Install Azure Container Apps CLI extension" {
        az extension add --name containerapp --upgrade --only-show-errors | Out-Null
    }
}
foreach ($ns in @('Microsoft.App', 'Microsoft.OperationalInsights', 'Microsoft.Storage', 'Microsoft.ManagedIdentity')) {
    $regState = az provider show --namespace $ns --query "registrationState" -o tsv 2>$null
    if ($regState -ne 'Registered') {
        Write-Host "Registering $ns..." -ForegroundColor Yellow
        Invoke-CheckedCommand "Register provider $ns" { az provider register --namespace $ns --wait | Out-Null }
    } else {
        Write-Host "[OK] Provider $ns already registered." -ForegroundColor Green
    }
}
if ($RegistryMode -eq 'acr') {
    $acrReg = az provider show --namespace Microsoft.ContainerRegistry --query "registrationState" -o tsv 2>$null
    if ($acrReg -ne 'Registered') {
        Invoke-CheckedCommand "Register Microsoft.ContainerRegistry" { az provider register --namespace Microsoft.ContainerRegistry --wait | Out-Null }
    }
}

# 8. Resource Group, Storage Account & Private Blob Container
Write-Section "[2/7] Provisioning Resource Group & Private Blob Storage"
$rgExists = az group exists --name $ResourceGroup -o tsv
if ($rgExists -ne 'true') {
    Invoke-CheckedCommand "Create resource group $ResourceGroup" {
        az group create --name $ResourceGroup --location $Location --only-show-errors | Out-Null
    }
}

$stExists = az storage account show --name $storageAcct --resource-group $ResourceGroup --query "name" -o tsv 2>$null
if (-not $stExists) {
    Invoke-CheckedCommand "Create StorageV2 LRS account $storageAcct" {
        az storage account create `
            --name $storageAcct `
            --resource-group $ResourceGroup `
            --location $Location `
            --sku Standard_LRS `
            --kind StorageV2 `
            --allow-blob-public-access false `
            --https-only true `
            --min-tls-version TLS1_2 `
            --only-show-errors | Out-Null
    }
}
$blobEndpoint = (az storage account show --name $storageAcct --resource-group $ResourceGroup --query "primaryEndpoints.blob" -o tsv).TrimEnd('/')
$storageScope = (az storage account show --name $storageAcct --resource-group $ResourceGroup --query "id" -o tsv).Trim()

$stKey = (az storage account keys list --resource-group $ResourceGroup --account-name $storageAcct --query "[0].value" -o tsv).Trim()
$containerExists = az storage container exists --name $BlobContainerName --account-name $storageAcct --account-key $stKey --query "exists" -o tsv 2>$null
if ($containerExists -ne 'true') {
    Invoke-CheckedCommand "Create private blob container $BlobContainerName" {
        az storage container create --name $BlobContainerName --account-name $storageAcct --account-key $stKey --public-access off --only-show-errors | Out-Null
    }
}

if ($SyncSeedImages) {
    $localSeedDir = Join-Path $RepoRoot 'backend\uploads'
    if (Test-Path $localSeedDir) {
        Write-Host "Uploading local seed images non-destructively to $BlobContainerName/reports/..." -ForegroundColor Yellow
        Get-ChildItem -Path $localSeedDir -Filter 'seed_*' -File | ForEach-Object {
            $blobName = 'reports/' + $_.Name
            az storage blob upload --account-name $storageAcct --account-key $stKey --container-name $BlobContainerName --name $blobName --file $_.FullName --if-none-match '*' --only-show-errors | Out-Null
        }
    }
}

# 9. Managed Identity & RBAC Permissions
Write-Section "[3/7] Configuring Managed Identity & RBAC"
$idExists = az identity show --name $identityName --resource-group $ResourceGroup --query "id" -o tsv 2>$null
if (-not $idExists) {
    Invoke-CheckedCommand "Create Managed Identity $identityName" {
        az identity create --name $identityName --resource-group $ResourceGroup --location $Location --only-show-errors | Out-Null
    }
}
$identityResourceId = (az identity show --name $identityName --resource-group $ResourceGroup --query "id" -o tsv).Trim()
$identityClientId = (az identity show --name $identityName --resource-group $ResourceGroup --query "clientId" -o tsv).Trim()
$identityPrincipalId = (az identity show --name $identityName --resource-group $ResourceGroup --query "principalId" -o tsv).Trim()

Ensure-RbacWithRetry -AssigneeObjectId $identityPrincipalId -RoleName 'Storage Blob Data Contributor' -Scope $storageScope

# 10. Container Registry Setup
Write-Section "[4/7] Configuring Container Registry ($RegistryMode)"
$ghcrPat = ''
if ($RegistryMode -eq 'acr') {
    $acrExists = az acr show --name $acrName --resource-group $ResourceGroup --query "name" -o tsv 2>$null
    if (-not $acrExists) {
        Invoke-CheckedCommand "Create ACR Basic $acrName" {
            az acr create --name $acrName --resource-group $ResourceGroup --location $Location --sku Basic --admin-enabled false --only-show-errors | Out-Null
        }
    }
    $acrScope = (az acr show --name $acrName --resource-group $ResourceGroup --query "id" -o tsv).Trim()
    Ensure-RbacWithRetry -AssigneeObjectId $identityPrincipalId -RoleName 'AcrPull' -Scope $acrScope
    Invoke-CheckedCommand "Login Docker to ACR" { az acr login --name $acrName | Out-Null }
} else {
    $ghcrPat = $env:GHCR_TOKEN
    if (-not $ghcrPat) {
        $secPat = Read-Host -Prompt "Enter GitHub PAT (read:packages & write:packages) for private GHCR image push/pull" -AsSecureString
        $ghcrPat = (ConvertFrom-SecureStringPlain -Secure $secPat).Trim()
    }
    if (-not $ghcrPat) { throw "GitHub Personal Access Token is required for private GHCR push/pull." }
    $ghcrPat | docker login ghcr.io -u $GitHubUser --password-stdin | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Docker login to ghcr.io failed." }
}

# 11. Build, Inspect & Push Production Container Image
Write-Section "[5/7] Building & Verifying Linux AMD64 Production Container"
Invoke-CheckedCommand "Build production Docker image ($fullImage)" {
    docker build --platform linux/amd64 -t $fullImage $RepoRoot
}

Write-Host "Verifying packaged V2.1 SavedModel checksum inside built image..." -ForegroundColor Yellow
$insideSha = (docker run --rm --entrypoint python $fullImage -c "import hashlib; print(hashlib.sha256(open('/app/backend/models/structural_defect_detector/saved_model.pb','rb').read()).hexdigest())").Trim()
if ($LASTEXITCODE -ne 0 -or $insideSha -ne $ExpectedSavedModelSha256) {
    throw "Container image SavedModel verification failed (expected $ExpectedSavedModelSha256, got '$insideSha')."
}
Write-Host "[OK] Verified V2.1 SavedModel packaged cleanly inside container." -ForegroundColor Green

Invoke-CheckedCommand "Push production image ($fullImage)" {
    docker push $fullImage
}

# 12. Azure Container Apps Environment & Application Deployment
Write-Section "[6/7] Provisioning Container Apps Environment & Deploying Revision"
$envExists = az containerapp env show --name $ContainerAppsEnv --resource-group $ResourceGroup --query "name" -o tsv 2>$null
if (-not $envExists) {
    $wsExists = az monitor log-analytics workspace show --workspace-name $logWsName --resource-group $ResourceGroup --query "customerId" -o tsv 2>$null
    if (-not $wsExists) {
        Invoke-CheckedCommand "Create minimal Log Analytics workspace" {
            az monitor log-analytics workspace create --resource-group $ResourceGroup --workspace-name $logWsName --location $Location --retention-time 30 --only-show-errors | Out-Null
        }
    }
    $wsCustomerId = (az monitor log-analytics workspace show --workspace-name $logWsName --resource-group $ResourceGroup --query "customerId" -o tsv).Trim()
    $wsSharedKey = (az monitor log-analytics workspace get-shared-keys --resource-group $ResourceGroup --workspace-name $logWsName --query "primarySharedKey" -o tsv).Trim()
    Invoke-CheckedCommand "Create Container Apps environment $ContainerAppsEnv" {
        az containerapp env create `
            --name $ContainerAppsEnv `
            --resource-group $ResourceGroup `
            --location $Location `
            --logs-workspace-id $wsCustomerId `
            --logs-workspace-key $wsSharedKey `
            --only-show-errors | Out-Null
    }
}

$envId = (az containerapp env show --name $ContainerAppsEnv --resource-group $ResourceGroup --query "id" -o tsv).Trim()
$appExists = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup --query "name" -o tsv 2>$null
$previousRevision = ''
if ($appExists) {
    $previousRevision = (az containerapp revision list --name $ContainerAppName --resource-group $ResourceGroup --query "[?properties.active].name | [0]" -o tsv 2>$null)
}

$secretKeyJson = $secretKey | ConvertTo-Json -Compress
$jwtSecretJson = $jwtSecret | ConvertTo-Json -Compress
$mongoUriJson = $effectiveMongoUri | ConvertTo-Json -Compress
$dbNameJson = $dbName | ConvertTo-Json -Compress
$smtpHostJson = $smtpHost | ConvertTo-Json -Compress
$smtpUserJson = $smtpUser | ConvertTo-Json -Compress
$smtpSenderJson = $smtpSender | ConvertTo-Json -Compress
$googleClientIdJson = $googleClientId | ConvertTo-Json -Compress

$yamlLines = [System.Collections.Generic.List[string]]::new()
$yamlLines.Add("location: $Location")
$yamlLines.Add("identity:")
$yamlLines.Add("  type: UserAssigned")
$yamlLines.Add("  userAssignedIdentities:")
$yamlLines.Add("    `"$identityResourceId`": {}")
$yamlLines.Add("properties:")
$yamlLines.Add("  managedEnvironmentId: $envId")
$yamlLines.Add("  configuration:")
$yamlLines.Add("    activeRevisionsMode: Single")
$yamlLines.Add("    ingress:")
$yamlLines.Add("      external: true")
$yamlLines.Add("      targetPort: 8080")
$yamlLines.Add("      allowInsecure: false")
$yamlLines.Add("      transport: auto")
$yamlLines.Add("    registries:")
if ($RegistryMode -eq 'acr') {
    $yamlLines.Add("      - server: $acrName.azurecr.io")
    $yamlLines.Add("        identity: $identityResourceId")
} else {
    $yamlLines.Add("      - server: ghcr.io")
    $yamlLines.Add("        username: $GitHubUser")
    $yamlLines.Add("        passwordSecretRef: ghcr-token")
}
$yamlLines.Add("    secrets:")
$yamlLines.Add("      - name: secret-key")
$yamlLines.Add("        value: $secretKeyJson")
$yamlLines.Add("      - name: jwt-secret-key")
$yamlLines.Add("        value: $jwtSecretJson")
$yamlLines.Add("      - name: mongo-uri")
$yamlLines.Add("        value: $mongoUriJson")
if ($smtpPass) {
    $smtpPassJson = $smtpPass | ConvertTo-Json -Compress
    $yamlLines.Add("      - name: smtp-password")
    $yamlLines.Add("        value: $smtpPassJson")
}
if ($RegistryMode -eq 'ghcr') {
    $ghcrPatJson = $ghcrPat | ConvertTo-Json -Compress
    $yamlLines.Add("      - name: ghcr-token")
    $yamlLines.Add("        value: $ghcrPatJson")
}
$yamlLines.Add("  template:")
$yamlLines.Add("    containers:")
$yamlLines.Add("      - name: $ContainerAppName")
$yamlLines.Add("        image: $fullImage")
$yamlLines.Add("        resources:")
$yamlLines.Add("          cpu: 2.0")
$yamlLines.Add("          memory: 4Gi")
$yamlLines.Add("        env:")
$yamlLines.Add("          - name: FLASK_ENV")
$yamlLines.Add("            value: production")
$yamlLines.Add("          - name: DEBUG")
$yamlLines.Add("            value: `"False`"")
$yamlLines.Add("          - name: PORT")
$yamlLines.Add("            value: `"8080`"")
$yamlLines.Add("          - name: DB_NAME")
$yamlLines.Add("            value: $dbNameJson")
$yamlLines.Add("          - name: MONGO_URI")
$yamlLines.Add("            secretRef: mongo-uri")
$yamlLines.Add("          - name: SECRET_KEY")
$yamlLines.Add("            secretRef: secret-key")
$yamlLines.Add("          - name: JWT_SECRET_KEY")
$yamlLines.Add("            secretRef: jwt-secret-key")
$yamlLines.Add("          - name: STORAGE_BACKEND")
$yamlLines.Add("            value: azure")
$yamlLines.Add("          - name: AZURE_STORAGE_ACCOUNT_URL")
$yamlLines.Add("            value: $blobEndpoint")
$yamlLines.Add("          - name: AZURE_STORAGE_CONTAINER")
$yamlLines.Add("            value: $BlobContainerName")
$yamlLines.Add("          - name: AZURE_CLIENT_ID")
$yamlLines.Add("            value: $identityClientId")
$yamlLines.Add("          - name: UPLOAD_FOLDER")
$yamlLines.Add("            value: /tmp/uploads")
$yamlLines.Add("          - name: MODEL_PATH")
$yamlLines.Add("            value: /app/backend/models/structural_defect_detector")
$yamlLines.Add("          - name: MODEL_VERSION")
$yamlLines.Add("            value: $ExpectedModelVersion")
$yamlLines.Add("          - name: DETECTION_CONFIDENCE_THRESHOLD")
$yamlLines.Add("            value: `"$confThresh`"")
$yamlLines.Add("          - name: ENABLE_PRODUCTION_OTP_FALLBACK")
$yamlLines.Add("            value: `"False`"")
$yamlLines.Add("          - name: SMTP_HOST")
$yamlLines.Add("            value: $smtpHostJson")
$yamlLines.Add("          - name: SMTP_PORT")
$yamlLines.Add("            value: `"$smtpPort`"")
$yamlLines.Add("          - name: SMTP_USER")
$yamlLines.Add("            value: $smtpUserJson")
$yamlLines.Add("          - name: SMTP_SENDER")
$yamlLines.Add("            value: $smtpSenderJson")
$yamlLines.Add("          - name: GOOGLE_CLIENT_ID")
$yamlLines.Add("            value: $googleClientIdJson")
if ($smtpPass) {
    $yamlLines.Add("          - name: SMTP_PASSWORD")
    $yamlLines.Add("            secretRef: smtp-password")
}
$yamlLines.Add("        probes:")
$yamlLines.Add("          - type: Startup")
$yamlLines.Add("            httpGet:")
$yamlLines.Add("              path: /ready")
$yamlLines.Add("              port: 8080")
$yamlLines.Add("            initialDelaySeconds: 10")
$yamlLines.Add("            periodSeconds: 10")
$yamlLines.Add("            timeoutSeconds: 5")
$yamlLines.Add("            failureThreshold: 18")
$yamlLines.Add("          - type: Readiness")
$yamlLines.Add("            httpGet:")
$yamlLines.Add("              path: /ready")
$yamlLines.Add("              port: 8080")
$yamlLines.Add("            periodSeconds: 15")
$yamlLines.Add("            timeoutSeconds: 5")
$yamlLines.Add("            failureThreshold: 3")
$yamlLines.Add("          - type: Liveness")
$yamlLines.Add("            httpGet:")
$yamlLines.Add("              path: /health")
$yamlLines.Add("              port: 8080")
$yamlLines.Add("            periodSeconds: 30")
$yamlLines.Add("            timeoutSeconds: 5")
$yamlLines.Add("            failureThreshold: 3")
$yamlLines.Add("    scale:")
$yamlLines.Add("      minReplicas: 0")
$yamlLines.Add("      maxReplicas: 2")
$yamlLines.Add("      rules:")
$yamlLines.Add("        - name: http-scaling-rule")
$yamlLines.Add("          http:")
$yamlLines.Add("            metadata:")
$yamlLines.Add("              concurrentRequests: `"4`"")
$acaYaml = $yamlLines -join "`n"

$tempYaml = Join-Path ([System.IO.Path]::GetTempPath()) "infravision-aca-$PID.yaml"
try {
    $acaYaml | Set-Content -Path $tempYaml -Encoding UTF8
    if (-not $appExists) {
        Invoke-CheckedCommand "Create Azure Container App $ContainerAppName" {
            az containerapp create --name $ContainerAppName --resource-group $ResourceGroup --yaml $tempYaml --only-show-errors | Out-Null
        }
    } else {
        Invoke-CheckedCommand "Update Azure Container App $ContainerAppName" {
            az containerapp update --name $ContainerAppName --resource-group $ResourceGroup --yaml $tempYaml --only-show-errors | Out-Null
        }
    }
} catch {
    Write-Host "[ERROR] Deployment step failed. Fetching recent Container App console logs..." -ForegroundColor Red
    az containerapp logs show --name $ContainerAppName --resource-group $ResourceGroup --tail 80 2>$null
    throw
} finally {
    if (Test-Path $tempYaml) {
        Remove-Item -Path $tempYaml -Force -ErrorAction SilentlyContinue
    }
}

# 13. Post-Deploy Verification
Write-Section "[7/7] Verifying Live Production HTTPS Endpoints"
$fqdn = (az containerapp show --name $ContainerAppName --resource-group $ResourceGroup --query "properties.configuration.ingress.fqdn" -o tsv).Trim()
$latestRevision = (az containerapp show --name $ContainerAppName --resource-group $ResourceGroup --query "properties.latestRevisionName" -o tsv).Trim()
$appUrl = "https://$fqdn"

Write-Host "  Public URL       : $appUrl" -ForegroundColor Green
Write-Host "  Active Revision  : $latestRevision" -ForegroundColor Green
if ($previousRevision -and ($previousRevision -ne $latestRevision)) {
    Write-Host "  Rollback Ref     : $previousRevision (az containerapp revision activate --name $ContainerAppName --resource-group $ResourceGroup --revision $previousRevision)" -ForegroundColor DarkCyan
}

foreach ($ep in @('/health', '/ready', '/api/health', '/api/reports/public/recent?limit=3', '/')) {
    $target = "$appUrl$ep"
    $resp = Invoke-WebRequest -Uri $target -UseBasicParsing -TimeoutSec 60
    if ($resp.StatusCode -ne 200) {
        throw "Live health check failed at $target (HTTP $($resp.StatusCode))"
    }
    Write-Host "[OK] $target -> HTTP $($resp.StatusCode)" -ForegroundColor Green
}

Write-Section "Azure Production Deployment Completed Successfully"

