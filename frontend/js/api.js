/**
 * InfraVision API Client - Handles all REST communication with Flask backend
 */
const API_BASE = '/api';

const Api = {
    // Current role header state
    currentUser: {
        id: 'usr_eng_01',
        role: 'engineer',
        name: 'Eng. Elena (PE #8491)'
    },

    setRole(role) {
        if (role === 'citizen') {
            this.currentUser = {
                id: 'usr_cit_01',
                role: 'citizen',
                name: 'Eugene Onyango (Citizen)'
            };
        } else if (role === 'engineer') {
            this.currentUser = {
                id: 'usr_eng_01',
                role: 'engineer',
                name: 'Eng. Elena (PE #8491)'
            };
        } else if (role === 'admin') {
            this.currentUser = {
                id: 'usr_admin_01',
                role: 'admin',
                name: 'Infrastructure Admin'
            };
        }
    },

    getHeaders(isFormData = false) {
        const headers = {
            'X-User-Id': this.currentUser.id
        };
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

    // Reports & Defect Analysis (FR-02, FR-03, FR-04)
    async submitDefect(formData) {
        const res = await fetch(`${API_BASE}/reports`, {
            method: 'POST',
            headers: this.getHeaders(true),
            body: formData
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Submission failed.');
        }
        return res.json();
    },

    async getReports(params = {}) {
        const query = new URLSearchParams(params).toString();
        const res = await fetch(`${API_BASE}/reports${query ? '?' + query : ''}`, {
            headers: this.getHeaders()
        });
        return res.json();
    },

    async getReportById(reportId) {
        const res = await fetch(`${API_BASE}/reports/${reportId}`, {
            headers: this.getHeaders()
        });
        return res.json();
    },

    async getMyReports() {
        const res = await fetch(`${API_BASE}/reports/my`, {
            headers: this.getHeaders()
        });
        return res.json();
    },

    // Analytics & Trends (FR-07, FR-09)
    async getSummary() {
        const res = await fetch(`${API_BASE}/analytics/summary`, {
            headers: this.getHeaders()
        });
        return res.json();
    },

    async getDegradationTrends() {
        const res = await fetch(`${API_BASE}/analytics/trends`, {
            headers: this.getHeaders()
        });
        return res.json();
    },

    // Professional Review Sign-Off (FR-06)
    async submitReview(assessmentId, reviewData) {
        const res = await fetch(`${API_BASE}/reviews/${assessmentId}`, {
            method: 'POST',
            headers: this.getHeaders(false),
            body: JSON.stringify(reviewData)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Sign-off failed.');
        }
        return res.json();
    },

    // Administration & Governance (FR-10)
    async getUsers(role = '') {
        const query = role ? `?role=${role}` : '';
        const res = await fetch(`${API_BASE}/admin/users${query}`, {
            headers: this.getHeaders()
        });
        return res.json();
    },

    async verifyUser(userId, status) {
        const res = await fetch(`${API_BASE}/admin/users/${userId}/verify`, {
            method: 'PUT',
            headers: this.getHeaders(false),
            body: JSON.stringify({ status })
        });
        return res.json();
    }
};

window.Api = Api;
