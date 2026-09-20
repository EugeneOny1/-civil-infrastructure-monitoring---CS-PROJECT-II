/**
 * Dashboard Module - Engineer Monitoring Dashboard (Figure 4.7)
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

        const padL = 45;
        const padR = 25;
        const padT = 30;
        const padB = 40;
        const chartW = width - padL - padR;
        const chartH = height - padT - padB;

        ctx.clearRect(0, 0, width, height);

        // Grid lines (0 to 100)
        ctx.font = '11px "JetBrains Mono", monospace';
        ctx.fillStyle = '#64748b';
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
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
        ctx.strokeStyle = '#ef4444';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(padL, threshY);
        ctx.lineTo(width - padR, threshY);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = '#fca5a5';
        ctx.fillText(`[ Review Threshold: ${threshold} ]`, width - padR - 180, threshY - 6);

        if (!trendData || trendData.length === 0) return;

        const stepX = chartW / (trendData.length - 1);
        const points = trendData.map((d, i) => {
            const score = d.condition_score ?? d.score ?? 70;
            const x = padL + i * stepX;
            const y = padT + chartH - (score / 100) * chartH;
            return { x, y, score, period: d.period || d.month };
        });

        // Gradient under curve
        const grad = ctx.createLinearGradient(0, padT, 0, height - padB);
        grad.addColorStop(0, 'rgba(59, 130, 246, 0.35)');
        grad.addColorStop(1, 'rgba(59, 130, 246, 0.0)');

        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i].x, points[i].y);
        }
        ctx.lineTo(points[points.length - 1].x, height - padB);
        ctx.lineTo(points[0].x, height - padB);
        ctx.closePath();
        ctx.fillStyle = grad;
        ctx.fill();

        // Trend line
        ctx.strokeStyle = '#3b82f6';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i].x, points[i].y);
        }
        ctx.stroke();

        // Points
        points.forEach(pt => {
            ctx.fillStyle = '#1e293b';
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, 6, 0, 2 * Math.PI);
            ctx.fill();

            ctx.strokeStyle = '#60a5fa';
            ctx.lineWidth = 2.5;
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, 6, 0, 2 * Math.PI);
            ctx.stroke();

            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 11px "JetBrains Mono", monospace';
            ctx.fillText(pt.score.toString(), pt.x - 7, pt.y - 10);

            ctx.fillStyle = '#94a3b8';
            ctx.font = '11px "JetBrains Mono", monospace';
            ctx.fillText(pt.period, pt.x - 10, height - padB + 18);
        });
    },

    async loadReportsList() {
        const queueContainer = document.getElementById('defectQueueList');
        if (!queueContainer) return;

        const severityFilter = document.getElementById('filterSeveritySelect')?.value;

        try {
            const data = await window.Api.getReports({ severity: severityFilter });
            const reports = data.reports || [];

            if (reports.length === 0) {
                queueContainer.innerHTML = `<div class="canvas-placeholder"><p>No infrastructure defect reports matching filter.</p></div>`;
                return;
            }

            queueContainer.innerHTML = reports.map(r => {
                const assessment = r.assessment || {};
                const severity = assessment.relative_severity || 'Low';
                const defectClass = assessment.defect_class || 'Surface Defect';
                const location = r.asset?.location || r.metadata?.location_name || 'Infrastructure Corridor';
                const frameId = (r.report_id || r._id).slice(0, 18);
                const isVerified = r.status === 'Verified';

                return `
                    <div class="queue-item" data-report-id="${r.report_id || r._id}">
                        <div class="queue-item-info">
                            <div class="queue-item-header">
                                <span class="queue-frame-id">[ ${frameId} ]</span>
                                <span class="queue-location">${location}</span>
                            </div>
                            <span class="queue-defect-desc">${defectClass} • ${r.description || 'Structural distress recorded'}</span>
                        </div>
                        <div class="queue-action">
                            <span class="severity-pill ${severity.toLowerCase()}">[ ${severity.toUpperCase()} ]</span>
                            <span class="status-badge ${r.status ? r.status.toLowerCase() : 'pending'}">${r.status || 'Pending'}</span>
                            <button type="button" class="btn-secondary btn-sm btn-open-review" data-report-id="${r.report_id || r._id}">
                                ${isVerified ? 'View Review' : 'Inspect & Validate'}
                            </button>
                        </div>
                    </div>
                `;
            }).join('');

            queueContainer.querySelectorAll('.btn-open-review').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const rId = e.currentTarget.getAttribute('data-report-id');
                    window.Review.loadReportForReview(rId);
                    window.App.navigateTo('view-review');
                });
            });
        } catch (e) {
            console.error("Queue load error:", e);
        }
    }
};

window.Dashboard = Dashboard;
