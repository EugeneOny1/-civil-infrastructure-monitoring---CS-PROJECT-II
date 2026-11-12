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
        this.bindLandingEvents();
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
        const requestedView = urlParams.get('view');

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
        } else if (requestedView && document.getElementById(requestedView)) {
            this.navigateTo(requestedView);
        } else {
            this.navigateTo('view-landing');
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
                document.getElementById('tabHome')?.classList.add('hidden');
                document.getElementById('tabSubmit')?.classList.add('hidden');
                document.getElementById('tabTracking')?.classList.add('hidden');
                document.getElementById('tabMap')?.classList.add('hidden');
                document.getElementById('tabDashboard')?.classList.add('hidden');
                document.getElementById('tabReview')?.classList.add('hidden');
                document.getElementById('tabAdminDashboard')?.classList.remove('hidden');
                document.getElementById('tabAdmin')?.classList.remove('hidden');
            } else if (user.role === 'engineer') {
                // Engineer sees: Home, Report Defect, My Reports, Infrastructure Map, Monitoring Dashboard, Defect Review
                document.getElementById('tabHome')?.classList.remove('hidden');
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
                // Citizen sees: Home, Report Defect, My Reports, and Infrastructure Map
                document.getElementById('tabHome')?.classList.remove('hidden');
                document.getElementById('tabSubmit')?.classList.remove('hidden');
                document.getElementById('tabTracking')?.classList.remove('hidden');
                document.getElementById('tabMap')?.classList.remove('hidden');
                document.getElementById('tabDashboard')?.classList.add('hidden');
                document.getElementById('tabReview')?.classList.add('hidden');
                document.getElementById('tabAdminDashboard')?.classList.add('hidden');
                document.getElementById('tabAdmin')?.classList.add('hidden');
            }
        } else {
            // Unauthenticated Guest: Public Landing + Citizen entry views
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
            document.getElementById('tabHome')?.classList.remove('hidden');
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
                if (this.currentUser && this.currentUser.role === 'admin') {
                    this.navigateTo('view-admin-dashboard');
                } else {
                    this.navigateTo('view-landing');
                }
            });
        }

        // Tracking refresh
        const refreshBtn = document.getElementById('btnRefreshTracking');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadTrackingData());
        }

        // Section 20: Tracking view mode toggle (List vs Gallery)
        const btnListView = document.getElementById('btnTrackingListView');
        const btnGalleryView = document.getElementById('btnTrackingGalleryView');
        if (btnListView) {
            btnListView.addEventListener('click', () => this.setTrackingViewMode('list'));
        }
        if (btnGalleryView) {
            btnGalleryView.addEventListener('click', () => this.setTrackingViewMode('gallery'));
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
                this.clearPasswordFields();
                this.currentUser = null;
                this.pending2FA = null;
                this.updateSessionUI();
                this.showToast('Logged out successfully.');
                this.navigateTo('view-landing');
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
                this.clearPasswordFields();
            });
            tabRegister.addEventListener('click', () => {
                tabRegister.classList.add('active');
                tabLogin.classList.remove('active');
                registerForm.classList.remove('hidden');
                loginForm.classList.add('hidden');
                if (twoFactorForm) twoFactorForm.classList.add('hidden');
                if (authTabsRow) authTabsRow.classList.remove('hidden');
                this.clearPasswordFields();
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
                        this.clearPasswordFields();
                        this.show2FAChallenge(data);
                        return;
                    }

                    // Direct login
                    this.clearPasswordFields();
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
                        this.showToast("Verification code entered.");
                    } else {
                        this.showToast("Automatic code entry is unavailable. Please check your email inbox.", true);
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
                        const btnFillEl = document.getElementById('btnFillDemoOtp');
                        if (res.enable_demo_otp && res.demo_otp) {
                            this.pending2FA.demo_otp = res.demo_otp;
                            if (btnFillEl) btnFillEl.classList.remove('hidden');
                        } else {
                            this.pending2FA.demo_otp = null;
                            if (btnFillEl) btnFillEl.classList.add('hidden');
                        }
                        const helpEl = document.getElementById('twoFactorHelpText');
                        if (helpEl) {
                            helpEl.textContent = "Enter the 6-digit verification code sent to your registered email address.";
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

                    this.clearPasswordFields();
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

    clearPasswordFields() {
        ['loginPassword', 'regPassword', 'pwdCurrent', 'pwdNew', 'pwdConfirm'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
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

            const hasFallback = data.enable_demo_otp === true && Boolean(data.demo_otp);
            if (btnFill) {
                btnFill.classList.toggle('hidden', !hasFallback);
            }
            if (helpEl) {
                helpEl.textContent = "Enter the 6-digit verification code sent to your registered email address.";
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

        // Section 7: Update sliding navigation active indicator
        this.updateNavIndicator(viewId);

        // Toggle view sections
        document.querySelectorAll('.view-section').forEach(sec => {
            sec.classList.toggle('active', sec.id === viewId);
        });

        // View-specific data loads
        if (viewId === 'view-landing') {
            this.loadPublicRecentReports();
        } else if (viewId === 'view-tracking') {
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

    updateNavIndicator(viewId) {
        const indicator = document.getElementById('navSlidingIndicator');
        const activeTab = document.querySelector(`.nav-tab[data-view="${viewId}"]`);
        if (!indicator) return;
        if (!activeTab || activeTab.classList.contains('hidden') || activeTab.offsetParent === null) {
            indicator.style.opacity = '0';
            return;
        }
        const left = activeTab.offsetLeft;
        const width = activeTab.offsetWidth;
        indicator.style.transform = `translateX(${left}px)`;
        indicator.style.width = `${width}px`;
        indicator.style.opacity = '1';
    },

    async checkBackendStatus() {
        try {
            const health = await window.Api.checkHealth();
            console.log("[InfraVision] Connected to backend service:", health);
        } catch (e) {
            console.warn("[InfraVision] Running in standalone frontend mode:", e);
        }
    },

    // Section 18-23: Citizen My Reports Master-Detail Explorer
    trackingViewMode: 'list',
    selectedTrackingReportId: null,

    setTrackingViewMode(mode) {
        this.trackingViewMode = mode;
        const btnListView = document.getElementById('btnTrackingListView');
        const btnGalleryView = document.getElementById('btnTrackingGalleryView');
        const listContainer = document.getElementById('trackingListContainer');
        const galleryContainer = document.getElementById('trackingGalleryContainer');

        if (mode === 'gallery') {
            if (btnGalleryView) {
                btnGalleryView.classList.add('active');
                btnGalleryView.style.background = '#2563eb';
                btnGalleryView.style.color = '#ffffff';
            }
            if (btnListView) {
                btnListView.classList.remove('active');
                btnListView.style.background = 'transparent';
                btnListView.style.color = '#94a3b8';
            }
            if (listContainer) listContainer.classList.add('hidden');
            if (galleryContainer) galleryContainer.classList.remove('hidden');
        } else {
            if (btnListView) {
                btnListView.classList.add('active');
                btnListView.style.background = '#2563eb';
                btnListView.style.color = '#ffffff';
            }
            if (btnGalleryView) {
                btnGalleryView.classList.remove('active');
                btnGalleryView.style.background = 'transparent';
                btnGalleryView.style.color = '#94a3b8';
            }
            if (galleryContainer) galleryContainer.classList.add('hidden');
            if (listContainer) listContainer.classList.remove('hidden');
        }

        if (this.selectedTrackingReportId) {
            this.highlightTrackingSelection(this.selectedTrackingReportId);
        }
    },

    closeTrackingDetail() {
        this.selectedTrackingReportId = null;
        document.querySelectorAll('.tracking-table-row').forEach(r => r.classList.remove('selected-tracking-row'));
        document.querySelectorAll('.citizen-report-card').forEach(c => c.classList.remove('selected-gallery-card'));

        const detailCol = document.getElementById('trackingDetailCol');
        if (detailCol) detailCol.classList.add('hidden');
        const detailCard = document.getElementById('trackingActiveDetailCard');
        if (detailCard) detailCard.classList.add('hidden');

        const explorerCol = document.getElementById('trackingExplorerCol');
        if (explorerCol) {
            explorerCol.style.flex = '1 1 100%';
            explorerCol.style.maxWidth = '100%';
        }
    },

    highlightTrackingSelection(canonicalId) {
        document.querySelectorAll('.tracking-table-row').forEach(r => r.classList.remove('selected-tracking-row'));
        document.querySelectorAll('.citizen-report-card').forEach(c => c.classList.remove('selected-gallery-card'));

        const rowEl = document.getElementById(`tracking-row-${canonicalId}`);
        if (rowEl) rowEl.classList.add('selected-tracking-row');
        const cardEl = document.getElementById(`tracking-card-${canonicalId}`);
        if (cardEl) cardEl.classList.add('selected-gallery-card');
    },

    // Citizen Tracking View (FR-08)
    async loadTrackingData() {
        const tbody = document.getElementById('trackingTableBody');
        const galleryGrid = document.getElementById('trackingGalleryGrid');
        if (!tbody) return;

        if (!this.currentUser) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align:center; padding: 2.5rem; color: #86868b;">
                        Please <button type="button" class="btn-micro btn-accent" onclick="window.App.showAuthView('login')">Sign In</button> to view your submitted infrastructure defect reports.
                    </td>
                </tr>`;
            if (galleryGrid) {
                galleryGrid.innerHTML = `
                    <div style="grid-column: 1 / -1; text-align: center; padding: 2.5rem; color: #86868b;">
                        Please <button type="button" class="btn-micro btn-accent" onclick="window.App.showAuthView('login')">Sign In</button> to view your submitted infrastructure defect reports.
                    </div>`;
            }
            this.closeTrackingDetail();
            return;
        }

        try {
            const data = await window.Api.getMyReports();
            const reports = data.reports || [];
            this.citizenReports = reports;

            if (reports.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="6" style="text-align:center; padding: 2.5rem; color: #86868b;">
                            No defect reports submitted yet. Use the 'Report Defect' tab to photograph and submit an infrastructure defect!
                        </td>
                    </tr>`;
                if (galleryGrid) {
                    galleryGrid.innerHTML = `
                        <div style="grid-column: 1 / -1; text-align: center; padding: 2.5rem; color: #86868b;">
                            No defect reports submitted yet. Use the 'Report Defect' tab to photograph and submit an infrastructure defect!
                        </div>`;
                }
                this.closeTrackingDetail();
                return;
            }

            // Section 20: Render List View Rows with High-Contrast Typography
            tbody.innerHTML = reports.map((item) => {
                const rep = item.report;
                const ai = item.assessment || {};
                const sev = (ai.relative_severity || rep.metadata?.relative_severity || 'Low').toLowerCase();
                const status = rep.status || 'Received';
                const statusSlug = status.toLowerCase().replace(/\s+/g, '-');
                const isUnusual = rep.metadata?.is_unusual === true || rep.validation_status === 'unusual';
                const dateStr = rep.date_submitted ? new Date(rep.date_submitted).toLocaleDateString('en-KE', { dateStyle: 'medium' }) : 'Recent';
                const location = rep.metadata?.location_name || 'Corridor Asset';
                const canonicalId = rep.report_id || String(rep._id);
                const rawDisplayId = rep.display_id || (rep.report_id ? `#REP-${rep.report_id.slice(-6).toUpperCase()}` : `#REP-${String(rep._id).slice(-6).toUpperCase()}`);
                const displayId = rawDisplayId.startsWith('#') ? rawDisplayId : '#' + rawDisplayId;
                const imgUrl = item.image_url ? window.Api.resolveImageUrl(item.image_url) : (rep.metadata?.image_url ? window.Api.resolveImageUrl(rep.metadata.image_url) : '');

                return `
                    <tr class="tracking-table-row" id="tracking-row-${canonicalId}" style="cursor: pointer;" onclick="App.selectTrackingReport('${canonicalId}')">
                        <td style="width: 56px; padding: 6px 12px;">
                            ${imgUrl ? `<img src="${imgUrl}" class="tracking-evidence-thumb" alt="Defect" style="width: 44px; height: 44px; object-fit: cover; border-radius: 6px; border: 1px solid #cbd5e1;" onerror="this.parentElement.innerHTML='<div class=\\'tracking-evidence-thumb\\' style=\\'width:44px;height:44px;background:#f1f5f9;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#64748b;\\'><i class=\\\'bx bx-image\\\'></i></div>'">` : `<div class="tracking-evidence-thumb" style="width:44px;height:44px;background:#f1f5f9;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#64748b;"><i class='bx bx-image'></i></div>`}
                        </td>
                        <td>
                            <strong style="color: #0f172a; display: block; font-size: 0.88rem; font-weight: 700;">${location}</strong>
                            <code style="font-size: 0.72rem; color: #475569; font-weight: 600;">${displayId}</code>
                        </td>
                        <td>
                            <span style="font-weight: 600; color: #1e293b;">${ai.defect_class || rep.metadata?.defect_class || 'Pavement Distress'}</span>
                        </td>
                        <td>
                            <span class="severity-pill ${sev}">${sev.toUpperCase()}</span>
                        </td>
                        <td>
                            <span class="status-chip ${statusSlug}">${status}</span>
                            ${isUnusual ? `<span class="badge-tag" style="background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;margin-left:4px;"><i class='bx bx-error-circle'></i> Unusual</span>` : ''}
                        </td>
                        <td style="color: #334155; font-size: 0.82rem; font-weight: 500;">${dateStr}</td>
                    </tr>
                `;
            }).join('');

            // Section 20: Render Gallery View Cards with High-Contrast Typography
            if (galleryGrid) {
                galleryGrid.innerHTML = reports.map((item) => {
                    const rep = item.report;
                    const ai = item.assessment || {};
                    const sev = (ai.relative_severity || rep.metadata?.relative_severity || 'Low').toLowerCase();
                    const status = rep.status || 'Received';
                    const statusSlug = status.toLowerCase().replace(/\s+/g, '-');
                    const dateStr = rep.date_submitted ? new Date(rep.date_submitted).toLocaleDateString('en-KE', { dateStyle: 'medium' }) : 'Recent';
                    const location = rep.metadata?.location_name || 'Corridor Asset';
                    const canonicalId = rep.report_id || String(rep._id);
                    const defect = ai.defect_class || rep.metadata?.defect_class || 'Pavement Distress';
                    const imgUrl = item.image_url ? window.Api.resolveImageUrl(item.image_url) : (rep.metadata?.image_url ? window.Api.resolveImageUrl(rep.metadata.image_url) : '');
                    const isMultiView = Boolean(rep.combined_multi_view_assessment || rep.metadata?.combined_multi_view_assessment);

                    return `
                        <div class="citizen-report-card" id="tracking-card-${canonicalId}" style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; cursor: pointer; transition: all 0.2s ease; box-shadow: 0 1px 3px rgba(15,23,42,0.06);" onclick="App.selectTrackingReport('${canonicalId}')">
                            <div class="report-card-media" style="position: relative; width: 100%; height: 160px; background: #f1f5f9;">
                                ${imgUrl ? `<img src="${imgUrl}" alt="${defect}" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.parentElement.style.background='#f1f5f9'">` : `<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#64748b;"><i class='bx bx-image' style="font-size:2rem;"></i></div>`}
                                <div style="position: absolute; top: 8px; left: 8px;">
                                    <span class="severity-pill ${sev}" style="font-size: 0.7rem; padding: 2px 8px;">${sev.toUpperCase()}</span>
                                </div>
                                ${isMultiView ? `<div style="position: absolute; top: 8px; right: 8px; background: rgba(15,23,42,0.85); color: #38bdf8; font-size: 0.68rem; font-weight: 600; padding: 2px 6px; border-radius: 4px; border: 1px solid #38bdf8;"><i class='bx bx-layer'></i> Multi-View</div>` : ''}
                            </div>
                            <div class="report-card-body" style="padding: 0.9rem; display: flex; flex-direction: column; gap: 0.45rem;">
                                <div style="font-size: 0.92rem; font-weight: 700; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${location}">
                                    <i class='bx bx-map-pin' style="color: #0284c7;"></i> ${location}
                                </div>
                                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.82rem;">
                                    <span style="font-weight: 600; color: #1e293b;">${defect}</span>
                                    <span class="status-chip ${statusSlug}" style="font-size: 0.68rem; padding: 2px 8px;">${status}</span>
                                </div>
                                <div style="font-size: 0.75rem; color: #475569; border-top: 1px solid #f1f5f9; padding-top: 0.45rem; margin-top: 0.2rem; display: flex; justify-content: space-between; align-items: center;">
                                    <span><i class='bx bx-calendar'></i> ${dateStr}</span>
                                    <span style="color: #2563eb; font-weight: 600;">View Details &rarr;</span>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            // Section 18 & 21: Default: NO report detail open by default!
            if (this.selectedTrackingReportId) {
                this.selectTrackingReport(this.selectedTrackingReportId, false);
            } else {
                this.closeTrackingDetail();
            }
        } catch (e) {
            console.error("Failed to load tracking data:", e);
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: #dc2626;">Failed to load defect reports.</td></tr>`;
        }
    },

    selectTrackingReport(reportId, scroll = true) {
        if (!this.citizenReports || this.citizenReports.length === 0) return;
        const item = this.citizenReports.find(r => (
            r.report.report_id === reportId ||
            r.report._id === reportId ||
            String(r.report._id) === String(reportId) ||
            r.report.display_id === reportId ||
            String(r.report.display_id) === String(reportId)
        ));
        if (!item) return;

        const rep = item.report;
        const canonicalId = rep.report_id || String(rep._id);
        this.selectedTrackingReportId = canonicalId;

        // Section 21: Highlight selected row and card
        this.highlightTrackingSelection(canonicalId);

        // Section 21 & 22: Open detail column and adjust master-detail proportions
        const detailCol = document.getElementById('trackingDetailCol');
        const explorerCol = document.getElementById('trackingExplorerCol');
        const cardEl = document.getElementById('trackingActiveDetailCard');
        if (detailCol) detailCol.classList.remove('hidden');
        if (cardEl) cardEl.classList.remove('hidden');

        if (explorerCol && window.innerWidth >= 992) {
            explorerCol.style.flex = '1 1 58%';
            explorerCol.style.maxWidth = '58%';
        }

        const ai = item.assessment || {};
        const rev = item.review || {};
        const status = rep.status || 'Received';
        const statusSlug = status.toLowerCase().replace(/\s+/g, '-');
        const dateStr = rep.date_submitted ? new Date(rep.date_submitted).toLocaleString('en-KE', { dateStyle: 'medium', timeStyle: 'short' }) : 'Recently Submitted';
        const location = rep.metadata?.location_name || 'Corridor Asset';
        const asset = rep.metadata?.asset_type || 'Road / Pavement';
        const defect = ai.defect_class || rep.metadata?.defect_class || 'Pavement Distress';
        const sev = (ai.relative_severity || rep.metadata?.relative_severity || 'Low').toUpperCase();
        const conf = ai.confidence_score ? `${(ai.confidence_score * 100).toFixed(1)}%` : (rep.metadata?.confidence ? `${(rep.metadata.confidence * 100).toFixed(1)}%` : '—');
        const areaRatio = ai.bounding_box && Array.isArray(ai.bounding_box) && ai.bounding_box.length === 4
            ? `${((ai.bounding_box[2] - ai.bounding_box[0]) * (ai.bounding_box[3] - ai.bounding_box[1]) * 100).toFixed(1)}%`
            : '—';
        const imgUrl = item.image_url ? (window.Api.resolveImageUrl(item.image_url)) : (rep.metadata?.image_url ? window.Api.resolveImageUrl(rep.metadata.image_url) : '');
        const lat = rep.metadata?.latitude || (rep.latitude || null);
        const lng = rep.metadata?.longitude || (rep.longitude || null);
        const rawDisplayId = rep.display_id || (rep.report_id ? `#REP-${rep.report_id.slice(-6).toUpperCase()}` : `#REP-${String(rep._id).slice(-6).toUpperCase()}`);
        const displayId = rawDisplayId.startsWith('#') ? rawDisplayId : '#' + rawDisplayId;

        // Stages: 1: Received, 2: Under Review, 3: Verified, 4: Resolved
        const stages = ['Received', 'Under Review', 'Verified', 'Resolved'];
        const currentIdx = stages.indexOf(status) >= 0 ? stages.indexOf(status) : 0;
        const fillPercent = (currentIdx / 3) * 100;

        let stageSummary = '';
        let whatHappensNext = '';
        if (status === 'Received') {
            stageSummary = 'Report received and registered into the defect monitoring pipeline.';
            whatHappensNext = 'Your defect report is queued for engineering evaluation. An accredited civil engineer will inspect the photographic evidence, analyze relative severity, and assign inspection priority.';
        } else if (status === 'Under Review') {
            stageSummary = 'Active engineering inspection and severity assessment in progress.';
            whatHappensNext = 'An accredited civil engineer is actively assessing this defect, evaluating visual extent, and determining maintenance priority or dispatch requirements.';
        } else if (status === 'Verified') {
            stageSummary = 'Defect confirmed and officially validated by an accredited civil engineer.';
            whatHappensNext = 'Engineering validation is complete. Remediation or maintenance has been recommended and logged for infrastructure asset servicing.';
        } else if (status === 'Resolved') {
            stageSummary = 'Defect remediation verified complete. Case officially closed.';
            whatHappensNext = 'Remediation and site maintenance have addressed this defect. The infrastructure record is archived as resolved.';
        }

        const reviewerName = rev.reviewer_name || (rep.metadata?.status_history && rep.metadata.status_history.slice(-1)[0]?.updated_by) || (status !== 'Received' ? 'Accredited Civil Engineer' : null);
        const reviewDate = rev.review_date ? new Date(rev.review_date).toLocaleString('en-KE', { dateStyle: 'medium', timeStyle: 'short' }) : (rep.metadata?.status_history && rep.metadata.status_history.slice(-1)[0]?.timestamp ? new Date(rep.metadata.status_history.slice(-1)[0].timestamp).toLocaleString('en-KE', { dateStyle: 'medium', timeStyle: 'short' }) : null);
        const nextAction = rev.next_action || rep.metadata?.next_action || (status === 'Verified' ? 'Refer to maintenance team' : (status === 'Resolved' ? 'No further action required' : 'Engineering assessment pending'));
        const followUpDate = rev.follow_up_date || rep.metadata?.follow_up_date || null;
        const reviewNotes = rev.notes || (rep.metadata?.status_history && rep.metadata.status_history.slice(-1)[0]?.notes) || (status !== 'Received' ? 'Engineering validation in progress.' : 'Awaiting professional assessment.');

        // Section 20-24: Clean, high-contrast, cohesive layout with Show on Map action
        // Location + submitted date -> Evidence image -> Lifecycle -> Defect Assessment -> Professional Review -> Next Action / Target Date -> Engineer Notes -> Show on Map
        cardEl.innerHTML = `
            <!-- 1. Location + Submitted Date + Close Button -->
            <div class="tracking-card-header" style="display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: 0.75rem; border-bottom: 1px solid #e2e8f0; margin-bottom: 1rem;">
                <div class="tracking-card-title-group" style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <i class='bx bx-map-pin' style="color: #0284c7; font-size: 1.15rem;"></i>
                        <h3 style="margin: 0; font-size: 1.05rem; font-weight: 700; color: #0f172a;">${location}</h3>
                    </div>
                    <p style="margin: 0.25rem 0 0 0; font-size: 0.78rem; color: #475569;">
                        Submitted on <strong style="color: #1e293b;">${dateStr}</strong> &bull; Case Ref: <code style="color: #0284c7; font-weight: 600;">${displayId}</code>
                    </p>
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <span class="status-chip ${statusSlug}" style="font-size: 0.72rem; padding: 2px 8px;">${status}</span>
                    <button type="button" class="btn-close-detail" onclick="App.closeTrackingDetail()" title="Close details" style="background: transparent; border: 1px solid #cbd5e1; color: #64748b; border-radius: 6px; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 1.1rem; line-height: 1;">
                        <i class='bx bx-x'></i>
                    </button>
                </div>
            </div>

            <!-- 2. Evidence Image / Gallery -->
            ${imgUrl ? `
            <div style="width: 100%; height: 180px; border-radius: 8px; overflow: hidden; background: #f8fafc; margin-bottom: 1rem; border: 1px solid #e2e8f0;">
                <img src="${imgUrl}" alt="Defect Evidence" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.parentElement.style.display='none'">
            </div>` : ''}

            <!-- 3. Current Lifecycle Progression Stepper -->
            <div class="tracking-stepper-container" style="margin-bottom: 1rem;">
                <div class="tracking-stepper">
                    <div class="tracking-stepper-line">
                        <div class="tracking-stepper-fill" style="width: ${fillPercent}%;"></div>
                    </div>
                    <div class="tracking-step ${currentIdx > 0 ? 'completed' : (currentIdx === 0 ? 'active' : 'upcoming')}">
                        <div class="tracking-step-node"><i class='bx ${currentIdx > 0 ? 'bx-check' : 'bx-clipboard'}'></i></div>
                        <span class="tracking-step-title">1. Received</span>
                        <span class="tracking-step-sub">Registered</span>
                    </div>
                    <div class="tracking-step ${currentIdx > 1 ? 'completed' : (currentIdx === 1 ? 'active' : 'upcoming')}">
                        <div class="tracking-step-node"><i class='bx ${currentIdx > 1 ? 'bx-check' : 'bx-time'}'></i></div>
                        <span class="tracking-step-title">2. Under Review</span>
                        <span class="tracking-step-sub">Assessing</span>
                    </div>
                    <div class="tracking-step ${currentIdx > 2 ? 'completed' : (currentIdx === 2 ? 'active' : 'upcoming')}">
                        <div class="tracking-step-node"><i class='bx ${currentIdx > 2 ? 'bx-check' : 'bx-badge-check'}'></i></div>
                        <span class="tracking-step-title">3. Verified</span>
                        <span class="tracking-step-sub">Validated</span>
                    </div>
                    <div class="tracking-step ${currentIdx === 3 ? 'completed active' : 'upcoming'}">
                        <div class="tracking-step-node"><i class='bx ${currentIdx === 3 ? 'bx-check-double' : 'bx-check-circle'}'></i></div>
                        <span class="tracking-step-title">4. Resolved</span>
                        <span class="tracking-step-sub">Remediated</span>
                    </div>
                </div>
            </div>

            <div class="tracking-summary-panel" style="margin-bottom: 1rem; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.75rem 1rem;">
                <div style="font-weight: 700; color: #0f172a; font-size: 0.88rem; margin-bottom: 3px;">${stageSummary}</div>
                <div style="color: #475569; font-size: 0.8rem; line-height: 1.4;"><strong style="color:#0f172a;">Next step:</strong> ${whatHappensNext}</div>
            </div>

            <!-- 4. Defect Assessment & 5. Professional Review -->
            <div style="display: flex; flex-direction: column; gap: 0.75rem;">
                <!-- 4. Defect Assessment -->
                <div class="tracking-info-box" style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.75rem 1rem;">
                    <div class="tracking-info-title" style="font-weight: 700; color: #0284c7; font-size: 0.82rem; text-transform: uppercase; margin-bottom: 0.5rem;">
                        <i class='bx bx-scan'></i> Defect Assessment
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.82rem;">
                        <div style="display: flex; justify-content: space-between;"><span style="color: #475569; font-weight: 500;">Defect Class:</span><strong style="color: #0f172a;">${defect}</strong></div>
                        <div style="display: flex; justify-content: space-between;"><span style="color: #475569; font-weight: 500;">Infrastructure:</span><span style="color: #1e293b; font-weight: 600;">${asset}</span></div>
                        <div style="display: flex; justify-content: space-between;"><span style="color: #475569; font-weight: 500;">Visual Severity:</span><span class="severity-pill ${sev.toLowerCase()}">${sev}</span></div>
                        <div style="display: flex; justify-content: space-between;"><span style="color: #475569; font-weight: 500;">Model Confidence:</span><span style="color: #1e293b; font-weight: 600;">${conf}</span></div>
                        <div style="display: flex; justify-content: space-between;"><span style="color: #475569; font-weight: 500;">Defect Extent:</span><span style="color: #1e293b; font-weight: 600;">${areaRatio}</span></div>
                    </div>
                </div>

                <!-- 5. Professional Engineering Review & 6. Next Action / Target Date -->
                <div class="tracking-info-box" style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.75rem 1rem;">
                    <div class="tracking-info-title" style="font-weight: 700; color: #059669; font-size: 0.82rem; text-transform: uppercase; margin-bottom: 0.5rem;">
                        <i class='bx bx-user-check'></i> Professional Engineering Review
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.82rem;">
                        <div style="display: flex; justify-content: space-between;"><span style="color: #475569; font-weight: 500;">Reviewer:</span><strong style="color: #0f172a;">${reviewerName || 'Queue Pending'}</strong></div>
                        ${reviewDate ? `<div style="display: flex; justify-content: space-between;"><span style="color: #475569; font-weight: 500;">Validated Date:</span><span style="color: #1e293b; font-weight: 600;">${reviewDate}</span></div>` : ''}
                        <div style="display: flex; justify-content: space-between; align-items: center;"><span style="color: #475569; font-weight: 500;">Next Action:</span><span style="font-weight: 600; color: #2563eb;">${nextAction}</span></div>
                        ${followUpDate ? `<div style="display: flex; justify-content: space-between;"><span style="color: #475569; font-weight: 500;">Target Date:</span><strong style="color: #d97706;">${followUpDate}</strong></div>` : ''}
                        
                        <!-- 7. Engineer Notes -->
                        <div style="border-top: 1px solid #e2e8f0; padding-top: 0.45rem; margin-top: 0.2rem;">
                            <span style="color: #475569; font-size: 0.75rem; font-weight: 600; display: block; margin-bottom: 2px;">Engineer Remarks:</span>
                            <p style="margin: 0; color: #1e293b; font-size: 0.82rem; font-style: italic; line-height: 1.4;">"${reviewNotes}"</p>
                        </div>
                    </div>
                </div>

                <!-- Section 24: Show on Map Action -->
                ${(lat !== null && lng !== null && lat !== undefined && lng !== undefined) ? `
                    <button type="button" class="btn-secondary btn-sm btn-show-on-map" style="width: 100%; margin-top: 0.5rem; display: flex; align-items: center; justify-content: center; gap: 6px; font-weight: 600; color: #0284c7; border: 1px solid #bae6fd; background: #f0f9ff; padding: 8px 12px; border-radius: 6px; cursor: pointer; transition: all 0.15s ease;" onclick="window.App.navigateTo('view-map'); window.DefectMap?.showReportOnMap('${canonicalId}', ${lat}, ${lng});">
                        <i class='bx bx-map-pin' style="font-size: 1.15rem;"></i> Show on Infrastructure Map
                    </button>
                ` : ''}
            </div>
        `;

        if (scroll && window.innerWidth <= 768) {
            cardEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
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
                const isAdvisory = n.event_type === 'safety_advisory' || n.category === 'safety_advisory' || (n.title && n.title.includes('Safety Advisory'));
                const isCitizenLifecycle = ['verified', 'resolved', 'override'].includes(n.event_type) || (!isAdvisory && n.report_id && this.currentUser?.role === 'citizen');
                const isEngineerReview = !isAdvisory && n.report_id && (this.currentUser?.role === 'engineer');
                const isAdminGovernance = !isAdvisory && (this.currentUser?.role === 'admin' && (n.event_type === 'engineer_registered' || !n.report_id));

                let linkText = '';
                if (isAdvisory) {
                    linkText = 'View on Infrastructure Map →';
                } else if (isCitizenLifecycle) {
                    linkText = 'Track Report →';
                } else if (isEngineerReview) {
                    linkText = 'Inspect in Defect Review →';
                } else if (isAdminGovernance) {
                    linkText = 'User Governance →';
                } else if (n.report_id) {
                    linkText = 'View Report Details →';
                }

                const advisoryId = n.metadata?.advisory_id || n.advisory_id || '';
                const lat = n.metadata?.latitude !== undefined ? n.metadata.latitude : (n.latitude !== undefined ? n.latitude : '');
                const lng = n.metadata?.longitude !== undefined ? n.metadata.longitude : (n.longitude !== undefined ? n.longitude : '');

                return `
                    <div class="notification-item ${isUnread ? 'unread' : ''}" data-id="${n.notification_id || n._id}" data-report-id="${n.report_id || ''}" data-is-advisory="${isAdvisory}" data-advisory-id="${advisoryId}" data-lat="${lat}" data-lng="${lng}">
                        <div class="notification-item-header">
                            <span class="notification-item-title">${n.title || 'Report Feedback'}</span>
                            <span class="notification-item-time">${timeStr}</span>
                        </div>
                        <div class="notification-item-message">${n.message}</div>
                        ${linkText ? `<div class="notification-item-link">${linkText}</div>` : ''}
                    </div>
                `;
            }).join('');

            // Bind click to each notification item
            listEl.querySelectorAll('.notification-item').forEach(item => {
                item.addEventListener('click', async () => {
                    const notifId = item.getAttribute('data-id');
                    const reportId = item.getAttribute('data-report-id');
                    const isAdvisory = item.getAttribute('data-is-advisory') === 'true';
                    const advisoryId = item.getAttribute('data-advisory-id');
                    const lat = parseFloat(item.getAttribute('data-lat'));
                    const lng = parseFloat(item.getAttribute('data-lng'));

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

                    if (isAdvisory) {
                        this.navigateTo('view-map');
                        if (window.DefectMap) {
                            window.DefectMap.focusOnAdvisory(advisoryId, reportId, !isNaN(lat) ? lat : null, !isNaN(lng) ? lng : null);
                        }
                    } else if (reportId) {
                        if (this.currentUser?.role === 'engineer') {
                            this.navigateTo('view-review', reportId);
                        } else if (this.currentUser?.role === 'admin') {
                            this.navigateTo('view-admin');
                        } else {
                            this.navigateTo('view-tracking');
                            setTimeout(() => {
                                this.selectTrackingReport(reportId, true);
                            }, 250);
                        }
                    } else if (this.currentUser?.role === 'admin') {
                        this.navigateTo('view-admin');
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
                const ebkCat = u.engineering_category || '';
                const regNo = u.professional_reg_no || u.ebk_reg_no || '';
                const orgLine = u.organization || '';
                const detailParts = [orgLine, ebkCat, regNo ? `EBK: ${regNo}` : ''].filter(Boolean);
                const orgInfo = detailParts.length > 0 ? detailParts.join(' • ') : '—';
                const has2fa = u.two_factor_enabled ? '<span style="color:#16a34a; font-weight:600;"><i class=\'bx bx-shield-quarter\'></i> Enabled</span>' : '<span style="color:#86868b;">Disabled</span>';
                const verifClass = isVerified ? 'verified' : (u.verification_status === 'rejected' ? 'rejected' : 'pending');
                const reasonTooltip = u.rejection_reason ? `title="Rejection Reason: ${u.rejection_reason}"` : '';
                const auditActor = isVerified
                    ? (u.verified_by_name ? `Verified by ${u.verified_by_name}` : '')
                    : (u.verification_status === 'rejected' && u.rejected_by_name ? `Rejected by ${u.rejected_by_name}` : '');
                const auditTime = isVerified ? u.verified_at : (u.verification_status === 'rejected' ? u.rejected_at : '');
                const auditDateStr = auditTime ? new Date(auditTime).toLocaleDateString('en-KE', { dateStyle: 'medium' }) : '';
                const auditLine = auditActor ? `<div style="font-size:0.7rem; color:#64748b; margin-top:2px;">${auditActor}${auditDateStr ? ` • ${auditDateStr}` : ''}</div>` : '';

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
                            ${auditLine}
                        </td>
                        <td>
                            <div style="display:flex; align-items:center; gap:4px; flex-wrap:wrap;">
                                ${isEngineer ? `
                                    <a href="https://engineers.ebk.go.ke/" target="_blank" rel="noopener noreferrer" class="btn-micro" style="padding: 2px 6px; font-size: 0.74rem; text-decoration: none;" title="Open official EBK Register to verify ${regNo || u.name}">
                                        <i class='bx bx-link-external'></i> EBK Register
                                    </a>
                                ` : ''}
                                ${isEngineer && !isVerified ? `
                                    <button type="button" class="btn-action-verify" onclick="App.handleVerifyUser('${uid}', 'verified')">
                                        <i class='bx bx-user-check'></i> Verify
                                    </button>
                                    ${u.verification_status !== 'rejected' ? `
                                    <button type="button" class="btn-action-reject" onclick="App.openRejectionModal('${uid}', '${(u.name || 'Engineer').replace(/'/g, "\\'")}', '${u.email}')">
                                        <i class='bx bx-user-x'></i> Reject
                                    </button>` : ''}
                                ` : (!isEngineer ? `<span style="color: #86868b; font-size: 0.8rem;">Active</span>` : '')}
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
        if (selectEl) selectEl.value = 'Unable to verify EBK registration';
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
                const reason = reasonSelect ? reasonSelect.value : 'Unable to verify EBK registration';
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
                        this.loadAdminDashboard().catch(() => { });
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

    async openTargetedNotice(userId, name, email) {
        const modal = document.getElementById('adminNoticeModal');
        const modeSelect = document.getElementById('adminNoticeMode');
        const targetGroup = document.getElementById('adminNoticeTargetGroup');
        const audienceGroup = document.getElementById('adminNoticeAudienceGroup');
        const targetUserSelect = document.getElementById('adminNoticeTargetUser');
        const catSelect = document.getElementById('adminNoticeCategory');
        const titleInput = document.getElementById('adminNoticeTitleInput');
        const msgText = document.getElementById('adminNoticeMessage');

        if (modeSelect) modeSelect.value = 'targeted';
        if (targetGroup) targetGroup.classList.remove('hidden');
        if (audienceGroup) audienceGroup.classList.add('hidden');

        if (catSelect) {
            catSelect.innerHTML = `
                <option value="Credential correction request" selected>Credential correction request</option>
                <option value="Verification information">Verification information</option>
                <option value="Account / security notice">Account / security notice</option>
                <option value="Administrative account message">Administrative account message</option>
            `;
        }

        try {
            const data = await window.Api.getUsers();
            const users = data.users || [];
            if (targetUserSelect) {
                targetUserSelect.innerHTML = `<option value="">Select recipient...</option>` +
                    users.map(u => {
                        const uid = u.user_id || u._id;
                        return `<option value="${uid}" ${uid === userId ? 'selected' : ''}>${u.name} (${u.email}) [${u.role.toUpperCase()}]</option>`;
                    }).join('');
                if (userId) targetUserSelect.value = userId;
            }
        } catch (e) {
            console.warn("Failed to load users for targeted notice:", e);
        }

        if (titleInput) titleInput.value = `Credential correction request: ${name || 'User'}`;
        if (msgText) msgText.value = '';
        if (modal) modal.classList.add('active');
    },

    openSystemNotice() {
        const modal = document.getElementById('adminNoticeModal');
        const modeSelect = document.getElementById('adminNoticeMode');
        const targetGroup = document.getElementById('adminNoticeTargetGroup');
        const audienceGroup = document.getElementById('adminNoticeAudienceGroup');
        const audienceSelect = document.getElementById('adminNoticeAudience');
        const catSelect = document.getElementById('adminNoticeCategory');
        const titleInput = document.getElementById('adminNoticeTitleInput');
        const msgText = document.getElementById('adminNoticeMessage');

        if (modeSelect) modeSelect.value = 'broadcast';
        if (targetGroup) targetGroup.classList.add('hidden');
        if (audienceGroup) audienceGroup.classList.remove('hidden');
        if (audienceSelect) audienceSelect.value = 'all';

        if (catSelect) {
            catSelect.innerHTML = `
                <option value="Platform Announcement" selected>Platform Announcement</option>
                <option value="Scheduled Maintenance">Scheduled Maintenance</option>
                <option value="Emergency / Weather Infrastructure Advisory">Emergency / Weather Infrastructure Advisory</option>
                <option value="Operational Notice">Operational Notice</option>
            `;
        }

        if (titleInput) titleInput.value = 'InfraVision: Platform Announcement';
        if (msgText) msgText.value = '';
        if (modal) modal.classList.add('active');
    },

    bindAdminNoticeModal() {
        const modal = document.getElementById('adminNoticeModal');
        const btnOpen = document.getElementById('btnOpenAdminNotice');
        const btnOpenSystem = document.getElementById('btnOpenSystemNotice');
        const btnCancel = document.getElementById('btnCancelAdminNotice');
        const btnClose = document.getElementById('btnCloseAdminNotice');
        const btnConfirm = document.getElementById('btnConfirmAdminNotice');
        const modeSelect = document.getElementById('adminNoticeMode');
        const targetGroup = document.getElementById('adminNoticeTargetGroup');
        const audienceGroup = document.getElementById('adminNoticeAudienceGroup');
        const targetUserSelect = document.getElementById('adminNoticeTargetUser');
        const audienceSelect = document.getElementById('adminNoticeAudience');
        const catSelect = document.getElementById('adminNoticeCategory');
        const titleInput = document.getElementById('adminNoticeTitleInput');
        const msgText = document.getElementById('adminNoticeMessage');

        const closeModal = () => {
            if (modal) modal.classList.remove('active');
        };

        if (btnOpen) {
            btnOpen.addEventListener('click', () => this.openTargetedNotice());
        }

        if (btnOpenSystem) {
            btnOpenSystem.addEventListener('click', () => this.openSystemNotice());
        }

        if (modeSelect) {
            modeSelect.addEventListener('change', (e) => {
                const isBroadcast = e.target.value === 'broadcast';
                if (targetGroup) {
                    if (isBroadcast) targetGroup.classList.add('hidden');
                    else targetGroup.classList.remove('hidden');
                }
                if (audienceGroup) {
                    if (isBroadcast) audienceGroup.classList.remove('hidden');
                    else audienceGroup.classList.add('hidden');
                }
                if (catSelect) {
                    if (isBroadcast) {
                        catSelect.innerHTML = `
                            <option value="Platform Announcement" selected>Platform Announcement</option>
                            <option value="Scheduled Maintenance">Scheduled Maintenance</option>
                            <option value="Emergency / Weather Infrastructure Advisory">Emergency / Weather Infrastructure Advisory</option>
                            <option value="Operational Notice">Operational Notice</option>
                        `;
                        if (titleInput) titleInput.value = 'InfraVision: Platform Announcement';
                    } else {
                        catSelect.innerHTML = `
                            <option value="Credential correction request" selected>Credential correction request</option>
                            <option value="Verification information">Verification information</option>
                            <option value="Account / security notice">Account / security notice</option>
                            <option value="Administrative account message">Administrative account message</option>
                        `;
                        if (titleInput) titleInput.value = 'InfraVision: Credential correction request';
                    }
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
                const audience = audienceSelect ? audienceSelect.value : 'all';
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
                        audience: audience,
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
                this.loadAdminDashboard().catch(() => { });
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

    bindLandingEvents() {
        document.getElementById('btnLandingReport')?.addEventListener('click', () => this.navigateTo('view-submit'));
        document.getElementById('btnEditorialReportRoad')?.addEventListener('click', () => this.navigateTo('view-submit'));
        document.getElementById('btnRoleCitizenSubmit')?.addEventListener('click', () => this.navigateTo('view-submit'));

        document.getElementById('btnLandingExploreMap')?.addEventListener('click', () => this.navigateTo('view-map'));
        document.getElementById('btnEditorialExploreMap')?.addEventListener('click', () => this.navigateTo('view-map'));
        document.getElementById('btnLandingViewMap')?.addEventListener('click', () => this.navigateTo('view-map'));
        document.getElementById('btnRoleAuthorityMap')?.addEventListener('click', () => this.navigateTo('view-map'));

        document.getElementById('btnLandingHeroSignIn')?.addEventListener('click', () => this.showAuthView('login'));
        document.getElementById('btnLandingHeroRegister')?.addEventListener('click', () => this.showAuthView('register'));
        document.getElementById('btnFooterSignIn')?.addEventListener('click', () => this.showAuthView('login'));
        document.getElementById('btnFooterRegister')?.addEventListener('click', () => this.showAuthView('register'));

        document.getElementById('btnRoleEngineerRegister')?.addEventListener('click', () => {
            this.showAuthView('register');
            const roleSel = document.getElementById('regRole');
            if (roleSel) {
                roleSel.value = 'engineer';
                roleSel.dispatchEvent(new Event('change'));
            }
        });

        document.querySelectorAll('.footer-nav-link[data-nav]').forEach(btn => {
            btn.addEventListener('click', () => {
                const targetView = btn.getAttribute('data-nav');
                if (targetView) this.navigateTo(targetView);
            });
        });

        const track = document.getElementById('landingEditorialTrack');
        document.getElementById('btnLandingCarouselPrev')?.addEventListener('click', () => {
            if (track) track.scrollBy({ left: -340, behavior: 'smooth' });
        });
        document.getElementById('btnLandingCarouselNext')?.addEventListener('click', () => {
            if (track) track.scrollBy({ left: 340, behavior: 'smooth' });
        });
    },

    async loadPublicRecentReports() {
        const grid = document.getElementById('landingRecentReportsGrid');
        if (!grid) return;

        try {
            const data = await window.Api.getPublicRecentReports(6);
            const items = data.reports || [];

            if (items.length === 0) {
                grid.innerHTML = `<div class="landing-recent-empty">No public infrastructure defect reports recorded yet. Use <strong>Report a Defect</strong> above to submit an initial report.</div>`;
                return;
            }

            grid.innerHTML = items.map(rep => {
                const sev = (rep.relative_severity || 'Low').toUpperCase();
                const status = rep.status || 'Received';
                const statusSlug = status.toLowerCase().replace(/\s+/g, '-');
                const dateStr = rep.date_submitted
                    ? new Date(rep.date_submitted).toLocaleDateString('en-KE', { dateStyle: 'medium' })
                    : 'Recent';
                const thumbUrl = rep.thumbnail_url ? (window.Api.resolveImageUrl(rep.thumbnail_url) || rep.thumbnail_url) : '';
                const rvsiChip = (rep.rvsi_score !== null && rep.rvsi_score !== undefined)
                    ? `<span class="recent-rvsi-chip">RVSI ${Number(rep.rvsi_score).toFixed(1)}</span>`
                    : '';

                return `
                    <div class="landing-recent-card glass-card" tabindex="0" role="button" data-view-map="true">
                        <div class="recent-card-thumb ${thumbUrl ? '' : 'no-thumb'}">
                            ${thumbUrl
                        ? `<img src="${thumbUrl}" alt="${rep.defect_class || 'Infrastructure defect'}" onerror="this.style.display='none'; this.parentElement.classList.add('no-thumb');">`
                        : ''}
                            <span class="recent-thumb-fallback"><i class='bx bx-map-pin'></i></span>
                        </div>
                        <div class="recent-card-body">
                            <div class="recent-card-top">
                                <span class="recent-defect-title">${rep.defect_class || 'Surface Defect'}</span>
                                <span class="severity-pill ${sev.toLowerCase()}">${sev}</span>
                            </div>
                            <div class="recent-card-location">${rep.location_name || 'Monitored Corridor'}</div>
                            <div class="recent-card-meta">
                                <span class="status-chip ${statusSlug}">${status}</span>
                                ${rvsiChip}
                                <span class="recent-date-text">${rep.asset_type || 'Asset'} • ${dateStr}</span>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            grid.querySelectorAll('.landing-recent-card').forEach(card => {
                const openMap = () => this.navigateTo('view-map');
                card.addEventListener('click', openMap);
                card.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        openMap();
                    }
                });
            });
        } catch (err) {
            console.warn('[Landing] Failed loading recent public reports:', err);
            grid.innerHTML = `<div class="landing-recent-empty">Recent monitoring activity is currently unavailable.</div>`;
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
