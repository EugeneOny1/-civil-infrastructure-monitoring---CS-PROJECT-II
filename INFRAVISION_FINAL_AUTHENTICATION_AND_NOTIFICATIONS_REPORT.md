# InfraVision — Final Authentication, ACS Email OTP Activation & Notifications Report

**Date:** 2026-11-19  
**Branch:** `app-development`  
**Target Production URL:** [https://infravision.graybush-fed30b34.uaenorth.azurecontainerapps.io](https://infravision.graybush-fed30b34.uaenorth.azurecontainerapps.io)  
**Final Deployment Readiness Verdict:** **READY FOR AUTHORIZED COMMIT, DEPLOYMENT & LIVE ACS CONFIGURATION** *(Real ACS delivery remains **UNVERIFIED** until the Azure ACS resource is provisioned, secrets/env vars are attached to Container App `infravision`, and a live post-deploy send test is executed)*

---

## 1. Confirmed Production SMTP Diagnosis & Decision

Direct live testing inside the deployed Azure Container App (`infravision`) confirmed:
- Gmail SMTP port `587` and port `465`: TCP and TLS handshakes succeeded.
- SMTP credentials are present in the container.
- Gmail SMTP authentication failed with `SMTPServerDisconnected`.
- `email_service.verify_smtp_health()` returned `Degraded (SMTPServerDisconnected)`.

**Authorized Decision:** Activate **Azure Communication Services (ACS) Email** as the primary production OTP transport (over HTTPS port 443), while retaining Gmail SMTP as an optional secondary transport and keeping zero production OTP fallback/bypass.

---

## 2. Exact Files Changed & Justification (Minimal Change Set)

| File | Justification |
|---|---|
| `requirements.txt` | Restored `azure-communication-email>=1.0.0` so the production `Dockerfile` (`COPY requirements.txt` → `pip install -r requirements.txt`) packages the official Azure Communication Email SDK into the container image. |
| `backend/requirements.txt` | Restored `azure-communication-email>=1.0.0` to maintain dependency parity with root `requirements.txt`. |
| `backend/app/services/email_service.py` | Reused the existing ACS implementation; added `is_acs_enabled()` helper and explicit credential-free misconfiguration diagnostics (`Misconfigured ACS` in `verify_smtp_health()`, `MissingACSConfiguration` in `send_otp_email()`) when `ENABLE_ACS_EMAIL=true` is set without `ACS_EMAIL_CONNECTION_STRING` or `ACS_EMAIL_SENDER`. Never logs OTPs or credentials. |
| `tests/test_azure_deployment_readiness.py` | Extended `test_13` to verify `backend/scripts/prepare_aca_update.py` preserves `acs-email-connection-string` secret and `ENABLE_ACS_EMAIL`, `ACS_EMAIL_CONNECTION_STRING`, `ACS_EMAIL_SENDER` env vars across deployments; extended `test_15` to verify missing ACS config fails closed (no auth bypass) and `azure-communication-email` is listed in both requirements files. |
| `INFRAVISION_FINAL_AUTHENTICATION_AND_NOTIFICATIONS_REPORT.md` | Updated completion report documenting ACS activation readiness, test results, and outstanding Azure portal configuration steps. |

---

## 3. Confirmation of Existing ACS Code Reuse & Security Policy

- **Reused existing implementation:** All ACS configuration (`ENABLE_ACS_EMAIL`, `ACS_EMAIL_CONNECTION_STRING`, `ACS_EMAIL_SENDER` in `backend/app/config.py`) and HTTPS send logic (`EmailClient.from_connection_string(...).begin_send(...)` in `backend/app/services/email_service.py`) were reused without duplicating code or introducing any other provider (no Brevo, SendGrid, or Resend).
- **Explicit feature flag preserved:** ACS activates **only** when `ENABLE_ACS_EMAIL=true` and both `ACS_EMAIL_CONNECTION_STRING` and `ACS_EMAIL_SENDER` are configured.
- **No production OTP bypass:** `ProductionConfig.ENABLE_DEMO_OTP = False`; `is_demo_mode()` and `should_expose_fallback_otp()` unconditionally return `False` in production. Delivery failures return **HTTP 503** without persisting an undelivered OTP or issuing a JWT.
- **OTP single-use & rate limits preserved:** Cryptographic 6-digit OTPs, 5-minute expiry, 60-second resend cooldown, 5 max attempts, 5 sends/hour cap, and immediate single-use invalidation after successful verification remain intact.
- **Google OAuth & privileged RBAC preserved:** Eligible Citizens sign in directly via Google without InfraVision OTP; Engineers/Admins and email/password logins enforce OTP.

---

## 4. Test Execution Summary (100% Isolated Mock Fixtures)

Executed the complete established regression suite (`python -m unittest discover -s tests -v`) with isolated local test URIs (`MONGO_URI=mongodb://127.0.0.1:27017/civil_infrastructure_test`):

| Test Suite | Executed | Passed | Failed | Blocked | Notes |
|---|---|---|---|---|---|
| `tests/test_azure_deployment_readiness.py` | 16 | 16 | 0 | 0 | Verified `test_13` (ACA secret/env preservation for ACS), `test_14` (no prod OTP bypass + SMTP 587/465), `test_15` (ACS enabled, missing ACS config fails closed, `azure-communication-email` in requirements), `test_16` (Citizen notifications). |
| `tests/test_auth_and_maps.py` | 20 | 20 | 0 | 0 | Verified OTP generation, expiry, single-use replay prevention, resend limits, Google Citizen direct login, privileged 2FA, and maps privacy. |
| Remaining 18 regression suites (`test_api_workflow`, `test_cloud_run_deployment_readiness`, `test_completion_pass`, `test_emergency_fix`, `test_eval_public_reports`, `test_final_acceptance_pass`, `test_final_enhancement_pass`, `test_final_intelligence_and_privacy`, `test_final_lifecycle_and_workflow`, `test_final_monitoring_refinement`, `test_inference`, `test_inspection_progress`, `test_map_hotspot`, `test_monitoring_intelligence_workspace`, `test_rvsi_and_engineering_assessment`, `test_targeted_refinement_pass`, `test_ui_cohesion`, `test_validation_and_severity`) | 152 | 151 | 0 | 1 | `test_completion_pass.py:test_03_rebalanced_demo_dataset_and_valid_images` requires a local `127.0.0.1:27017` MongoDB daemon (provisioned automatically in GitHub Actions CI via `mongo:7`). |
| **TOTAL** | **188** | **187** | **0** | **1** | **0 failures; 187/187 runnable offline tests passed.** |

**Database Isolation Confirmation:** All automated tests ran against the in-memory mock store (`TESTING=True`). **Zero** records were created, updated, or deleted in production MongoDB Atlas.

---

## 5. Outstanding Azure Configuration Requirements (Manual / Authorized)

To activate live ACS Email OTP delivery on Container App **`infravision`** (`infravision-rg`) after deploying the updated Docker image:

1. **Provision ACS Email in Azure Portal** (in `infravision-rg`, if not already created):
   - Create an **Email Communication Service** → **Provision domains** → **Add a free Azure subdomain** (provides `DoNotReply@<id>.azurecomm.net`).
   - Create a **Communication Service** → **Email → Domains → Connect domain** → link the Email Communication Service & subdomain.
   - Copy the **Connection string** from **Communication Service → Keys**.
2. **Configure Container App `infravision`:**
   - **Secrets:** Add secret `acs-email-connection-string` containing the ACS connection string.
   - **Environment variables:**
     - `ENABLE_ACS_EMAIL` = `true`
     - `ACS_EMAIL_CONNECTION_STRING` → Secret reference: `acs-email-connection-string`
     - `ACS_EMAIL_SENDER` = `DoNotReply@<your-provisioned-subdomain>.azurecomm.net`
   - Confirmed via `test_13`: `backend/scripts/prepare_aca_update.py` and `.github/workflows/deploy-azure.yml` preserve all existing Container App secrets and environment variables on every future deployment.
3. **Post-Deploy Live Verification (Console Probe):**
   ```bash
   python3 -c "from backend.app.services.email_service import email_service; print(email_service.verify_smtp_health())"
   ```
   Expected output: `(True, 'Operational (Azure Communication Services Email)')`.

---

## 6. Preservation of Existing Functionality & Remaining Blockers

- **Preserved 100% untouched:** V2.1 SSD-MobileNetV2 SavedModel, inference pipeline, RVSI formulas, MongoDB Atlas records/accounts/emails/roles, canonical report lifecycle, engineering reviews, inspection notebook, Leaflet maps, Citizen lifecycle notifications, Google OAuth, and Azure ACR CI/CD workflow.
- **Remaining Blockers to Live Production OTP Delivery:**
  1. Deploying the updated Docker image containing `azure-communication-email>=1.0.0`.
  2. Configuring the 3 Azure Container App settings (`ENABLE_ACS_EMAIL=true`, secret `acs-email-connection-string` → `ACS_EMAIL_CONNECTION_STRING`, and `ACS_EMAIL_SENDER`).
  3. Executing one authorized live login/OTP send verification after deployment to confirm end-to-end inbox delivery.

**Status:** Nothing has been staged, committed, pushed, or deployed. Awaiting your explicit authorization.
