/**
 * InfraVision API Client - Handles authenticated REST communication with Flask backend
 * Automatically resolves Flask API host across direct serving, Live Server (port 5500), and local origins.
 */
const getApiBase = () => {
    try {
        if (typeof window !== 'undefined') {
            // When opened directly via file:/// protocol or via Live Server / alternative dev ports
            if (window.location.protocol === 'file:' || (window.location.port && window.location.port !== '5000')) {
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
        if (url.startsWith('/api')) {
            const apiBase = getApiBase();
            if (apiBase.startsWith('http://') || apiBase.startsWith('https://')) {
                try {
                    const hostOrigin = new URL(apiBase).origin;
                    return `${hostOrigin}${url}`;
                } catch {
                    return url;
                }
            }
        }
        return url;
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
        return { enable_demo_otp: true, google_client_id: '', otp_expiry_seconds: 300, otp_cooldown_seconds: 60 };
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

    async getDegradationTrends() {
        const res = await this.safeFetch(`${API_BASE}/analytics/trends`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to load trend analytics.');
        }
        return res.json();
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

    // Administrator Governance (FR-10)
    async getUsers(role = '', status = '') {
        const params = {};
        if (role) params.role = role;
        if (status) params.verification_status = status;
        const query = new URLSearchParams(params).toString();
        const res = await this.safeFetch(`${API_BASE}/admin/users${query ? '?' + query : ''}`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Admin access denied.');
        }
        return res.json();
    },

    async verifyUser(userId, status) {
        const res = await this.safeFetch(`${API_BASE}/admin/users/${userId}/verify`, {
            method: 'PUT',
            headers: this.getHeaders(false),
            body: JSON.stringify({ status })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to update user verification.');
        }
        return data;
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

    async loginWithGoogle(credential) {
        const res = await this.safeFetch(`${API_BASE}/auth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ credential })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Google sign-in failed.');
        }
        if (data.token && data.user) {
            this.setSession(data.token, data.user);
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
    }
};

window.Api = Api;
