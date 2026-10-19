/**
 * App Module - Routing, Authentication State, Role-Based UI Guarding, 2FA Flow,
 * Google Sign-In, Password Strength Validation, Map & Cohesive Admin Oversight.
 */
const App = {
    currentUser: null,
    pending2FA: null,
    resendCooldownTimer: null,

    init() {
        this.bindNavigation();
        this.bindAuthEvents();
        this.bindPasswordStrengthMeter();
        this.bindEbkCategorySelector();
        
        // Initialize submodules
        if (window.Submission) window.Submission.init();
        if (window.Dashboard) window.Dashboard.init();
        if (window.Review) window.Review.init();
        if (window.DefectMap) window.DefectMap.init();

        // Restore session or default to citizen view
        this.restoreSession();
        this.checkBackendStatus();
    },

    restoreSession() {
        this.currentUser = window.Api.getUser();
        this.updateSessionUI();
        
        const urlParams = new URLSearchParams(window.location.search);
        const reportParam = urlParams.get('report_id');

        if (this.currentUser) {
            if (reportParam && (this.currentUser.role === 'engineer' || this.currentUser.role === 'admin')) {
                this.navigateTo('view-review', { reportId: reportParam });
            } else if (this.currentUser.role === 'engineer' && this.currentUser.verification_status === 'verified') {
                this.navigateTo('view-dashboard');
            } else if (this.currentUser.role === 'admin') {
                this.navigateTo('view-admin-dashboard');
            } else {
                this.navigateTo('view-submit');
            }
        } else {
            this.navigateTo('view-submit');
        }
    },

    updateSessionUI() {
        const user = this.currentUser;
        const profileBadge = document.getElementById('userProfileBadge');
        const authButtons = document.getElementById('authButtonsGroup');
        const nameEl = document.getElementById('currentUserName');
        const roleEl = document.getElementById('currentUserRole');
        const verifEl = document.getElementById('currentVerificationBadge');
        const dotEl = document.getElementById('userStatusDot');

        const citizenTabs = document.querySelectorAll('.role-citizen');
        const engineerTabs = document.querySelectorAll('.role-engineer');
        const adminTabs = document.querySelectorAll('.role-admin');

        if (user) {
            if (profileBadge) profileBadge.classList.remove('hidden');
            if (authButtons) authButtons.classList.add('hidden');

            if (nameEl) nameEl.textContent = user.name || user.email;
            if (roleEl) roleEl.textContent = user.role.toUpperCase();

            const isVerified = user.verification_status === 'verified';
            if (verifEl) {
                verifEl.textContent = isVerified ? 'Verified' : 'Pending Verification';
                verifEl.className = `verification-badge ${isVerified ? 'verified' : 'pending'}`;
            }
            if (dotEl) {
                dotEl.className = `user-dot ${isVerified ? 'verified' : 'pending'}`;
            }

            // Exact, explicit Role-Based Navigation:
            if (user.role === 'admin') {
                // Admin ONLY sees Admin Dashboard and User Governance
                document.getElementById('tabSubmit')?.classList.add('hidden');
                document.getElementById('tabTracking')?.classList.add('hidden');
                document.getElementById('tabMap')?.classList.add('hidden');
                document.getElementById('tabDashboard')?.classList.add('hidden');
                document.getElementById('tabReview')?.classList.add('hidden');
                document.getElementById('tabAdminDashboard')?.classList.remove('hidden');
                document.getElementById('tabAdmin')?.classList.remove('hidden');
            } else if (user.role === 'engineer') {
                // Engineer sees: Report Defect, My Reports, Infrastructure Map, Monitoring Dashboard, Defect Review
                document.getElementById('tabSubmit')?.classList.remove('hidden');
                document.getElementById('tabTracking')?.classList.remove('hidden');
                document.getElementById('tabMap')?.classList.remove('hidden');
                document.getElementById('tabAdminDashboard')?.classList.add('hidden');
                document.getElementById('tabAdmin')?.classList.add('hidden');
                if (isVerified) {
                    document.getElementById('tabDashboard')?.classList.remove('hidden');
                    document.getElementById('tabReview')?.classList.remove('hidden');
                } else {
                    document.getElementById('tabDashboard')?.classList.add('hidden');
                    document.getElementById('tabReview')?.classList.add('hidden');
                }
            } else {
                // Citizen sees: Report Defect, My Reports, and Infrastructure Map
                document.getElementById('tabSubmit')?.classList.remove('hidden');
                document.getElementById('tabTracking')?.classList.remove('hidden');
                document.getElementById('tabMap')?.classList.remove('hidden');
                document.getElementById('tabDashboard')?.classList.add('hidden');
                document.getElementById('tabReview')?.classList.add('hidden');
                document.getElementById('tabAdminDashboard')?.classList.add('hidden');
                document.getElementById('tabAdmin')?.classList.add('hidden');
            }
        } else {
            // Unauthenticated Guest: public Citizen views
            if (profileBadge) profileBadge.classList.add('hidden');
            if (authButtons) authButtons.classList.remove('hidden');
            document.getElementById('tabSubmit')?.classList.remove('hidden');
            document.getElementById('tabTracking')?.classList.remove('hidden');
            document.getElementById('tabMap')?.classList.remove('hidden');
            document.getElementById('tabDashboard')?.classList.add('hidden');
            document.getElementById('tabReview')?.classList.add('hidden');
            document.getElementById('tabAdminDashboard')?.classList.add('hidden');
            document.getElementById('tabAdmin')?.classList.add('hidden');
        }
    },

    bindNavigation() {
        const tabs = document.querySelectorAll('.nav-tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const viewId = tab.getAttribute('data-view');
                this.navigateTo(viewId);
            });
        });

        // Brand Home click
        const brandHome = document.getElementById('brandHome');
        if (brandHome) {
            brandHome.addEventListener('click', () => {
                this.navigateTo('view-submit');
            });
        }

        // Tracking refresh
        const refreshBtn = document.getElementById('btnRefreshTracking');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadTrackingData());
        }

        // Admin Dashboard refresh
        const refreshAdminDashBtn = document.getElementById('btnRefreshAdminDashboard');
        if (refreshAdminDashBtn) {
            refreshAdminDashBtn.addEventListener('click', () => this.loadAdminDashboard());
        }

        // Pending verification shortcut
        const btnGoVerification = document.getElementById('btnGoToVerification');
        if (btnGoVerification) {
            btnGoVerification.addEventListener('click', () => {
                this.navigateTo('view-admin');
            });
        }

        // Post-submit redirect button
        const viewTrackingBtn = document.getElementById('btnViewTrackingAfterSubmit');
        if (viewTrackingBtn) {
            viewTrackingBtn.addEventListener('click', () => {
                this.navigateTo('view-tracking');
            });
        }

        // Admin role filter & user search
        const adminRoleFilter = document.getElementById('adminRoleFilter');
        if (adminRoleFilter) {
            adminRoleFilter.addEventListener('change', () => this.loadAdminData());
        }
        const adminUserSearch = document.getElementById('adminUserSearch');
        if (adminUserSearch) {
            adminUserSearch.addEventListener('input', () => this.loadAdminData());
        }
    },

    bindAuthEvents() {
        // Sign In / Register buttons in header
        const btnOpenLogin = document.getElementById('btnOpenLogin');
        const btnOpenRegister = document.getElementById('btnOpenRegister');
        const btnLogout = document.getElementById('btnLogout');

        if (btnOpenLogin) {
            btnOpenLogin.addEventListener('click', () => this.showAuthView('login'));
        }
        if (btnOpenRegister) {
            btnOpenRegister.addEventListener('click', () => this.showAuthView('register'));
        }
        if (btnLogout) {
            btnLogout.addEventListener('click', () => {
                window.Api.clearSession();
                this.currentUser = null;
                this.pending2FA = null;
                this.updateSessionUI();
                this.showToast('Logged out successfully.');
                this.navigateTo('view-submit');
            });
        }

        // Auth view tabs (Sign In vs Create Account)
        const tabLogin = document.getElementById('tabAuthLogin');
        const tabRegister = document.getElementById('tabAuthRegister');
        const loginForm = document.getElementById('loginForm');
        const registerForm = document.getElementById('registerForm');
        const twoFactorForm = document.getElementById('twoFactorForm');
        const authTabsRow = document.getElementById('authTabsRow');

        if (tabLogin && tabRegister) {
            tabLogin.addEventListener('click', () => {
                tabLogin.classList.add('active');
                tabRegister.classList.remove('active');
                loginForm.classList.remove('hidden');
                registerForm.classList.add('hidden');
                if (twoFactorForm) twoFactorForm.classList.add('hidden');
                if (authTabsRow) authTabsRow.classList.remove('hidden');
            });
            tabRegister.addEventListener('click', () => {
                tabRegister.classList.add('active');
                tabLogin.classList.remove('active');
                registerForm.classList.remove('hidden');
                loginForm.classList.add('hidden');
                if (twoFactorForm) twoFactorForm.classList.add('hidden');
                if (authTabsRow) authTabsRow.classList.remove('hidden');
            });
        }

        // Quick test account autofill chips
        const chipCitizen = document.getElementById('chipCitizen');
        const chipEngineer = document.getElementById('chipEngineer');
        const chipAdmin = document.getElementById('chipAdmin');

        if (chipCitizen) {
            chipCitizen.addEventListener('click', () => {
                document.getElementById('loginEmail').value = 'citizen@strathmore.edu';
                document.getElementById('loginPassword').value = 'Citizen@123';
            });
        }
        if (chipEngineer) {
            chipEngineer.addEventListener('click', () => {
                document.getElementById('loginEmail').value = 'engineer@kenha.go.ke';
                document.getElementById('loginPassword').value = 'Engineer@123';
            });
        }
        if (chipAdmin) {
            chipAdmin.addEventListener('click', () => {
                document.getElementById('loginEmail').value = 'admin@infravision.ke';
                document.getElementById('loginPassword').value = 'Admin@123';
            });
        }

        // Continue with Google Button
        const btnGoogle = document.getElementById('btnGoogleSignIn');
        if (btnGoogle) {
            btnGoogle.addEventListener('click', async () => {
                try {
                    this.showToast("Connecting to Google Identity Services...");
                    const data = await window.Api.loginWithGoogle('demo_google_gis_credential_token');
                    this.currentUser = data.user;
                    this.updateSessionUI();
                    this.showToast(`Signed in with Google as ${data.user.name || data.user.email}!`);
                    this.routeUserAfterAuth(data.user);
                } catch (err) {
                    console.error("Google sign-in error:", err);
                    this.showToast(err.message || "Google sign in was cancelled or failed.", true);
                }
            });
        }

        // Dynamic registration role toggle
        const regRoleSelect = document.getElementById('regRole');
        const engineerFieldsContainer = document.getElementById('engineerFieldsContainer');
        const regNameInput = document.getElementById('regName');

        if (regRoleSelect) {
            regRoleSelect.addEventListener('change', (e) => {
                const role = e.target.value;
                if (role === 'engineer') {
                    if (engineerFieldsContainer) engineerFieldsContainer.classList.remove('hidden');
                    if (regNameInput) regNameInput.placeholder = "e.g., Eng. Jane Doe";
                } else {
                    if (engineerFieldsContainer) engineerFieldsContainer.classList.add('hidden');
                    if (regNameInput) regNameInput.placeholder = "Full name";
                }
            });
        }

        // Login Form Submission
        if (loginForm) {
            loginForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const email = document.getElementById('loginEmail').value.trim();
                const password = document.getElementById('loginPassword').value.trim();
                const submitBtn = document.getElementById('btnLoginSubmit');
                
                submitBtn.disabled = true;
                submitBtn.textContent = 'Authenticating...';

                try {
                    const data = await window.Api.login(email, password);

                    // Check if 2FA challenge is returned
                    if (data.require_2fa) {
                        this.pending2FA = {
                            email: data.email,
                            role: data.role,
                            demo_otp: data.demo_otp
                        };

                        loginForm.classList.add('hidden');
                        if (authTabsRow) authTabsRow.classList.add('hidden');
                        if (twoFactorForm) {
                            twoFactorForm.classList.remove('hidden');
                            document.getElementById('twoFactorEmailDisplay').textContent = data.email;
                            document.getElementById('twoFactorOtpInput').value = '';
                            document.getElementById('twoFactorHelpText').innerHTML = 
                                `Dispatched verification passcode: <strong>${data.demo_otp || '123456'}</strong> (or enter test code <strong>123456</strong>)`;
                        }
                        this.showToast(data.message || 'Two-Factor Authentication required.');
                        return;
                    }

                    // Direct login
                    this.currentUser = data.user;
                    this.updateSessionUI();
                    this.showToast(`Welcome, ${data.user.name || data.user.email}!`);
                    this.routeUserAfterAuth(data.user);
                } catch (err) {
                    this.showToast(err.message || 'Login failed.', true);
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Sign In to InfraVision';
                }
            });
        }

        // Two-Factor Authentication Form Handling
        if (twoFactorForm) {
            const btnFillDemo = document.getElementById('btnFillDemoOtp');
            if (btnFillDemo) {
                btnFillDemo.addEventListener('click', () => {
                    const code = (this.pending2FA && this.pending2FA.demo_otp) ? this.pending2FA.demo_otp : '123456';
                    document.getElementById('twoFactorOtpInput').value = code;
                    this.showToast("Test security code filled.");
                });
            }

            const btnResend = document.getElementById('btnResendOtp');
            if (btnResend) {
                btnResend.addEventListener('click', async () => {
                    if (!this.pending2FA || !this.pending2FA.email) return;
                    btnResend.disabled = true;
                    try {
                        const res = await window.Api.resendOtp(this.pending2FA.email);
                        if (res.demo_otp) this.pending2FA.demo_otp = res.demo_otp;
                        this.showToast(res.message || "New 2FA security code dispatched.");
                        this.startResendCooldown(60);
                    } catch (err) {
                        this.showToast(err.message || "Failed to resend code.", true);
                        btnResend.disabled = false;
                    }
                });
            }

            const btnCancel2FA = document.getElementById('btnCancelTwoFactor');
            if (btnCancel2FA) {
                btnCancel2FA.addEventListener('click', () => {
                    this.pending2FA = null;
                    twoFactorForm.classList.add('hidden');
                    loginForm.classList.remove('hidden');
                    if (authTabsRow) authTabsRow.classList.remove('hidden');
                });
            }

            twoFactorForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                if (!this.pending2FA || !this.pending2FA.email) {
                    this.showToast("No active 2FA session. Please sign in again.", true);
                    this.showAuthView('login');
                    return;
                }

                const otpCode = document.getElementById('twoFactorOtpInput').value.trim();
                const btnVerify = document.getElementById('btnVerifyTwoFactor');

                btnVerify.disabled = true;
                btnVerify.textContent = 'Verifying Code...';

                try {
                    const data = await window.Api.verify2FA(this.pending2FA.email, otpCode);
                    this.currentUser = data.user;
                    this.pending2FA = null;
                    this.updateSessionUI();
                    this.showToast("2FA verification successful. Access granted!");
                    
                    twoFactorForm.classList.add('hidden');
                    if (authTabsRow) authTabsRow.classList.remove('hidden');
                    loginForm.classList.remove('hidden');

                    this.routeUserAfterAuth(data.user);
                } catch (err) {
                    this.showToast(err.message || 'Invalid 2FA verification code.', true);
                } finally {
                    btnVerify.disabled = false;
                    btnVerify.textContent = 'Verify & Complete Login';
                }
            });
        }

        // Register Form Submission
        if (registerForm) {
            registerForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const name = document.getElementById('regName').value.trim();
                const email = document.getElementById('regEmail').value.trim();
                const password = document.getElementById('regPassword').value.trim();
                const role = document.getElementById('regRole').value;
                const organization = document.getElementById('regOrg')?.value.trim() || '';
                const professional_category = document.getElementById('regEbkCategory')?.value || '';
                const professional_reg_no = document.getElementById('regLicense')?.value.trim() || '';
                const phone = document.getElementById('regPhone')?.value.trim() || '';
                const two_factor_enabled = role === 'engineer' || role === 'admin' ? true : (document.getElementById('regTwoFactor')?.checked || false);

                const submitBtn = document.getElementById('btnRegisterSubmit');

                submitBtn.disabled = true;
                submitBtn.textContent = 'Creating Account...';

                try {
                    const data = await window.Api.register({
                        name,
                        email,
                        password,
                        role,
                        organization,
                        professional_category,
                        professional_reg_no,
                        phone,
                        two_factor_enabled
                    });

                    this.currentUser = data.user;
                    this.updateSessionUI();
                    this.showToast(data.message || 'Account created successfully!');

                    if (role === 'engineer') {
                        this.showToast("Engineer account submitted for administrative accreditation verification.", true);
                    }
                    this.navigateTo('view-submit');
                } catch (err) {
                    this.showToast(err.message || 'Registration failed.', true);
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Create Account';
                }
            });
        }
    },

    bindPasswordStrengthMeter() {
        const passInput = document.getElementById('regPassword');
        if (!passInput) return;

        passInput.addEventListener('input', (e) => {
            const val = e.target.value;
            const hasLen = val.length >= 8;
            const hasUpper = /[A-Z]/.test(val);
            const hasLower = /[a-z]/.test(val);
            const hasSpecial = /[\d!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(val);

            const ruleLenEl = document.getElementById('ruleLength');
            const ruleUpEl = document.getElementById('ruleUpper');
            const ruleLowEl = document.getElementById('ruleLower');
            const ruleNumEl = document.getElementById('ruleNumber');

            if (ruleLenEl) ruleLenEl.className = `strength-item ${hasLen ? 'passed' : 'failed'}`;
            if (ruleUpEl) ruleUpEl.className = `strength-item ${hasUpper ? 'passed' : 'failed'}`;
            if (ruleLowEl) ruleLowEl.className = `strength-item ${hasLower ? 'passed' : 'failed'}`;
            if (ruleNumEl) ruleNumEl.className = `strength-item ${hasSpecial ? 'passed' : 'failed'}`;

            const score = [hasLen, hasUpper, hasLower, hasSpecial].filter(Boolean).length;
            const segs = [document.getElementById('seg1'), document.getElementById('seg2'), document.getElementById('seg3'), document.getElementById('seg4')];

            segs.forEach((seg, i) => {
                if (!seg) return;
                seg.className = 'strength-bar-seg';
                if (i < score) {
                    if (score === 1) seg.classList.add('active-weak');
                    else if (score === 2) seg.classList.add('active-fair');
                    else if (score === 3) seg.classList.add('active-good');
                    else if (score === 4) seg.classList.add('active-strong');
                }
            });
        });
    },

    bindEbkCategorySelector() {
        const catSelect = document.getElementById('regEbkCategory');
        const licInput = document.getElementById('regLicense');
        const helpText = document.getElementById('ebkHelpText');

        if (!catSelect || !licInput) return;

        catSelect.addEventListener('change', (e) => {
            const cat = e.target.value;
            if (cat === 'Graduate Engineer') {
                licInput.placeholder = 'e.g., B24512';
                if (helpText) helpText.textContent = 'Format: Letter B followed by digits (e.g. B24512)';
            } else if (cat === 'Professional Engineer') {
                licInput.placeholder = 'e.g., A3947';
                if (helpText) helpText.textContent = 'Format: Letter A followed by digits (e.g. A3947)';
            } else if (cat === 'Consulting Engineer') {
                licInput.placeholder = 'e.g., E475';
                if (helpText) helpText.textContent = 'Format: Letter E followed by digits (e.g. E475)';
            }
        });
    },

    startResendCooldown(seconds) {
        const btn = document.getElementById('btnResendOtp');
        const timerText = document.getElementById('resendTimerText');
        if (!btn || !timerText) return;

        let remaining = seconds;
        btn.disabled = true;
        timerText.textContent = `${remaining}s`;

        if (this.resendCooldownTimer) clearInterval(this.resendCooldownTimer);

        this.resendCooldownTimer = setInterval(() => {
            remaining -= 1;
            if (remaining <= 0) {
                clearInterval(this.resendCooldownTimer);
                btn.disabled = false;
                timerText.textContent = 'Ready';
            } else {
                timerText.textContent = `${remaining}s`;
            }
        }, 1000);
    },

    routeUserAfterAuth(user) {
        if (!user) return;
        if (user.role === 'engineer') {
            if (user.verification_status === 'verified') {
                this.navigateTo('view-dashboard');
            } else {
                this.showToast("Engineer account pending administrative verification. Professional tools locked.", true);
                this.navigateTo('view-submit');
            }
        } else if (user.role === 'admin') {
            this.navigateTo('view-admin-dashboard');
        } else {
            this.navigateTo('view-submit');
        }
    },

    showAuthView(mode = 'login') {
        const tabLogin = document.getElementById('tabAuthLogin');
        const tabRegister = document.getElementById('tabAuthRegister');
        const twoFactorForm = document.getElementById('twoFactorForm');
        const authTabsRow = document.getElementById('authTabsRow');

        if (twoFactorForm) twoFactorForm.classList.add('hidden');
        if (authTabsRow) authTabsRow.classList.remove('hidden');

        if (mode === 'login') {
            if (tabLogin) tabLogin.click();
        } else {
            if (tabRegister) tabRegister.click();
        }
        this.navigateTo('view-auth');
    },

    navigateTo(viewId, params = {}) {
        // Toggle tab active class
        document.querySelectorAll('.nav-tab').forEach(t => {
            t.classList.toggle('active', t.getAttribute('data-view') === viewId);
        });

        // Toggle view sections
        document.querySelectorAll('.view-section').forEach(sec => {
            sec.classList.toggle('active', sec.id === viewId);
        });

        // View-specific data loads
        if (viewId === 'view-tracking') {
            this.loadTrackingData();
        } else if (viewId === 'view-map') {
            if (window.DefectMap) window.DefectMap.loadMapData();
        } else if (viewId === 'view-dashboard') {
            if (window.Dashboard) window.Dashboard.loadDashboardData();
        } else if (viewId === 'view-review') {
            const reportId = params?.reportId || window.Review.targetReportId;
            if (window.Review) window.Review.loadCaseworkList(reportId);
            window.Review.targetReportId = null;
        } else if (viewId === 'view-admin-dashboard') {
            this.loadAdminDashboard();
        } else if (viewId === 'view-admin') {
            this.loadAdminData();
        }
    },

    async checkBackendStatus() {
        try {
            const health = await window.Api.checkHealth();
            console.log("[InfraVision] Connected to backend service:", health);
        } catch (e) {
            console.warn("[InfraVision] Running in standalone frontend mode:", e);
        }
    },

    // Citizen Tracking View (FR-08)
    async loadTrackingData() {
        const tbody = document.getElementById('trackingTableBody');
        if (!tbody) return;

        if (!this.currentUser) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align:center; padding: 2.5rem; color: #86868b;">
                        Please <button type="button" class="btn-micro btn-accent" onclick="window.App.showAuthView('login')">Sign In</button> to view your submitted infrastructure defect reports.
                    </td>
                </tr>`;
            return;
        }

        try {
            const data = await window.Api.getMyReports();
            const reports = data.reports || [];

            if (reports.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="6" style="text-align:center; padding: 2.5rem; color: #86868b;">
                            No defect reports submitted yet. Use the 'Report Defect' tab to photograph and submit an infrastructure defect!
                        </td>
                    </tr>`;
                return;
            }

            tbody.innerHTML = reports.map(item => {
                const rep = item.report;
                const ai = item.assessment || {};
                const sev = ai.relative_severity || rep.metadata?.relative_severity || 'Low';
                const status = rep.status || 'Received';
                const statusSlug = status.toLowerCase().replace(' ', '-');
                const isUnusual = rep.metadata?.is_unusual === true || rep.validation_status === 'unusual';
                const dateStr = rep.date_submitted ? new Date(rep.date_submitted).toLocaleDateString() : 'Recent';
                const location = rep.metadata?.location_name || 'Corridor Asset';
                const repId = rep.report_id || (rep._id ? rep._id.slice(0, 16) : 'REF');

                return `
                    <tr>
                        <td><code>#${repId}</code></td>
                        <td>${dateStr}</td>
                        <td>${location}</td>
                        <td><strong>${ai.defect_class || 'Pavement Distress'}</strong></td>
                        <td><span class="severity-pill ${sev.toLowerCase()}">${sev.toUpperCase()}</span></td>
                        <td>
                            <span class="status-chip ${statusSlug}">${status}</span>
                            ${isUnusual ? `<span class="badge-tag" style="background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;margin-left:4px;">⚠️ Unusual Pairing</span>` : ''}
                        </td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error("Failed to load tracking data:", e);
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: #dc2626;">Failed to load defect reports.</td></tr>`;
        }
    },

    // Cohesive Administrative Oversight Dashboard View
    async loadAdminDashboard() {
        try {
            const data = await window.Api.getAdminDashboard();

            // KPI Overview Tiles
            document.getElementById('dashTotalUsers').textContent = data.overview.total_users || 0;
            document.getElementById('dashUserRoleBreakdown').textContent = 
                `${data.overview.citizens_count} Citizens • ${data.overview.engineers_count} Engineers`;
            document.getElementById('dashVerifiedEngineers').textContent = data.overview.verified_engineers_count || 0;
            document.getElementById('dashTotalReports').textContent = data.reports.total_reports || 0;
            document.getElementById('dashOpenReports').textContent = 
                `${data.reports.open_reports} Open / Under Review`;
            document.getElementById('dashResolutionRate').textContent = 
                `${data.reports.resolution_rate_percent}%`;

            // Pending Engineer Alert Banner
            const alertBanner = document.getElementById('adminPendingAlertBanner');
            const alertText = document.getElementById('adminPendingAlertText');
            if (alertBanner && alertText) {
                if (data.overview.pending_engineers_count > 0) {
                    alertBanner.classList.remove('hidden');
                    alertText.textContent = `${data.overview.pending_engineers_count} engineer(s) awaiting accreditation verification`;
                } else {
                    alertBanner.classList.add('hidden');
                }
            }

            // Corridor Hotspots Table
            const corridorTbody = document.getElementById('corridorTableBody');
            if (corridorTbody) {
                const hotspots = data.reports_by_location || [];
                if (hotspots.length === 0) {
                    corridorTbody.innerHTML = `<tr><td colspan="3" style="text-align:center; color:#86868b; padding:1.5rem;">No location records available.</td></tr>`;
                } else {
                    corridorTbody.innerHTML = hotspots.map(h => `
                        <tr>
                            <td><strong>${h.corridor}</strong></td>
                            <td>${h.total_defects}</td>
                            <td><span style="color:${h.critical_count > 0 ? '#dc2626' : '#16a34a'}; font-weight:600;">${h.critical_count}</span></td>
                        </tr>
                    `).join('');
                }
            }

            // Engineer Workload Table
            const workloadTbody = document.getElementById('workloadTableBody');
            if (workloadTbody) {
                const workload = data.engineer_workload || [];
                if (workload.length === 0) {
                    workloadTbody.innerHTML = `<tr><td colspan="3" style="text-align:center; color:#86868b; padding:1.5rem;">No engineer inspections completed yet.</td></tr>`;
                } else {
                    workloadTbody.innerHTML = workload.map(w => `
                        <tr>
                            <td><strong>${w.name}</strong></td>
                            <td>${w.organization || 'Independent Inspector'}</td>
                            <td><span class="badge-tag" style="background:#eff6ff; color:#1d4ed8; font-weight:600;">${w.inspections_completed} Reviews</span></td>
                        </tr>
                    `).join('');
                }
            }

            // Platform Health Indicators
            const health = data.system_health || {};
            const setPill = (id, isHealthy, textHealthy = 'Healthy', textWarning = 'Not Configured') => {
                const el = document.getElementById(id);
                if (el) {
                    el.className = `health-pill ${isHealthy ? 'healthy' : 'warning'}`;
                    el.textContent = isHealthy ? textHealthy : textWarning;
                }
            };

            const isBackendOnline = health.backend_api?.status === 'online' || health.backend_api?.status === 'healthy';
            const isMongoConnected = (health.mongodb?.status || health.database?.status) === 'connected';
            const isAiLoaded = health.ai_model?.status === 'loaded';
            const isEmailConfigured = health.email_service?.configured === true || health.email_otp?.status === 'configured';
            const isGoogleConfigured = health.google_auth?.configured === true || health.google_auth?.status === 'configured';
            const isMapsConfigured = health.google_maps?.configured === true || health.google_maps?.status === 'configured';

            setPill('healthBackend', isBackendOnline, 'Online', 'Offline');
            setPill('healthMongo', isMongoConnected, 'Connected', 'Disconnected');
            setPill('healthAiModel', isAiLoaded, 'Loaded', 'Offline');
            setPill('healthEmail', isEmailConfigured, 'Configured', 'Demo Fallback');
            setPill('healthGoogle', isGoogleConfigured, 'Configured', 'Pending ID');
            setPill('healthMaps', isMapsConfigured, 'Active (Key)', 'Pending Key');

        } catch (err) {
            console.error("Failed to load admin dashboard:", err);
            this.showToast("Failed to load admin dashboard data.", true);
        }
    },

    // Admin Verification View (FR-10)
    async loadAdminData() {
        const tbody = document.getElementById('adminTableBody');
        if (!tbody) return;

        const roleFilter = document.getElementById('adminRoleFilter')?.value || '';

        try {
            const [usersData, statsData] = await Promise.all([
                window.Api.getUsers(roleFilter),
                window.Api.getAdminStats()
            ]);

            // Update stats tiles
            document.getElementById('adminTotalUsers').textContent = statsData.total_users || 0;
            document.getElementById('adminPendingEngineers').textContent = statsData.pending_engineer_verifications || 0;
            document.getElementById('adminVerifiedEngineers').textContent = statsData.verified_engineers_count || 0;
            document.getElementById('adminTotalReports').textContent = statsData.total_defect_reports || 0;

            const searchInput = (document.getElementById('adminUserSearch')?.value || '').toLowerCase().trim();
            let users = usersData.users || [];
            if (searchInput) {
                users = users.filter(u => {
                    const name = (u.name || '').toLowerCase();
                    const email = (u.email || '').toLowerCase();
                    const org = (u.organization || '').toLowerCase();
                    const reg = (u.professional_reg_no || '').toLowerCase();
                    return name.includes(searchInput) || email.includes(searchInput) || org.includes(searchInput) || reg.includes(searchInput);
                });
            }

            if (users.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: #86868b;">No matching user records found.</td></tr>`;
                return;
            }

            tbody.innerHTML = users.map(u => {
                const isVerified = u.verification_status === 'verified';
                const isEngineer = u.role === 'engineer';
                const uid = u.user_id || u._id;
                const orgInfo = u.organization ? `${u.organization} ${u.professional_reg_no ? '(' + u.professional_reg_no + ')' : ''}` : (u.professional_reg_no || '—');
                const has2fa = u.two_factor_enabled ? '<span style="color:#16a34a; font-weight:600;">🔐 Enabled</span>' : '<span style="color:#86868b;">Disabled</span>';

                return `
                    <tr>
                        <td><strong>${u.name}</strong></td>
                        <td>${u.email}</td>
                        <td><span class="certifier-tag">${u.role.toUpperCase()}</span></td>
                        <td><span style="font-size:0.82rem; color: #515154;">${orgInfo}</span></td>
                        <td>${has2fa}</td>
                        <td>
                            <span class="verification-badge ${isVerified ? 'verified' : 'pending'}">
                                ${u.verification_status.toUpperCase()}
                            </span>
                        </td>
                        <td>
                            ${isEngineer && !isVerified ? `
                                <button type="button" class="btn-action-verify" onclick="App.handleVerifyUser('${uid}', 'verified')">
                                    ✓ Verify Engineer
                                </button>
                                <button type="button" class="btn-action-reject" onclick="App.handleVerifyUser('${uid}', 'rejected')">
                                    ✕ Reject
                                </button>
                            ` : `<span style="color: #86868b; font-size: 0.8rem;">Active</span>`}
                        </td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error("Admin data load error:", e);
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: #dc2626;">Admin access required. Please authenticate as administrator.</td></tr>`;
        }
    },

    async handleVerifyUser(userId, status) {
        try {
            await window.Api.verifyUser(userId, status);
            this.showToast(`User verification updated to '${status}'.`);
            this.loadAdminData();
        } catch (e) {
            this.showToast(e.message || "Failed to update user verification.", true);
        }
    },

    showToast(message, isError = false) {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast-msg ${isError ? 'error' : ''}`;
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 250);
        }, 3400);
    }
};

window.App = App;

// Bootstrap on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.App.init();
});
