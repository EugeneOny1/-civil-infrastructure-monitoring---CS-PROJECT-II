/**
 * InfraVision API Client - Handles authenticated REST communication with Flask backend
 */
const API_BASE = '/api';

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

    // Health Check
    async checkHealth() {
        const res = await fetch(`${API_BASE}/health`);
        return res.json();
    },

    // Authentication (FR-01)
    async register(userData) {
        const res = await fetch(`${API_BASE}/auth/register`, {
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

    async login(email, password) {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
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

    async getProfile() {
        const res = await fetch(`${API_BASE}/auth/me`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            throw new Error('Unauthorized');
        }
        const data = await res.json();
        if (data.user) {
            sessionStorage.setItem('user', JSON.stringify(data.user));
        }
        return data.user;
    },

    // Defect Reports (FR-02, FR-03, FR-04)
    async submitDefect(formData) {
        const res = await fetch(`${API_BASE}/reports`, {
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
        const res = await fetch(`${API_BASE}/reports${query ? '?' + query : ''}`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to fetch reports.');
        }
        return res.json();
    },

    async getReportById(reportId) {
        const res = await fetch(`${API_BASE}/reports/${reportId}`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Report not found.');
        }
        return res.json();
    },

    async getMyReports() {
        const res = await fetch(`${API_BASE}/users/reports`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to load user reports.');
        }
        return res.json();
    },

    // Engineer Analytics & Trends (FR-07, FR-09)
    async getSummary() {
        const res = await fetch(`${API_BASE}/analytics/summary`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to load analytics summary.');
        }
        return res.json();
    },

    async getDegradationTrends() {
        const res = await fetch(`${API_BASE}/analytics/trends`, {
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
        const res = await fetch(`${API_BASE}/reviews/${assessmentId}`, {
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
        const res = await fetch(`${API_BASE}/reviews/${assessmentId}`, {
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
        const res = await fetch(`${API_BASE}/admin/users${query ? '?' + query : ''}`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Admin access denied.');
        }
        return res.json();
    },

    async verifyUser(userId, status) {
        const res = await fetch(`${API_BASE}/admin/users/${userId}/verify`, {
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
        const res = await fetch(`${API_BASE}/admin/stats`, {
            headers: this.getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to fetch admin stats.');
        }
        return res.json();
    }
};

window.Api = Api;
