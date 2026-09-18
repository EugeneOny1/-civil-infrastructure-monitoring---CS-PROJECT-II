/**
 * App Module - Routing, State Management & Role Governance
 */
const App = {
    currentRole: 'engineer',

    init() {
        this.bindNavigation();
        this.bindRoleSelector();
        
        // Initialize sub-modules
        window.Submission.init();
        window.Dashboard.init();
        window.Review.init();

        // Load initial default review ticket
        window.Review.loadReportForReview('INFRA-2024-0982-A');

        // Check backend connectivity
        this.checkBackendStatus();
    },

    bindNavigation() {
        const tabs = document.querySelectorAll('.nav-tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                const viewId = tab.getAttribute('data-view');
                this.navigateTo(viewId);
            });
        });

        // Tracking refresh
        const refreshBtn = document.getElementById('btnRefreshTracking');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadTrackingData());
        }
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

        // Trigger view-specific refreshes
        if (viewId === 'view-tracking') {
            this.loadTrackingData();
        } else if (viewId === 'view-dashboard') {
            window.Dashboard.loadDashboardData();
        } else if (viewId === 'view-admin') {
            this.loadAdminData();
        }
    },

    bindRoleSelector() {
        const selector = document.getElementById('roleSelector');
        const userBadge = document.getElementById('currentUserName');

        if (selector) {
            selector.addEventListener('change', (e) => {
                this.currentRole = e.target.value;
                window.Api.setRole(this.currentRole);

                if (this.currentRole === 'citizen') {
                    userBadge.textContent = 'Eugene Onyango (Citizen)';
                    this.showToast("Switched to Citizen / Reporter mode.");
                } else if (this.currentRole === 'engineer') {
                    userBadge.textContent = 'Eng. Elena (PE #8491)';
                    this.showToast("Switched to Engineer (Lead Certifier) mode.");
                } else if (this.currentRole === 'admin') {
                    userBadge.textContent = 'Admin (Infrastructure Authority)';
                    this.showToast("Switched to System Administrator mode.");
                }
            });
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

        try {
            const data = await window.Api.getMyReports();
            const reports = data.my_reports || [];

            if (reports.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: #64748b;">No defect reports submitted yet. Submit a photo from the 'Submit Defect' tab!</td></tr>`;
                return;
            }

            tbody.innerHTML = reports.map(item => {
                const rep = item.report;
                const ai = item.assessment || {};
                const sev = ai.relative_severity || 'Medium';
                const status = rep.status || 'Pending';
                const dateStr = rep.date_submitted ? new Date(rep.date_submitted).toLocaleDateString() : 'Today';

                return `
                    <tr>
                        <td><code>#${rep._id.slice(0, 16)}</code></td>
                        <td>${dateStr}</td>
                        <td>${rep.metadata?.location_name || 'Corridor Asset'}</td>
                        <td><strong>${ai.defect_class || 'Pavement Distress'}</strong></td>
                        <td><span class="severity-pill ${sev.toLowerCase()}">[ ${sev.toUpperCase()} ]</span></td>
                        <td><span class="status-badge ${status.toLowerCase()}">${status}</span></td>
                        <td>
                            <button class="btn-secondary btn-sm" onclick="window.Review.loadReportForReview('${rep._id}'); window.App.navigateTo('view-review');">
                                View Assessment
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error("Failed to load tracking data:", e);
        }
    },

    // Admin Verification View (FR-10)
    async loadAdminData() {
        const tbody = document.getElementById('adminTableBody');
        if (!tbody) return;

        try {
            const data = await window.Api.getUsers();
            const users = data.users || [];

            tbody.innerHTML = users.map(u => {
                const isVerified = u.verification_status === 'verified';
                const isEngineer = u.role === 'engineer';

                return `
                    <tr>
                        <td><code>${u.user_id || u._id}</code></td>
                        <td><strong>${u.name}</strong></td>
                        <td>${u.email}</td>
                        <td><span class="certifier-tag">${u.role.toUpperCase()}</span></td>
                        <td>
                            <span class="status-badge ${isVerified ? 'verified' : 'pending'}">
                                ${u.verification_status.toUpperCase()}
                            </span>
                        </td>
                        <td>${u.created_at ? new Date(u.created_at).toLocaleDateString() : 'N/A'}</td>
                        <td>
                            ${isEngineer && !isVerified ? `
                                <button class="btn-success btn-sm" onclick="App.handleVerifyUser('${u.user_id || u._id}', 'verified')">
                                    ✓ Approve License
                                </button>
                                <button class="btn-secondary btn-sm" onclick="App.handleVerifyUser('${u.user_id || u._id}', 'rejected')">
                                    ✕ Reject
                                </button>
                            ` : `<span style="color: #64748b; font-size: 0.8rem;">Access Active</span>`}
                        </td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error("Admin user list load error:", e);
        }
    },

    async handleVerifyUser(userId, status) {
        try {
            await window.Api.verifyUser(userId, status);
            this.showToast(`User verification updated to '${status}'.`);
            this.loadAdminData();
        } catch (e) {
            this.showToast("Failed to update user verification.", true);
        }
    },

    showToast(message, isError = false) {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = 'toast-msg';
        if (isError) {
            toast.style.borderLeftColor = '#ef4444';
        }
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3200);
    }
};

window.App = App;

// Bootstrap on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.App.init();
});
