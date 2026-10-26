/**
 * Dashboard Module - Engineer Monitoring Dashboard (Figure 4.7)
 * Apple-Inspired Light Mode Visualizations
 */
const Dashboard = {
    init() {
        this.bindEvents();
    },

    bindEvents() {
        const filterSelect = document.getElementById('filterSeveritySelect');
        if (filterSelect) {
            filterSelect.addEventListener('change', () => this.loadReportsList());
        }
    },

    async loadDashboardData() {
        await Promise.all([
            this.loadKpis(),
            this.loadDegradationChart(),
            this.loadReportsList()
        ]);
    },

    async loadKpis() {
        try {
            const summary = await window.Api.getSummary();
            const queueEl = document.getElementById('kpiActiveQueue');
            const verifiedEl = document.getElementById('kpiVerifiedCount');
            const modelEl = document.getElementById('kpiModelVersion');
            const critEl = document.getElementById('kpiCriticalHazards');

            if (queueEl) queueEl.textContent = summary.active_defect_queue ?? 0;
            if (verifiedEl) verifiedEl.textContent = summary.verified_inspections ?? 0;
            if (modelEl) modelEl.textContent = summary.model_version || 'SSD-MobileNetV2';
            if (critEl) critEl.textContent = summary.severity_breakdown?.Critical ?? 0;
        } catch (e) {
            console.error("KPI load error:", e);
        }
    },

    async loadDegradationChart() {
        try {
            const data = await window.Api.getDegradationTrends();
            this.drawDegradationChart(data.trend_data, data.action_threshold);
        } catch (e) {
            console.error("Trend load error:", e);
        }
    },

    drawDegradationChart(trendData, threshold = 68) {
        const canvas = document.getElementById('degradationChart');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        const width = canvas.parentElement.clientWidth || 540;
        const height = canvas.parentElement.clientHeight || 260;
        canvas.width = width * 2;
        canvas.height = height * 2;
        ctx.scale(2, 2);

        const padL = 40;
        const padR = 25;
        const padT = 30;
        const padB = 40;
        const chartW = width - padL - padR;
        const chartH = height - padT - padB;

        ctx.clearRect(0, 0, width, height);

        // Grid lines (0 to 100)
        ctx.font = '11px "Montserrat", sans-serif';
        ctx.fillStyle = '#86868b';
        ctx.strokeStyle = '#e5e5ea';
        ctx.lineWidth = 1;

        const yLevels = [0, 20, 40, 60, 80, 100];
        yLevels.forEach(lvl => {
            const y = padT + chartH - (lvl / 100) * chartH;
            ctx.beginPath();
            ctx.moveTo(padL, y);
            ctx.lineTo(width - padR, y);
            ctx.stroke();
            ctx.fillText(lvl.toString(), 15, y + 4);
        });

        // Threshold line (Action Threshold at 68)
        const threshY = padT + chartH - (threshold / 100) * chartH;
        ctx.strokeStyle = '#dc2626';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(padL, threshY);
        ctx.lineTo(width - padR, threshY);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = '#b91c1c';
        ctx.fillText(`[ Review Threshold: ${threshold} ]`, width - padR - 165, threshY - 6);

        if (!trendData || trendData.length === 0) return;

        const stepX = chartW / (trendData.length - 1);
        const points = trendData.map((d, idx) => ({
            x: padL + idx * stepX,
            y: padT + chartH - (d.condition_score / 100) * chartH,
            score: d.condition_score,
            period: d.period
        }));

        // Connecting trend line
        ctx.strokeStyle = '#0071e3';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i].x, points[i].y);
        }
        ctx.stroke();

        // Points
        points.forEach(pt => {
            ctx.fillStyle = '#ffffff';
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, 6, 0, 2 * Math.PI);
            ctx.fill();

            ctx.strokeStyle = '#0071e3';
            ctx.lineWidth = 2.5;
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, 6, 0, 2 * Math.PI);
            ctx.stroke();

            ctx.fillStyle = '#1d1d1f';
            ctx.font = 'bold 11px "Montserrat", sans-serif';
            ctx.fillText(pt.score.toString(), pt.x - 7, pt.y - 10);

            ctx.fillStyle = '#86868b';
            ctx.font = '11px "Montserrat", sans-serif';
            ctx.fillText(pt.period, pt.x - 10, height - padB + 18);
        });
    },

    async loadReportsList() {
        const queueContainer = document.getElementById('defectQueueList');
        if (!queueContainer) return;

        const filterVal = document.getElementById('filterSeveritySelect')?.value || '';

        try {
            const params = { exclude_status: 'Resolved' };
            if (filterVal && filterVal !== 'Flagged') {
                params.severity = filterVal;
            }

            const data = await window.Api.getReports(params);
            let reports = data.reports || [];

            // Exclude resolved reports from active priority queue
            reports = reports.filter(r => (r.status || '').toLowerCase() !== 'resolved');

            if (filterVal === 'Flagged') {
                reports = reports.filter(r => r.validation_status === 'unusual' || r.requires_engineer_review === true || r.metadata?.is_unusual === true);
            }

            if (reports.length === 0) {
                queueContainer.innerHTML = `<div class="canvas-placeholder"><p>No infrastructure defect reports matching selected filter.</p></div>`;
                return;
            }

            queueContainer.innerHTML = reports.map(r => {
                const assessment = r.assessment || {};
                const severity = assessment.relative_severity || r.metadata?.relative_severity || 'Low';
                const defectClass = assessment.defect_class || 'Surface Defect';
                const location = r.asset?.location || r.metadata?.location_name || 'Infrastructure Corridor';
                const assetType = r.asset?.asset_type || r.metadata?.asset_type || 'Civil Asset';
                const frameId = (r.report_id || r._id).slice(0, 18);
                const status = r.status || 'Received';
                const statusSlug = status.toLowerCase().replace(' ', '-');
                const isVerified = status === 'Verified' || status === 'Resolved';
                const isFlagged = r.validation_status === 'unusual' || r.requires_engineer_review === true || r.metadata?.is_unusual === true;

                return `
                    <div class="queue-item-card ${isFlagged ? 'is-flagged' : ''}" data-report-id="${r.report_id || r._id}">
                        <div class="queue-item-info">
                            <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                                <span class="queue-item-title">${location}</span>
                                <span class="status-chip ${statusSlug}">${status}</span>
                                ${isFlagged ? `<span class="badge-tag flagged">⚠️ Unusual Pairing</span>` : ''}
                            </div>
                            <span class="queue-item-meta">${assetType} • ${defectClass} • [ ${frameId} ]</span>
                            ${isFlagged && r.metadata?.advisory_notes ? `<span style="font-size: 0.72rem; color: #b45309;">${r.metadata.advisory_notes}</span>` : ''}
                        </div>
                        <div class="queue-item-actions">
                            <span class="severity-pill ${severity.toLowerCase()}">${severity.toUpperCase()}</span>
                            <button type="button" class="btn-review-item btn-open-review" data-report-id="${r.report_id || r._id}">
                                Review & Sign Off
                            </button>
                        </div>
                    </div>
                `;
            }).join('');

            queueContainer.querySelectorAll('.btn-open-review').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const rId = e.currentTarget.getAttribute('data-report-id');
                    window.Review.targetReportId = rId;
                    window.App.navigateTo('view-review', { reportId: rId });
                });
            });
        } catch (e) {
            console.error("Queue load error:", e);
        }
    }
};

window.Dashboard = Dashboard;
