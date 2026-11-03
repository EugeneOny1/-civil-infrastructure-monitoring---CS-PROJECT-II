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

        const kpiVerified = document.getElementById('kpiCardVerified');
        const kpiVerifiedCount = document.getElementById('kpiVerifiedCount');
        const triggerVerifiedFilter = () => {
            const select = document.getElementById('filterSeveritySelect');
            if (select) {
                select.value = 'Verified';
                this.loadReportsList();
                const queueCard = document.querySelector('.queue-card');
                if (queueCard && typeof queueCard.scrollIntoView === 'function') {
                    queueCard.scrollIntoView({ behavior: 'smooth' });
                }
            }
        };

        if (kpiVerified) kpiVerified.addEventListener('click', triggerVerifiedFilter);
        if (kpiVerifiedCount) kpiVerifiedCount.addEventListener('click', (e) => {
            e.stopPropagation();
            triggerVerifiedFilter();
        });
        const rangeSelect = document.getElementById('trendRangeSelect');
        const viewBySelect = document.getElementById('trendViewBySelect');
        const countySelect = document.getElementById('trendCountySelect');
        const wardSelect = document.getElementById('trendWardSelect');

        [rangeSelect, viewBySelect, countySelect, wardSelect].forEach(el => {
            if (el) el.addEventListener('change', () => this.loadDegradationChart());
        });
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
        const range = document.getElementById('trendRangeSelect')?.value || '6m';
        const viewBy = document.getElementById('trendViewBySelect')?.value || 'defect_class';
        const county = document.getElementById('trendCountySelect')?.value || 'all';
        const ward = document.getElementById('trendWardSelect')?.value || 'all';

        try {
            const data = await window.Api.getDegradationTrends({
                range: range,
                view_by: viewBy,
                county: county,
                ward: ward
            });
            this.drawHistoricalDefectChart(data);
        } catch (e) {
            console.error("Historical Defect Trend load error:", e);
        }
    },

    drawHistoricalDefectChart(apiData) {
        const canvas = document.getElementById('degradationChart');
        const emptyState = document.getElementById('trendEmptyState');
        const legendContainer = document.getElementById('trendLegend');
        if (!canvas) return;

        const trendData = apiData?.trend_data || [];
        const series = apiData?.series || ['Crack', 'Pothole', 'Surface deterioration'];
        const viewBy = apiData?.view_by || 'defect_class';
        const hasData = Boolean(apiData?.has_sufficient_data && trendData.length > 0 && trendData.some(d => (d.total || 0) > 0));

        // Update secondary summary strip
        const summary = apiData?.summary || {};
        const repEl = document.getElementById('trendSummaryMostReported');
        const critEl = document.getElementById('trendSummaryCritical');
        const resEl = document.getElementById('trendSummaryResolved');
        const locEl = document.getElementById('trendSummaryActiveLocation');

        if (repEl) repEl.textContent = summary.most_reported_defect || 'None';
        if (critEl) critEl.textContent = summary.critical_reports_count ?? 0;
        if (resEl) resEl.textContent = summary.resolved_reports_count ?? 0;
        if (locEl) locEl.textContent = summary.most_active_location || 'Corridors';

        // Update mode subtitle
        const subEl = document.getElementById('trendSubtitle');
        if (subEl) {
            subEl.textContent = viewBy === 'visual_severity'
                ? "Observations Over Time — By Visual Severity"
                : "Observations Over Time — By Defect Class";
        }

        // Color palettes
        const COLORS = {
            'Crack': '#f59e0b',
            'Pothole': '#ef4444',
            'Surface deterioration': '#0284c7',
            'Critical': '#ef4444',
            'Medium': '#f59e0b',
            'Low': '#10b981'
        };

        // Render dynamic legend
        if (legendContainer) {
            legendContainer.innerHTML = series.map(k => `
                <div class="legend-item" style="display:flex; align-items:center; gap:6px; font-size:0.78rem; color:#cbd5e1;">
                    <span style="display:inline-block; width:12px; height:12px; border-radius:3px; background:${COLORS[k] || '#94a3b8'};"></span>
                    <span>${k}</span>
                </div>
            `).join('');
        }

        // Handle empty data
        if (!hasData) {
            if (emptyState) emptyState.classList.remove('hidden');
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            return;
        } else {
            if (emptyState) emptyState.classList.add('hidden');
        }

        const ctx = canvas.getContext('2d');
        const width = canvas.parentElement.clientWidth || 540;
        const height = canvas.parentElement.clientHeight || 260;
        canvas.width = width * 2;
        canvas.height = height * 2;
        ctx.scale(2, 2);

        const padL = 36;
        const padR = 20;
        const padT = 24;
        const padB = 40;
        const chartW = width - padL - padR;
        const chartH = height - padT - padB;

        ctx.clearRect(0, 0, width, height);

        // Find max count for Y-axis scale
        let maxVal = 1;
        trendData.forEach(d => {
            series.forEach(s => {
                if ((d[s] || 0) > maxVal) maxVal = d[s];
            });
            if ((d.total || 0) > maxVal) maxVal = d.total;
        });

        // Round maxVal up to nice integer step (e.g. 5, 10, 20)
        let yMax = Math.max(5, Math.ceil(maxVal * 1.25));
        if (yMax % 5 !== 0) yMax += (5 - (yMax % 5));

        // Draw horizontal grid lines
        ctx.font = '10px "Inter", sans-serif';
        ctx.fillStyle = '#64748b';
        ctx.strokeStyle = '#334155';
        ctx.lineWidth = 1;

        const ySteps = 4;
        for (let i = 0; i <= ySteps; i++) {
            const val = Math.round((yMax / ySteps) * i);
            const y = padT + chartH - (i / ySteps) * chartH;
            ctx.beginPath();
            ctx.moveTo(padL, y);
            ctx.lineTo(width - padR, y);
            ctx.stroke();
            ctx.fillText(val.toString(), 10, y + 3);
        }

        const numPeriods = trendData.length;
        const stepX = numPeriods > 1 ? chartW / (numPeriods - 1) : chartW / 2;

        // Store plotted points for hover interactivity
        const plottedPoints = [];

        // Plot each series line
        series.forEach(sName => {
            const color = COLORS[sName] || '#94a3b8';
            const sPoints = trendData.map((d, idx) => {
                const count = d[sName] || 0;
                const x = numPeriods > 1 ? padL + idx * stepX : padL + chartW / 2;
                const y = padT + chartH - (count / yMax) * chartH;
                return { x, y, count, period: d.period, series: sName };
            });

            // Draw line
            ctx.strokeStyle = color;
            ctx.lineWidth = 2.5;
            ctx.lineJoin = 'round';
            ctx.beginPath();
            ctx.moveTo(sPoints[0].x, sPoints[0].y);
            for (let i = 1; i < sPoints.length; i++) {
                ctx.lineTo(sPoints[i].x, sPoints[i].y);
            }
            ctx.stroke();

            // Draw points
            sPoints.forEach(pt => {
                plottedPoints.push(pt);

                ctx.fillStyle = '#0f172a';
                ctx.beginPath();
                ctx.arc(pt.x, pt.y, 4.5, 0, 2 * Math.PI);
                ctx.fill();

                ctx.strokeStyle = color;
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(pt.x, pt.y, 4.5, 0, 2 * Math.PI);
                ctx.stroke();
            });
        });

        // X-axis period labels
        ctx.fillStyle = '#94a3b8';
        ctx.font = '10px "Inter", sans-serif';
        ctx.textAlign = 'center';

        trendData.forEach((d, idx) => {
            const x = numPeriods > 1 ? padL + idx * stepX : padL + chartW / 2;
            const shortLabel = d.period.length > 10 ? d.period.slice(0, 8) + '..' : d.period;
            ctx.fillText(shortLabel, x, height - padB + 16);
        });

        // Interactive mouse hover tooltip binding
        if (!canvas._hoverBound) {
            canvas._hoverBound = true;
            canvas.style.cursor = 'crosshair';

            canvas.addEventListener('mousemove', (e) => {
                const rect = canvas.getBoundingClientRect();
                const mouseX = e.clientX - rect.left;
                const mouseY = e.clientY - rect.top;

                // Find nearest period column
                let closestIdx = 0;
                let minDist = Infinity;
                trendData.forEach((d, idx) => {
                    const x = numPeriods > 1 ? padL + idx * stepX : padL + chartW / 2;
                    const dist = Math.abs(mouseX - x);
                    if (dist < minDist) {
                        minDist = dist;
                        closestIdx = idx;
                    }
                });

                if (minDist < 30) {
                    const d = trendData[closestIdx];
                    let tipText = `${d.period}\n`;
                    series.forEach(s => {
                        tipText += `${s}: ${d[s] || 0}\n`;
                    });
                    tipText += `Total: ${d.total || 0}`;
                    canvas.title = tipText;
                } else {
                    canvas.title = '';
                }
            });
        }
    },

    drawDegradationChart(trendData, threshold = 68) {
        // Backwards compatibility alias
        this.loadDegradationChart();
    },

    async loadReportsList() {
        const queueContainer = document.getElementById('defectQueueList');
        if (!queueContainer) return;

        const filterVal = document.getElementById('filterSeveritySelect')?.value || '';

        try {
            const params = {};
            if (filterVal === 'Verified') {
                params.status = 'Verified';
            } else {
                params.exclude_status = 'Resolved';
                if (filterVal && filterVal !== 'Flagged') {
                    params.severity = filterVal;
                }
            }

            const data = await window.Api.getReports(params);
            let reports = data.reports || [];

            if (filterVal === 'Verified') {
                reports = reports.filter(r => (r.status || '') === 'Verified');
            } else {
                // Exclude resolved reports from active priority queue
                reports = reports.filter(r => (r.status || '').toLowerCase() !== 'resolved');
            }

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
                                ${isFlagged ? `<span class="badge-tag flagged"><i class='bx bx-error'></i> Unusual Pairing</span>` : ''}
                            </div>
                            <span class="queue-item-meta">${assetType} • ${defectClass} • #${frameId}</span>
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
