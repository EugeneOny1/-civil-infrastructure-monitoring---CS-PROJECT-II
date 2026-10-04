/**
 * App Module - Routing, Authentication State, Role-Based UI Guarding & 2FA Flow
 * Apple-Inspired Clean Interaction Design
 */
const App = {
    currentUser: null,
    pending2FA: null,

    init() {
        this.bindNavigation();
        this.bindAuthEvents();
        
        // Initialize submodules
        if (window.Submission) window.Submission.init();
        if (window.Dashboard) window.Dashboard.init();
        if (window.Review) window.Review.init();

        // Restore session or default to citizen view
        this.restoreSession();
        this.checkBackendStatus();
    },

    restoreSession() {
        this.currentUser = window.Api.getUser();
        this.updateSessionUI();
        
        if (this.currentUser) {
            if (this.currentUser.role === 'engineer' && this.currentUser.verification_status === 'verified') {
                this.navigateTo('view-dashboard');
            } else if (this.currentUser.role === 'admin') {
                this.navigateTo('view-admin');
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

        // Hide all role-guarded tabs first
        document.querySelectorAll('.role-guarded').forEach(el => el.classList.add('hidden'));

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

            // Expose role-specific navigation tabs
            if (user.role === 'engineer') {
                if (isVerified) {
                    document.querySelectorAll('.role-engineer').forEach(el => el.classList.remove('hidden'));
                }
            } else if (user.role === 'admin') {
                document.querySelectorAll('.role-engineer').forEach(el => el.classList.remove('hidden'));
                document.querySelectorAll('.role-admin').forEach(el => el.classList.remove('hidden'));
            }
        } else {
            if (profileBadge) profileBadge.classList.add('hidden');
            if (authButtons) authButtons.classList.remove('hidden');
        }
    },

    bindNavigation() {
        const tabs = document.querySelectorAll('.nav-tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
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

        // Post-submit redirect button
        const viewTrackingBtn = document.getElementById('btnViewTrackingAfterSubmit');
        if (viewTrackingBtn) {
            viewTrackingBtn.addEventListener('click', () => {
                this.navigateTo('view-tracking');
            });
        }

        // Admin role filter change
        const adminRoleFilter = document.getElementById('adminRoleFilter');
        if (adminRoleFilter) {
            adminRoleFilter.addEventListener('change', () => this.loadAdminData());
        }
    },

    bindAuthEvents() {
        // Sign In / Register buttons in header
        const btnOpenLogin = document.getElementById('btnOpenLogin');
        const btnOpenRegister = document.getElementById('btnOpenRegister');
        const btnLogout = document.getElementById('btnLogout');

        if (btnOpenLogin) {
            btnOpenLogin.addEventListener('click', () => {
                this.showAuthView('login');
            });
        }
        if (btnOpenRegister) {
            btnOpenRegister.addEventListener('click', () => {
                this.showAuthView('register');
            });
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

        // Dynamic registration role toggle for professional fields
        const regRoleSelect = document.getElementById('regRole');
        const engineerFieldsContainer = document.getElementById('engineerFieldsContainer');
        if (regRoleSelect && engineerFieldsContainer) {
            regRoleSelect.addEventListener('change', (e) => {
                if (e.target.value === 'engineer') {
                    engineerFieldsContainer.classList.remove('hidden');
                } else {
                    engineerFieldsContainer.classList.add('hidden');
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

                    // Check if Two-Factor Authentication challenge was returned
                    if (data.require_2fa) {
                        this.pending2FA = {
                            email: data.email,
                            role: data.role,
                            demo_otp: data.demo_otp
                        };

                        // Switch to 2FA verification form
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

                    // Direct login success (e.g. citizens or accounts with 2FA off)
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
                    this.showToast("No active 2FA verification session. Please sign in again.", true);
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
                const professional_reg_no = document.getElementById('regLicense')?.value.trim() || '';
                const phone = document.getElementById('regPhone')?.value.trim() || '';
                const two_factor_enabled = document.getElementById('regTwoFactor')?.checked || false;

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
            this.navigateTo('view-admin');
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

    navigateTo(viewId) {
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
        } else if (viewId === 'view-dashboard') {
            if (window.Dashboard) window.Dashboard.loadDashboardData();
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
                const status = rep.status || 'Pending';
                const isFlagged = status === 'Flagged for Review' || rep.metadata?.is_unusual === true;
                const dateStr = rep.date_submitted ? new Date(rep.date_submitted).toLocaleDateString() : 'Recent';
                const location = rep.metadata?.location_name || 'Corridor Asset';

                return `
                    <tr>
                        <td><code>#${rep._id ? rep._id.slice(0, 16) : 'REF'}</code></td>
                        <td>${dateStr}</td>
                        <td>${location}</td>
                        <td><strong>${ai.defect_class || 'Pavement Distress'}</strong></td>
                        <td><span class="severity-pill ${sev.toLowerCase()}">${sev.toUpperCase()}</span></td>
                        <td>
                            ${isFlagged ? `
                                <span class="report-status-badge flagged" title="${rep.metadata?.advisory_notes || 'Flagged for engineer review'}">
                                    ⚠️ Flagged for Review
                                </span>
                            ` : `
                                <span class="report-status-badge ${status.toLowerCase()}">${status}</span>
                            `}
                        </td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error("Failed to load tracking data:", e);
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: #dc2626;">Failed to load defect reports.</td></tr>`;
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

            const users = usersData.users || [];
            if (users.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: #86868b;">No user records found.</td></tr>`;
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
