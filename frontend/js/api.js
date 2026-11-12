/**
 * InfraVision API Client - Handles authenticated REST communication with Flask backend
 * Automatically resolves Flask API host across direct serving, Live Server (port 5500), and local origins.
 */
const getApiBase = () => {
    try {
        if (typeof window !== 'undefined') {
            const loc = window.location;
            // When opened directly via file:/// protocol
            if (loc.protocol === 'file:') {
                return 'http://127.0.0.1:5000/api';
            }
            // If running locally on separate front-end dev servers (e.g. Live Server on port 5500, 3000)
            const isLocal = loc.hostname === 'localhost' || loc.hostname === '127.0.0.1';
            if (isLocal && loc.port && loc.port !== '5000' && loc.port !== '8080') {
                return 'http://127.0.0.1:5000/api';
            }
        }
    } catch (e) {
        // Fallback to relative
    }
    return '/api';
};

const API_BASE = getApiBase();

const Api = {
    // Session token and user caching
    getToken() {
        return sessionStorage.getItem('token') || localStorage.getItem('token') || '';
    },

    setSession(token, user) {
        if (token) {
            sessionStorage.setItem('token', token);
        }
        if (user) {
            sessionStorage.setItem('user', JSON.stringify(user));
        }
    },

    getUser() {
        const userStr = sessionStorage.getItem('user');
        try {
            return userStr ? JSON.parse(userStr) : null;
        } catch {
            return null;
        }
    },

    clearSession() {
        sessionStorage.removeItem('token');
        sessionStorage.removeItem('user');
        localStorage.removeItem('token');
        localStorage.removeItem('user');
    },

    /**
     * Resolves an image URL against the backend origin if relative and running on a separate host/port.
     */
    resolveImageUrl(url) {
        if (!url || typeof url !== 'string') return '';
        if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:') || url.startsWith('blob:')) {
            return url;
        }
        let clean = url.replace(/\\/g, '/');
        if (clean.startsWith('backend/uploads/')) clean = clean.substring('backend/uploads/'.length);
        if (clean.startsWith('uploads/')) clean = clean.substring('uploads/'.length);
        if (!clean.startsWith('/api/')) {
            clean = `/api/reports/images/${clean.replace(/^\/+/, '')}`;
        }
        const apiBase = getApiBase();
        if (apiBase.startsWith('http://') || apiBase.startsWith('https://')) {
            try {
                const hostOrigin = new URL(apiBase).origin;
                return `${hostOrigin}${clean}`;
            } catch {
                return clean;
            }
        }
        return clean;
    },

    getHeaders(isFormData = false) {
        const headers = {};
        const token = this.getToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        if (!isFormData) {
            headers['Content-Type'] = 'application/json';
        }
        return headers;
    },

    /**
     * Resilient fetch wrapper providing clear diagnostics when the Flask server is not running.
     */
    async safeFetch(url, options = {}) {
        try {
            return await fetch(url, options);
        } catch (networkError) {
            console.error("[InfraVision API Connection Error]", networkError);
            throw new Error(
                "Unable to connect to backend server. Please make sure the Flask backend is started on http://127.0.0.1:5000 (run: python backend/run.py in your terminal)."
            );
        }
    },

    // Health Check
    async checkHealth() {
        const res = await this.safeFetch(`${API_BASE}/health`);
        return res.json();
    },

    // Authentication (FR-01)
    async register(userData) {
        const res = await this.safeFetch(`${API_BASE}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(userData)
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Registration failed.');
        }
        if (data.token && data.user) {
            this.setSession(data.token, data.user);
        }
        return data;
    },

    async login(email, password, otp_code = '') {
        const payload = { email, password };
        if (otp_code) payload.otp_code = otp_code;

        const res = await this.safeFetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Invalid credentials.');
        }
        if (data.token && data.user) {
            this.setSession(data.token, data.user);
        }
        return data;
    },

    async verify2FA(email, otp_code) {
        const res = await this.safeFetch(`${API_BASE}/auth/verify-2fa`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, otp_code })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || '2FA verification failed.');
        }
        if (data.token && data.user) {
            this.setSession(data.token, data.user);
        }
        return data;
    },

    async loginWithGoogle(credential) {
        const res = await this.safeFetch(`${API_BASE}/auth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ credential })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Google authentication failed.');
        }
        if (data.token && data.user) {
            this.setSession(data.token, data.user);
        }
        return data;
    },

    async resendOtp(email) {
        const res = await this.safeFetch(`${API_BASE}/auth/resend-otp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to resend code.');
        }
        return data;
    },

    async toggle2FA(enable) {
        const res = await this.safeFetch(`${API_BASE}/auth/toggle-2fa`, {
            method: 'POST',
            headers: this.getHeaders(false),
            body: JSON.stringify({ enable })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to toggle 2FA.');
        }
        return data;
    },

    async getProfile() {
        const res = await this.safeFetch(`${API_BASE}/auth/profile`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            throw new Error('Failed to load user profile.');
        }
        const data = await res.json();
        if (data.user) {
            sessionStorage.setItem('user', JSON.stringify(data.user));
        }
        return data;
    },

    async updateProfile(profileData) {
        const res = await this.safeFetch(`${API_BASE}/auth/profile`, {
            method: 'PUT',
            headers: this.getHeaders(),
            body: JSON.stringify(profileData)
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to update profile.');
        }
        if (data.user) {
            sessionStorage.setItem('user', JSON.stringify(data.user));
        }
        return data;
    },

    async changePassword(current_password, new_password) {
        const res = await this.safeFetch(`${API_BASE}/auth/change-password`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ current_password, new_password })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to change password.');
        }
        return data;
    },

    async getAuthConfig() {
        try {
            const res = await this.safeFetch(`${API_BASE}/auth/config`);
            if (res.ok) return await res.json();
        } catch (e) {
            // Ignore network errors in offline test mode
        }
        return { enable_demo_otp: false, google_client_id: '', otp_expiry_seconds: 300, otp_cooldown_seconds: 60 };
    },

    // Defect Reports (FR-02, FR-03, FR-04)
    async submitDefect(formData) {
        const res = await this.safeFetch(`${API_BASE}/reports`, {
            method: 'POST',
            headers: this.getHeaders(true),
            body: formData
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Submission failed.');
        }
        return data;
    },

    async getReports(params = {}) {
        const query = new URLSearchParams(params).toString();
        const res = await this.safeFetch(`${API_BASE}/reports${query ? '?' + query : ''}`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to fetch reports.');
        }
        return res.json();
    },

    async getPublicRecentReports(limit = 5) {
        const res = await this.safeFetch(`${API_BASE}/reports/public/recent?limit=${encodeURIComponent(limit)}`);
        if (!res.ok) {
            return { reports: [], count: 0 };
        }
        return res.json();
    },

    async getReportById(reportId) {
        const res = await this.safeFetch(`${API_BASE}/reports/${reportId}`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Report not found.');
        }
        return res.json();
    },

    async getMyReports() {
        const res = await this.safeFetch(`${API_BASE}/users/reports`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to load user reports.');
        }
        return res.json();
    },

    // Citizen Report Feedback Notifications (Section 11)
    async getNotifications() {
        const res = await this.safeFetch(`${API_BASE}/users/notifications`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            return { notifications: [], unread_count: 0 };
        }
        return res.json();
    },

    async markNotificationRead(notificationId) {
        const res = await this.safeFetch(`${API_BASE}/users/notifications/${notificationId}/read`, {
            method: 'PATCH',
            headers: this.getHeaders()
        });
        return res.json();
    },

    async markAllNotificationsRead() {
        const res = await this.safeFetch(`${API_BASE}/users/notifications/mark-all-read`, {
            method: 'POST',
            headers: this.getHeaders()
        });
        return res.json();
    },

    // Engineer Analytics & Trends (FR-07, FR-09)
    async getSummary() {
        const res = await this.safeFetch(`${API_BASE}/analytics/summary`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to load analytics summary.');
        }
        return res.json();
    },

    async getDegradationTrends(params = {}) {
        const qry = new URLSearchParams(params).toString();
        const url = qry ? `${API_BASE}/analytics/trends?${qry}` : `${API_BASE}/analytics/trends`;
        const res = await this.safeFetch(url, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to load trend analytics.');
        }
        return res.json();
    },

    getHistoricalDefectTrends(params = {}) {
        return this.getDegradationTrends(params);
    },

    async getCriticalCalendar(params = {}) {
        const qry = new URLSearchParams(params).toString();
        const url = qry ? `${API_BASE}/analytics/critical-calendar?${qry}` : `${API_BASE}/analytics/critical-calendar`;
        const res = await this.safeFetch(url, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to load critical calendar.');
        }
        return res.json();
    },

    async getMonitoringIntelligence(params = {}) {
        const qry = new URLSearchParams(params).toString();
        const url = qry ? `${API_BASE}/analytics/intelligence?${qry}` : `${API_BASE}/analytics/intelligence`;
        const res = await this.safeFetch(url, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || 'Failed to load monitoring intelligence.');
        }
        return res.json();
    },

    async getGeographyHierarchy(county = null, constituency = null) {
        let qry = '';
        if (county && county.toLowerCase() !== 'all') {
            qry = `?county=${encodeURIComponent(county)}`;
            if (constituency && constituency.toLowerCase() !== 'all') {
                qry += `&constituency=${encodeURIComponent(constituency)}`;
            }
        }
        const res = await this.safeFetch(`${API_BASE}/analytics/geography/hierarchy${qry}`, {
            headers: this.getHeaders()
        });
        if (!res.ok) return { counties: [], constituencies: [], wards: [] };
        return await res.json();
    },

    async getAvailableEngineers(reportId = null) {
        const url = reportId ? `${API_BASE}/reviews/engineers/available?report_id=${encodeURIComponent(reportId)}` : `${API_BASE}/reviews/engineers/available`;
        const res = await this.safeFetch(url, { headers: this.getHeaders() });
        if (!res.ok) return { engineers: [] };
        return await res.json();
    },

    async addCollaborator(reportId, engineerId, role, inviteNote = '') {
        const res = await this.safeFetch(`${API_BASE}/reviews/report/${reportId}/collaborators`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ engineer_id: engineerId, role, invite_note: inviteNote })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to add collaborator.');
        return data;
    },

    async respondToCollaboratorInvite(reportId, response) {
        const res = await this.safeFetch(`${API_BASE}/reviews/report/${reportId}/collaborators/respond`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ response })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to update invitation status.');
        return data;
    },

    async removeCollaborator(reportId, engineerId) {
        const res = await this.safeFetch(`${API_BASE}/reviews/report/${reportId}/collaborators/${engineerId}`, {
            method: 'DELETE',
            headers: this.getHeaders()
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to remove collaborator.');
        return data;
    },

    async transferLeadEngineer(reportId, newLeadId, reason) {
        const res = await this.safeFetch(`${API_BASE}/reviews/report/${reportId}/transfer-lead`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ new_lead_engineer_id: newLeadId, transfer_reason: reason })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to transfer lead engineer.');
        return data;
    },

    // Engineer Defect Review & Assessment Validation (FR-06)
    async submitReview(assessmentId, reviewData) {
        const res = await this.safeFetch(`${API_BASE}/reviews/${assessmentId}`, {
            method: 'POST',
            headers: this.getHeaders(false),
            body: JSON.stringify(reviewData)
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Validation submission failed.');
        }
        return data;
    },

    async getReview(assessmentId) {
        const res = await this.safeFetch(`${API_BASE}/reviews/${assessmentId}`, {
            headers: this.getHeaders()
        });
        return res.json();
    },

    async getAdminStats() {
        const res = await this.safeFetch(`${API_BASE}/admin/stats`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to fetch admin stats.');
        }
        return res.json();
    },

    async getAdminDashboard() {
        const res = await this.safeFetch(`${API_BASE}/admin/dashboard`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to fetch admin dashboard.');
        }
        return res.json();
    },

    // OTP Resend & Google Sign-In
    async resendOtp(email) {
        const res = await this.safeFetch(`${API_BASE}/auth/resend-otp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to resend OTP.');
        }
        return data;
    },

    async changePassword(old_password, new_password) {
        const res = await this.safeFetch(`${API_BASE}/auth/change-password`, {
            method: 'POST',
            headers: this.getHeaders(false),
            body: JSON.stringify({ old_password, new_password })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to change password.');
        }
        return data;
    },

    // Interactive Map Data & Config
    async getMapConfig() {
        const res = await this.safeFetch(`${API_BASE}/reports/map/config`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            return {
                api_key: '',
                has_api_key: false,
                default_center: { lat: -1.286389, lng: 36.817223 },
                default_zoom: 12
            };
        }
        return res.json();
    },

    async getMapPoints(params = {}) {
        const query = new URLSearchParams(params).toString();
        const res = await this.safeFetch(`${API_BASE}/reports/map${query ? '?' + query : ''}`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to fetch map data.');
        }
        return res.json();
    },

    // Report Lifecycle & Engineer Casework
    async updateReportStatus(reportId, targetStatus, reason = '') {
        const res = await this.safeFetch(`${API_BASE}/reports/${reportId}/status`, {
            method: 'PUT',
            headers: this.getHeaders(false),
            body: JSON.stringify({ status: targetStatus, reason })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to update report lifecycle status.');
        }
        return data;
    },

    async reviewReportDirect(reportId, reviewData) {
        const res = await this.safeFetch(`${API_BASE}/reviews/report/${reportId}`, {
            method: 'POST',
            headers: this.getHeaders(false),
            body: JSON.stringify(reviewData)
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Direct report review failed.');
        }
        return data;
    },

    // Admin User Verification & Governance (FR-10, Sections I, J, K, L)
    async getUsers(roleOrParams = '', status = '') {
        const params = (roleOrParams && typeof roleOrParams === 'object')
            ? { ...roleOrParams }
            : {};
        if (typeof roleOrParams === 'string' && roleOrParams.trim()) {
            params.role = roleOrParams.trim();
        }
        if (typeof status === 'string' && status.trim()) {
            params.verification_status = status.trim();
        }
        const query = new URLSearchParams(params).toString();
        const res = await this.safeFetch(`${API_BASE}/admin/users${query ? '?' + query : ''}`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to fetch users list.');
        }
        return res.json();
    },

    async verifyUser(userId, status, rejectionReason = '', rejectionNotes = '') {
        const payload = { status };
        if (status === 'rejected') {
            payload.rejection_reason = rejectionReason;
            payload.rejection_notes = rejectionNotes;
        }
        const res = await this.safeFetch(`${API_BASE}/admin/users/${userId}/verify`, {
            method: 'PUT',
            headers: this.getHeaders(false),
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to update user verification status.');
        }
        return data;
    },

    // Admin Operational Notices (Section T)
    async sendAdminNotice(noticeData) {
        const res = await this.safeFetch(`${API_BASE}/admin/notifications/send`, {
            method: 'POST',
            headers: this.getHeaders(false),
            body: JSON.stringify(noticeData)
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to dispatch administrative notice.');
        }
        return data;
    },

    // Engineer Safety Advisories (Section S)
    async issueSafetyAdvisory(reportId, category, note = '') {
        const res = await this.safeFetch(`${API_BASE}/reviews/${reportId}/safety-advisory`, {
            method: 'POST',
            headers: this.getHeaders(false),
            body: JSON.stringify({ category, note })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to issue safety advisory.');
        }
        return data;
    },

    // Operational Role-based Notifications (FR-11, Sections O, P, Q, R, U)
    async getNotifications() {
        const res = await this.safeFetch(`${API_BASE}/users/notifications`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            return { notifications: [], unread_count: 0 };
        }
        return res.json();
    },

    async markNotificationRead(notificationId) {
        const res = await this.safeFetch(`${API_BASE}/users/notifications/${notificationId}/read`, {
            method: 'POST',
            headers: this.getHeaders(false)
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to mark notification as read.');
        }
        return data;
    },

    async markAllNotificationsRead() {
        const res = await this.safeFetch(`${API_BASE}/users/notifications/mark-all-read`, {
            method: 'POST',
            headers: this.getHeaders(false)
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to mark all notifications as read.');
        }
        return data;
    },

    // Inspection Notebook & Compliance (Sections 30-33, 43)
    async updateInspectionNotebook(reportId, notebookData) {
        const res = await this.safeFetch(`${API_BASE}/reviews/report/${reportId}/inspection-notebook`, {
            method: 'POST',
            headers: this.getHeaders(false),
            body: JSON.stringify(notebookData)
        });
        const data = await res.json();
        if (!res.ok) {
            const err = new Error(data.error || 'Failed to save inspection notebook.');
            err.status = res.status;
            err.conflict = (res.status === 409);
            throw err;
        }
        return data;
    }
};

window.Api = Api;
