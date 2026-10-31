/**
 * App Module - Routing, Authentication State, Role-Based UI Guarding, 2FA Flow,
 * Google Sign-In, Password Strength Validation, Map & Cohesive Admin Oversight.
 */
const App = {
    currentUser: null,
    pending2FA: null,
    resendCooldownTimer: null,
    otpCountdownTimer: null,
    authConfig: null,

    init() {
        this.bindNavigation();
        this.bindAuthEvents();
        this.bindPasswordStrengthMeter();
        this.bindEbkCategorySelector();
        this.bindAccountDropdown();
        this.bindProfileEvents();
        this.bindRejectionModal();
        this.bindAdminNoticeModal();
        
        // Initialize submodules
        if (window.Submission) window.Submission.init();
        if (window.Dashboard) window.Dashboard.init();
        if (window.Review) window.Review.init();
        if (window.DefectMap) window.DefectMap.init();

        // Restore session or default to citizen view
        this.restoreSession();
        this.loadAuthConfig();
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

        // Account dropdown and profile sidebar info
        const menuName = document.getElementById('menuUserName');
        const menuEmail = document.getElementById('menuUserEmail');
        const sideName = document.getElementById('profileSidebarName');
        const sideRole = document.getElementById('profileSidebarRole');
        const sideAvatar = document.getElementById('profileAvatarInitial');

        if (user) {
            if (profileBadge) profileBadge.classList.remove('hidden');
            if (authButtons) authButtons.classList.add('hidden');
            const notifPanel = document.getElementById('notificationPanelWrapper');
            if (notifPanel) notifPanel.classList.remove('hidden');
            this.loadNotifications();

            if (nameEl) nameEl.textContent = user.name || user.email;
            if (roleEl) roleEl.textContent = user.role.toUpperCase();

            if (menuName) menuName.textContent = user.name || user.email;
            if (menuEmail) menuEmail.textContent = user.email || '';
            if (sideName) sideName.textContent = user.name || user.email;
            if (sideRole) sideRole.textContent = (user.role || 'citizen').toUpperCase();
            if (sideAvatar) sideAvatar.textContent = (user.name || user.email || 'U')[0].toUpperCase();

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
            const menu = document.getElementById('accountDropdownMenu');
            const wrapper = document.getElementById('userProfileWrapper');
            if (menu) menu.classList.add('hidden');
            if (wrapper) wrapper.classList.remove('open');
            const notifPanel = document.getElementById('notificationPanelWrapper');
            if (notifPanel) notifPanel.classList.add('hidden');
            const notifDropdown = document.getElementById('notificationDropdown');
            if (notifDropdown) notifDropdown.classList.add('hidden');

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
                const menu = document.getElementById('accountDropdownMenu');
                const wrapper = document.getElementById('userProfileWrapper');
                if (menu) menu.classList.add('hidden');
                if (wrapper) wrapper.classList.remove('open');

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

        // Notification bell toggle & mark all read (Section 11)
        const btnBell = document.getElementById('btnNotificationBell');
        const notifDropdown = document.getElementById('notificationDropdown');
        if (btnBell && notifDropdown) {
            btnBell.addEventListener('click', (e) => {
                e.stopPropagation();
                const isHidden = notifDropdown.classList.contains('hidden');
                notifDropdown.classList.toggle('hidden', !isHidden);
                if (isHidden) {
                    this.loadNotifications();
                }
            });
        }

        const btnMarkAll = document.getElementById('btnMarkAllRead');
        if (btnMarkAll) {
            btnMarkAll.addEventListener('click', async (e) => {
                e.stopPropagation();
                try {
                    await window.Api.markAllNotificationsRead();
                    await this.loadNotifications();
                    this.showToast('All notifications marked as read.');
                } catch (err) {
                    console.warn("Failed to mark all notifications read:", err);
                }
            });
        }

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (notifDropdown && !notifDropdown.classList.contains('hidden')) {
                if (!notifDropdown.contains(e.target) && btnBell && !btnBell.contains(e.target)) {
                    notifDropdown.classList.add('hidden');
                }
            }
        });

        // Real Google Identity Services Sign-In
        const btnGoogle = document.getElementById('btnGoogleSignIn');
        if (btnGoogle) {
            btnGoogle.addEventListener('click', async () => {
                try {
                    if (!this.authConfig?.google_client_id) {
                        this.showToast("Google Sign-In is not configured: Missing GOOGLE_CLIENT_ID.", true);
                        return;
                    }
                    if (window.google?.accounts?.id) {
                        this.setupGoogleIdentity();
                        // Find rendered Google button iframe or button
                        const renderedBtn = document.querySelector('#googleSignInContainer iframe, #googleSignInContainer [role="button"]');
                        if (renderedBtn) {
                            renderedBtn.click();
                        } else {
                            this.showToast("Please use the Google Sign-In button displayed above.");
                        }
                    } else {
                        this.showToast("Google Identity Services is initializing. Please try again in a few moments.", true);
                    }
                } catch (err) {
                    console.error("Google sign-in error:", err);
                    this.showToast("Google Sign-In could not be completed. Please try again or sign in using email.", true);
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
                        this.show2FAChallenge(data);
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

        // Two-Factor Authentication Form Handling (Sections 12, 13)
        if (twoFactorForm) {
            const btnFillDemo = document.getElementById('btnFillDemoOtp');
            if (btnFillDemo) {
                btnFillDemo.addEventListener('click', () => {
                    if (this.pending2FA && this.pending2FA.demo_otp) {
                        document.getElementById('twoFactorOtpInput').value = this.pending2FA.demo_otp;
                        this.showToast("Current active security code filled.");
                    } else {
                        this.showToast("Demo code autofill is not available in production mode.", true);
                    }
                });
            }

            const btnResend = document.getElementById('btnResendOtp');
            if (btnResend) {
                btnResend.addEventListener('click', async () => {
                    if (!this.pending2FA || !this.pending2FA.email) return;
                    btnResend.disabled = true;
                    try {
                        const res = await window.Api.resendOtp(this.pending2FA.email);
                        if (res.demo_otp) {
                            this.pending2FA.demo_otp = res.demo_otp;
                            const helpEl = document.getElementById('twoFactorHelpText');
                            if (helpEl) helpEl.textContent = "Development Demo Mode active. Use 'Fill Demo Code' to auto-populate the security code or check your registered email inbox.";
                        }
                        // Clear input so stale code is never left behind
                        document.getElementById('twoFactorOtpInput').value = '';
                        this.startOtpCountdown(res.expires_in_seconds || 300);
                        this.startResendCooldown(res.cooldown_seconds || 60);
                        this.showToast(res.message || "Fresh 2FA verification code dispatched.");
                    } catch (err) {
                        this.showToast(err.message || "Failed to resend code.", true);
                        btnResend.disabled = false;
                    }
                });
            }

            const btnCancel2FA = document.getElementById('btnCancelTwoFactor');
            if (btnCancel2FA) {
                btnCancel2FA.addEventListener('click', () => {
                    if (this.otpCountdownTimer) clearInterval(this.otpCountdownTimer);
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
                    if (this.otpCountdownTimer) clearInterval(this.otpCountdownTimer);
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

    show2FAChallenge(data) {
        this.pending2FA = {
            email: data.email,
            role: data.role,
            demo_otp: data.demo_otp,
            enable_demo_otp: data.enable_demo_otp
        };

        const loginForm = document.getElementById('loginForm');
        const authTabsRow = document.getElementById('authTabsRow');
        const twoFactorForm = document.getElementById('twoFactorForm');

        if (loginForm) loginForm.classList.add('hidden');
        if (authTabsRow) authTabsRow.classList.add('hidden');
        if (twoFactorForm) {
            twoFactorForm.classList.remove('hidden');
            const emailDisp = document.getElementById('twoFactorEmailDisplay');
            if (emailDisp) emailDisp.textContent = data.email;
            const otpInput = document.getElementById('twoFactorOtpInput');
            if (otpInput) otpInput.value = '';

            const helpEl = document.getElementById('twoFactorHelpText');
            const btnFill = document.getElementById('btnFillDemoOtp');

            const isDemo = data.enable_demo_otp !== false && Boolean(data.demo_otp);
            if (btnFill) {
                btnFill.classList.toggle('hidden', !isDemo);
            }
            if (helpEl) {
                if (isDemo) {
                    helpEl.textContent = "Development Demo Mode active. Use 'Fill Demo Code' to auto-populate the security code or check your registered email inbox.";
                } else {
                    helpEl.textContent = "Enter the 6-digit verification code sent to your registered email address.";
                }
            }

            this.startOtpCountdown(data.expires_in_seconds || 300);
            this.startResendCooldown(data.cooldown_seconds || 60);
        }
        this.showToast(data.message || 'Two-Factor Authentication required.');
    },

    startResendCooldown(seconds) {
        const btn = document.getElementById('btnResendOtp');
        const timerText = document.getElementById('resendTimerText');
        if (!btn || !timerText) return;

        let remaining = seconds;
        btn.disabled = true;
        btn.style.opacity = '0.7';
        btn.style.cursor = 'not-allowed';
        btn.style.textDecoration = 'none';
        timerText.textContent = `Resend available in ${remaining}s`;

        if (this.resendCooldownTimer) clearInterval(this.resendCooldownTimer);

        this.resendCooldownTimer = setInterval(() => {
            remaining -= 1;
            if (remaining <= 0) {
                clearInterval(this.resendCooldownTimer);
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';
                btn.style.textDecoration = 'underline';
                timerText.textContent = 'Resend Code';
            } else {
                timerText.textContent = `Resend available in ${remaining}s`;
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
            if (window.DefectMap) {
                window.DefectMap.loadMapData();
                window.DefectMap.invalidateSize();
            }
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
                            ${isUnusual ? `<span class="badge-tag" style="background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;margin-left:4px;"><i class='bx bx-error-circle'></i> Unusual Pairing</span>` : ''}
                        </td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error("Failed to load tracking data:", e);
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: #dc2626;">Failed to load defect reports.</td></tr>`;
        }
    },

    // Citizen Report Feedback Notifications (Section 11)
    async loadNotifications() {
        if (!this.currentUser) return;
        try {
            const data = await window.Api.getNotifications();
            const notifications = data.notifications || [];
            const unreadCount = data.unread_count || 0;

            const badge = document.getElementById('notificationBadge');
            if (badge) {
                if (unreadCount > 0) {
                    badge.textContent = unreadCount > 99 ? '99+' : unreadCount;
                    badge.classList.remove('hidden');
                } else {
                    badge.classList.add('hidden');
                }
            }

            const listEl = document.getElementById('notificationItemsList');
            if (!listEl) return;

            if (notifications.length === 0) {
                listEl.innerHTML = `<div class="notification-empty">No report feedback notifications yet.</div>`;
                return;
            }

            listEl.innerHTML = notifications.map(n => {
                const isUnread = !n.is_read;
                const timeStr = n.created_at ? new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' }) : '';
                return `
                    <div class="notification-item ${isUnread ? 'unread' : ''}" data-id="${n.notification_id || n._id}" data-report-id="${n.report_id || ''}">
                        <div class="notification-item-header">
                            <span class="notification-item-title">${n.title || 'Report Feedback'}</span>
                            <span class="notification-item-time">${timeStr}</span>
                        </div>
                        <div class="notification-item-message">${n.message}</div>
                        ${n.report_id ? `<div class="notification-item-link">View Report Details →</div>` : ''}
                    </div>
                `;
            }).join('');

            // Bind click to each notification item
            listEl.querySelectorAll('.notification-item').forEach(item => {
                item.addEventListener('click', async () => {
                    const notifId = item.getAttribute('data-id');
                    const reportId = item.getAttribute('data-report-id');
                    try {
                        await window.Api.markNotificationRead(notifId);
                    } catch (e) {
                        console.warn("Failed to mark notification read:", e);
                    }
                    item.classList.remove('unread');
                    const currentBadge = document.getElementById('notificationBadge');
                    if (currentBadge && !currentBadge.classList.contains('hidden')) {
                        const count = parseInt(currentBadge.textContent, 10) || 1;
                        if (count <= 1) {
                            currentBadge.classList.add('hidden');
                        } else {
                            currentBadge.textContent = count - 1;
                        }
                    }
                    document.getElementById('notificationDropdown')?.classList.add('hidden');

                    if (reportId) {
                        if (this.currentUser?.role === 'engineer' || this.currentUser?.role === 'admin') {
                            this.navigateTo('view-review', reportId);
                        } else {
                            this.navigateTo('view-tracking');
                        }
                    }
                });
            });
        } catch (err) {
            console.warn("Failed to load notifications:", err);
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
            const isEmailHealthy = health.email_otp?.status === 'operational' || health.email_service?.status === 'operational';
            const isMapsActive = health.gis_mapping?.status === 'operational' || health.google_maps?.status === 'operational';

            setPill('healthBackend', isBackendOnline, 'Online', 'Offline');
            setPill('healthMongo', isMongoConnected, 'Connected', 'Disconnected');
            setPill('healthAiModel', isAiLoaded, 'Loaded', 'Offline');
            setPill('healthEmail', isEmailHealthy, 'Operational', 'Demo Fallback');
            
            // Distinguish Google Identity Configured vs Operational (Section 5)
            const googleStatus = health.google_auth?.status;
            const googleEl = document.getElementById('healthGoogle');
            if (googleEl) {
                if (googleStatus === 'operational') {
                    googleEl.className = 'health-pill healthy';
                    googleEl.textContent = 'Operational';
                } else if (health.google_auth?.configured) {
                    googleEl.className = 'health-pill warning';
                    googleEl.textContent = 'Configured';
                } else {
                    googleEl.className = 'health-pill warning';
                    googleEl.textContent = 'Pending ID';
                }
            }

            setPill('healthMaps', isMapsActive, 'Active', 'Offline');

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
            if (document.getElementById('adminActiveUsers')) {
                document.getElementById('adminActiveUsers').textContent = statsData.active_users_count || (statsData.total_users - (statsData.pending_engineer_verifications || 0));
            } else if (document.getElementById('adminTotalReports')) {
                document.getElementById('adminTotalReports').textContent = statsData.total_defect_reports || 0;
            }

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
                const has2fa = u.two_factor_enabled ? '<span style="color:#16a34a; font-weight:600;"><i class=\'bx bx-shield-quarter\'></i> Enabled</span>' : '<span style="color:#86868b;">Disabled</span>';
                const verifClass = isVerified ? 'verified' : (u.verification_status === 'rejected' ? 'rejected' : 'pending');
                const reasonTooltip = u.rejection_reason ? `title="Rejection Reason: ${u.rejection_reason}"` : '';

                return `
                    <tr>
                        <td><strong>${u.name}</strong></td>
                        <td>${u.email}</td>
                        <td><span class="certifier-tag">${u.role.toUpperCase()}</span></td>
                        <td><span style="font-size:0.82rem; color: #515154;">${orgInfo}</span></td>
                        <td>${has2fa}</td>
                        <td>
                            <span class="verification-badge ${verifClass}" ${reasonTooltip}>
                                ${u.verification_status.toUpperCase()}
                            </span>
                        </td>
                        <td>
                            <div style="display:flex; align-items:center; gap:4px; flex-wrap:wrap;">
                                ${isEngineer && !isVerified ? `
                                    <button type="button" class="btn-action-verify" onclick="App.handleVerifyUser('${uid}', 'verified')">
                                        <i class='bx bx-user-check'></i> Verify
                                    </button>
                                    ${u.verification_status !== 'rejected' ? `
                                    <button type="button" class="btn-action-reject" onclick="App.openRejectionModal('${uid}', '${(u.name || 'Engineer').replace(/'/g, "\\'")}', '${u.email}')">
                                        <i class='bx bx-user-x'></i> Reject
                                    </button>` : ''}
                                ` : `<span style="color: #86868b; font-size: 0.8rem;">Active</span>`}
                                <button type="button" class="btn-micro" style="padding: 2px 6px; font-size: 0.75rem;" title="Send targeted notice to ${u.name}" onclick="App.openTargetedNotice('${uid}', '${(u.name || 'User').replace(/'/g, "\\'")}', '${u.email}')">
                                    <i class='bx bx-envelope'></i> Notice
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error("Admin data load error:", e);
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: #dc2626;">Admin access required. Please authenticate as administrator.</td></tr>`;
        }
    },

    openRejectionModal(userId, name, email) {
        this.pendingRejectionUserId = userId;
        const modal = document.getElementById('engineerRejectionModal');
        const nameEl = document.getElementById('rejectionTargetName');
        const emailEl = document.getElementById('rejectionTargetEmail');
        const selectEl = document.getElementById('rejectionReasonSelect');
        const notesEl = document.getElementById('rejectionNotesText');

        if (nameEl) nameEl.textContent = name || 'Engineer';
        if (emailEl) emailEl.textContent = email || '';
        if (selectEl) selectEl.value = 'Unable to verify submitted EBK registration';
        if (notesEl) notesEl.value = '';

        if (modal) modal.classList.add('active');
    },

    bindRejectionModal() {
        const modal = document.getElementById('engineerRejectionModal');
        const btnCancel = document.getElementById('btnCancelRejection');
        const btnClose = document.getElementById('btnCloseRejectionModal');
        const btnConfirm = document.getElementById('btnConfirmRejection');
        const reasonSelect = document.getElementById('rejectionReasonSelect');
        const notesText = document.getElementById('rejectionNotesText');

        const closeModal = () => {
            if (modal) modal.classList.remove('active');
            this.pendingRejectionUserId = null;
        };

        if (btnCancel) btnCancel.addEventListener('click', closeModal);
        if (btnClose) btnClose.addEventListener('click', closeModal);

        if (btnConfirm) {
            btnConfirm.addEventListener('click', async () => {
                if (!this.pendingRejectionUserId) return;
                const reason = reasonSelect ? reasonSelect.value : 'Unable to verify submitted EBK registration';
                const notes = notesText ? notesText.value.trim() : '';

                if (reason === 'Other' && !notes) {
                    this.showToast("Please provide explanation notes when 'Other' reason is selected.", true);
                    if (notesText) notesText.focus();
                    return;
                }

                try {
                    btnConfirm.disabled = true;
                    btnConfirm.textContent = 'Processing...';
                    const result = await window.Api.verifyUser(this.pendingRejectionUserId, 'rejected', reason, notes);
                    this.showToast(result.message || "Engineer application rejected and applicant notified.");
                    closeModal();
                    await this.loadAdminData();
                    if (typeof this.loadAdminDashboard === 'function') {
                        this.loadAdminDashboard().catch(() => {});
                    }
                } catch (err) {
                    console.error("Rejection error:", err);
                    this.showToast(err.message || "Failed to submit rejection decision.", true);
                } finally {
                    btnConfirm.disabled = false;
                    btnConfirm.textContent = 'Confirm Rejection';
                }
            });
        }
    },

    bindAdminNoticeModal() {
        const modal = document.getElementById('adminNoticeModal');
        const btnOpen = document.getElementById('btnOpenAdminNotice');
        const btnCancel = document.getElementById('btnCancelAdminNotice');
        const btnClose = document.getElementById('btnCloseAdminNotice');
        const btnConfirm = document.getElementById('btnConfirmAdminNotice');
        const modeSelect = document.getElementById('adminNoticeMode');
        const targetGroup = document.getElementById('adminNoticeTargetGroup');
        const targetUserSelect = document.getElementById('adminNoticeTargetUser');
        const catSelect = document.getElementById('adminNoticeCategory');
        const titleInput = document.getElementById('adminNoticeTitleInput');
        const msgText = document.getElementById('adminNoticeMessage');

        const closeModal = () => {
            if (modal) modal.classList.remove('active');
        };

        if (btnOpen) {
            btnOpen.addEventListener('click', async () => {
                try {
                    const data = await window.Api.getUsers();
                    const users = data.users || [];
                    if (targetUserSelect) {
                        targetUserSelect.innerHTML = `<option value="">Select recipient...</option>` +
                            users.map(u => `<option value="${u.user_id || u._id}">${u.name} (${u.email}) [${u.role.toUpperCase()}]</option>`).join('');
                    }
                } catch (e) {
                    console.warn("Failed to load users for notice target:", e);
                }
                if (titleInput) titleInput.value = 'Professional Registration Notice';
                if (msgText) msgText.value = '';
                if (modal) modal.classList.add('active');
            });
        }

        if (modeSelect) {
            modeSelect.addEventListener('change', (e) => {
                if (targetGroup) {
                    targetGroup.style.display = e.target.value === 'broadcast' ? 'none' : 'block';
                }
            });
        }

        if (catSelect) {
            catSelect.addEventListener('change', (e) => {
                if (titleInput) {
                    titleInput.value = `InfraVision: ${e.target.value}`;
                }
            });
        }

        if (btnCancel) btnCancel.addEventListener('click', closeModal);
        if (btnClose) btnClose.addEventListener('click', closeModal);

        if (btnConfirm) {
            btnConfirm.addEventListener('click', async () => {
                const mode = modeSelect ? modeSelect.value : 'targeted';
                const targetId = targetUserSelect ? targetUserSelect.value : '';
                const category = catSelect ? catSelect.value : 'Administrative Notice';
                const title = titleInput ? titleInput.value.trim() : '';
                const message = msgText ? msgText.value.trim() : '';

                if (mode === 'targeted' && !targetId) {
                    this.showToast("Please select a recipient user for targeted notice.", true);
                    return;
                }
                if (!message) {
                    this.showToast("Please enter a notice message.", true);
                    return;
                }

                try {
                    btnConfirm.disabled = true;
                    btnConfirm.textContent = 'Dispatching...';
                    const res = await window.Api.sendAdminNotice({
                        type: mode,
                        target_user_id: targetId,
                        category,
                        title,
                        message
                    });
                    this.showToast(res.message || "Notice dispatched successfully!");
                    closeModal();
                } catch (err) {
                    this.showToast(err.message || "Failed to dispatch notice.", true);
                } finally {
                    btnConfirm.disabled = false;
                    btnConfirm.textContent = 'Dispatch Notice';
                }
            });
        }
    },

    async handleVerifyUser(userId, status) {
        if (!userId) return;
        try {
            const result = await window.Api.verifyUser(userId, status);
            this.showToast(result.message || `Engineer accreditation status updated to '${status}'.`);
            // Refresh User Governance Table
            await this.loadAdminData();
            // Refresh Admin Dashboard stats if loaded
            if (typeof this.loadAdminDashboard === 'function') {
                this.loadAdminDashboard().catch(() => {});
            }
        } catch (err) {
            console.error("Admin verification error:", err);
            this.showToast(err.message || "Failed to update user verification status.", true);
        }
    },

    bindAccountDropdown() {
        const badge = document.getElementById('userProfileBadge');
        const menu = document.getElementById('accountDropdownMenu');
        const wrapper = document.getElementById('userProfileWrapper');

        const closeDropdown = () => {
            if (menu) menu.classList.add('hidden');
            if (wrapper) wrapper.classList.remove('open');
        };

        if (badge && menu) {
            badge.addEventListener('click', (e) => {
                e.stopPropagation();
                const isHidden = menu.classList.toggle('hidden');
                if (wrapper) wrapper.classList.toggle('open', !isHidden);
            });
            document.addEventListener('click', (e) => {
                if (!e.target.closest('#userProfileWrapper')) {
                    closeDropdown();
                }
            });
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' || e.key === 'Esc') {
                    closeDropdown();
                }
            });
        }

        const btnNavProf = document.getElementById('btnNavProfile');
        if (btnNavProf) {
            btnNavProf.addEventListener('click', () => {
                closeDropdown();
                this.openProfileView('panelProfileInfo');
            });
        }

        const btnNavSec = document.getElementById('btnNavSecurity');
        if (btnNavSec) {
            btnNavSec.addEventListener('click', () => {
                closeDropdown();
                this.openProfileView('panelProfileSecurity');
            });
        }
    },

    openProfileView(panelId = 'panelProfileInfo') {
        this.navigateTo('view-profile');
        const tabInfo = document.getElementById('tabProfileInfo');
        const tabSec = document.getElementById('tabProfileSecurity');
        const panelInfo = document.getElementById('panelProfileInfo');
        const panelSec = document.getElementById('panelProfileSecurity');

        if (panelId === 'panelProfileSecurity') {
            if (tabSec) tabSec.classList.add('active');
            if (tabInfo) tabInfo.classList.remove('active');
            if (panelSec) {
                panelSec.classList.remove('hidden');
                panelSec.classList.add('active');
            }
            if (panelInfo) {
                panelInfo.classList.add('hidden');
                panelInfo.classList.remove('active');
            }
        } else {
            if (tabInfo) tabInfo.classList.add('active');
            if (tabSec) tabSec.classList.remove('active');
            if (panelInfo) {
                panelInfo.classList.remove('hidden');
                panelInfo.classList.add('active');
            }
            if (panelSec) {
                panelSec.classList.add('hidden');
                panelSec.classList.remove('active');
            }
        }
        this.loadProfileData();
    },

    async loadProfileData() {
        if (!this.currentUser) return;
        try {
            const data = await window.Api.getProfile();
            const u = data.user || this.currentUser;

            const nameInp = document.getElementById('profFullName');
            const emailInp = document.getElementById('profEmail');
            const phoneInp = document.getElementById('profPhone');
            const roleInp = document.getElementById('profRole');

            if (nameInp) nameInp.value = u.name || '';
            if (emailInp) emailInp.value = u.email || '';
            if (phoneInp) phoneInp.value = u.phone || '';
            if (roleInp) roleInp.value = (u.role || 'citizen').toUpperCase();

            // Engineer credentials panel (Section 9)
            const engBox = document.getElementById('profEngineerDetails');
            if (engBox) {
                if (u.role === 'engineer' && data.engineering_details) {
                    engBox.classList.remove('hidden');
                    const catInp = document.getElementById('profEngCategory');
                    const regInp = document.getElementById('profEngRegNo');
                    const statInp = document.getElementById('profEngStatus');
                    const orgInp = document.getElementById('profOrganization');

                    if (catInp) catInp.value = data.engineering_details.engineering_category || '';
                    if (regInp) regInp.value = data.engineering_details.professional_reg_no || '';
                    if (statInp) statInp.value = (data.engineering_details.verification_status || 'pending').toUpperCase();
                    if (orgInp) orgInp.value = data.engineering_details.organization || '';
                } else {
                    engBox.classList.add('hidden');
                }
            }

            // Security: Weak password recommendation warning (Section 10)
            const weakBanner = document.getElementById('weakPasswordWarningBanner');
            if (weakBanner) {
                if (data.has_weak_password) {
                    weakBanner.classList.remove('hidden');
                } else {
                    weakBanner.classList.add('hidden');
                }
            }

            // 2FA Badge in Profile Security
            const badge2fa = document.getElementById('profTwoFactorBadge');
            if (badge2fa) {
                badge2fa.textContent = data.two_factor_enabled ? 'Enabled' : 'Disabled';
                badge2fa.className = `status-chip ${data.two_factor_enabled ? 'active' : 'pending'}`;
            }
        } catch (e) {
            console.error("Failed to load profile data:", e);
        }
    },

    bindProfileEvents() {
        const tabInfo = document.getElementById('tabProfileInfo');
        const tabSec = document.getElementById('tabProfileSecurity');
        const panelInfo = document.getElementById('panelProfileInfo');
        const panelSec = document.getElementById('panelProfileSecurity');

        if (tabInfo && tabSec) {
            tabInfo.addEventListener('click', () => {
                tabInfo.classList.add('active');
                tabSec.classList.remove('active');
                if (panelInfo) {
                    panelInfo.classList.remove('hidden');
                    panelInfo.classList.add('active');
                }
                if (panelSec) {
                    panelSec.classList.add('hidden');
                    panelSec.classList.remove('active');
                }
            });
            tabSec.addEventListener('click', () => {
                tabSec.classList.add('active');
                tabInfo.classList.remove('active');
                if (panelSec) {
                    panelSec.classList.remove('hidden');
                    panelSec.classList.add('active');
                }
                if (panelInfo) {
                    panelInfo.classList.add('hidden');
                    panelInfo.classList.remove('active');
                }
            });
        }

        // Profile information form submission (Section 9)
        const formProf = document.getElementById('formUpdateProfile');
        if (formProf) {
            formProf.addEventListener('submit', async (e) => {
                e.preventDefault();
                const name = document.getElementById('profFullName').value.trim();
                const phone = document.getElementById('profPhone').value.trim();
                const orgInput = document.getElementById('profOrganization');
                const organization = orgInput ? orgInput.value.trim() : '';

                const saveBtn = document.getElementById('btnSaveProfile');
                saveBtn.disabled = true;
                saveBtn.textContent = 'Saving Changes...';
                try {
                    const res = await window.Api.updateProfile({ name, phone, organization });
                    this.currentUser = res.user;
                    this.updateSessionUI();
                    this.showToast(res.message || "Profile information updated successfully!");
                } catch (err) {
                    this.showToast(err.message || "Failed to update profile.", true);
                } finally {
                    saveBtn.disabled = false;
                    saveBtn.textContent = 'Save Profile Changes';
                }
            });
        }

        // Live validation for new password in profile security (Section 10)
        const pwdNew = document.getElementById('pwdNew');
        if (pwdNew) {
            pwdNew.addEventListener('input', (e) => {
                const val = e.target.value;
                const hasLen = val.length >= 8;
                const hasNum = /\d/.test(val);
                const hasSpec = /[!@#$%^&*()\-_=+\[\]{};:'",.<>?/\\|`~]/.test(val);
                const hasCase = /[A-Z]/.test(val) && /[a-z]/.test(val);

                const critLen = document.getElementById('critProfLength');
                const critNum = document.getElementById('critProfNumber');
                const critSpec = document.getElementById('critProfSpecial');
                const critCase = document.getElementById('critProfCase');

                if (critLen) {
                    critLen.className = `criterion ${hasLen ? 'passed' : 'failed'}`;
                    critLen.innerHTML = `<i class='bx ${hasLen ? 'bx-check' : 'bx-x'}'></i> At least 8 characters`;
                }
                if (critNum) {
                    critNum.className = `criterion ${hasNum ? 'passed' : 'failed'}`;
                    critNum.innerHTML = `<i class='bx ${hasNum ? 'bx-check' : 'bx-x'}'></i> At least one number (0-9)`;
                }
                if (critSpec) {
                    critSpec.className = `criterion ${hasSpec ? 'passed' : 'failed'}`;
                    critSpec.innerHTML = `<i class='bx ${hasSpec ? 'bx-check' : 'bx-x'}'></i> At least one special symbol (!@#$)`;
                }
                if (critCase) {
                    critCase.className = `criterion ${hasCase ? 'passed' : 'failed'}`;
                    critCase.innerHTML = `<i class='bx ${hasCase ? 'bx-check' : 'bx-x'}'></i> Upper & lowercase letters`;
                }
            });
        }

        // Change password form submission (Section 10)
        const formPwd = document.getElementById('formChangePassword');
        if (formPwd) {
            formPwd.addEventListener('submit', async (e) => {
                e.preventDefault();
                const curr = document.getElementById('pwdCurrent').value;
                const next = document.getElementById('pwdNew').value;
                const conf = document.getElementById('pwdConfirm').value;

                if (next !== conf) {
                    this.showToast("New passwords do not match.", true);
                    return;
                }

                const btn = document.getElementById('btnSubmitChangePassword');
                btn.disabled = true;
                btn.textContent = 'Updating Password...';
                try {
                    const res = await window.Api.changePassword(curr, next);
                    this.showToast(res.message || "Password updated successfully!");
                    formPwd.reset();
                    const weakBanner = document.getElementById('weakPasswordWarningBanner');
                    if (weakBanner) weakBanner.classList.add('hidden');
                } catch (err) {
                    this.showToast(err.message || "Failed to update password.", true);
                } finally {
                    btn.disabled = false;
                    btn.textContent = 'Update Password';
                }
            });
        }
    },

    async loadAuthConfig() {
        try {
            this.authConfig = await window.Api.getAuthConfig();
            this.initGoogleIdentity();
        } catch (e) {
            console.warn("Failed to load auth configuration:", e);
        }
    },

    initGoogleIdentity() {
        if (!window.google?.accounts?.id) {
            let attempts = 0;
            const checkGis = setInterval(() => {
                attempts++;
                if (window.google?.accounts?.id) {
                    clearInterval(checkGis);
                    this.setupGoogleIdentity();
                } else if (attempts >= 10) {
                    clearInterval(checkGis);
                }
            }, 300);
            return;
        }
        this.setupGoogleIdentity();
    },

    setupGoogleIdentity() {
        if (!window.google?.accounts?.id || !this.authConfig?.google_client_id) return;
        try {
            if (!this._gisInitialized) {
                window.google.accounts.id.initialize({
                    client_id: this.authConfig.google_client_id,
                    auto_select: false,
                    callback: async (response) => {
                        if (response.credential) {
                            try {
                                const data = await window.Api.loginWithGoogle(response.credential);
                                if (data.require_2fa) {
                                    this.show2FAChallenge(data);
                                    return;
                                }
                                this.currentUser = data.user;
                                this.updateSessionUI();
                                this.showToast(`Signed in with Google as ${data.user.name || data.user.email}!`);
                                this.routeUserAfterAuth(data.user);
                            } catch (err) {
                                console.error("[Google Auth Error]", err);
                                this.showToast(err.message || "Google identity was verified, but InfraVision could not complete sign-in. Please try again.", true);
                            }
                        }
                    }
                });
                this._gisInitialized = true;
            }

            const googleContainer = document.getElementById('googleSignInContainer');
            if (googleContainer) {
                // Responsive width between 280 and 380
                const computedWidth = Math.min(380, Math.max(280, googleContainer.offsetWidth || 380));
                googleContainer.innerHTML = '';
                window.google.accounts.id.renderButton(googleContainer, {
                    theme: 'outline',
                    size: 'large',
                    text: 'continue_with',
                    shape: 'rectangular',
                    width: computedWidth,
                    logo_alignment: 'left'
                });
            }
        } catch (e) {
            console.warn("GIS initialization warning:", e);
        }
    },

    startOtpCountdown(seconds) {
        if (this.otpCountdownTimer) clearInterval(this.otpCountdownTimer);
        let remaining = seconds;
        const textEl = document.getElementById('otpCountdownText');
        const btnVerify = document.getElementById('btnVerifyTwoFactor');

        const updateDisplay = () => {
            if (!textEl) return;
            if (remaining <= 0) {
                textEl.innerHTML = `<i class='bx bx-time-five'></i> Code expired. Please request a new code.`;
                textEl.style.color = '#dc2626';
                if (btnVerify) btnVerify.disabled = true;
                if (this.otpCountdownTimer) clearInterval(this.otpCountdownTimer);
            } else {
                const m = Math.floor(remaining / 60);
                const s = remaining % 60;
                textEl.innerHTML = `<i class='bx bx-time-five'></i> Code expires in ${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
                textEl.style.color = remaining < 60 ? '#dc2626' : '#475569';
                if (btnVerify) btnVerify.disabled = false;
            }
        };

        updateDisplay();
        this.otpCountdownTimer = setInterval(() => {
            remaining -= 1;
            updateDisplay();
        }, 1000);
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
