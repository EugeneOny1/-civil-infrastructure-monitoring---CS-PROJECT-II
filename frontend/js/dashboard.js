/**
 * Dashboard Module - Engineer Monitoring Dashboard (Figure 4.7)
 * Apple-Inspired Clean Light Aesthetic with Interactive Chart.js & Critical Calendar
 */
const Dashboard = {
    trendChart: null,

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
        const calRangeSelect = document.getElementById('calRangeSelect');

        if (rangeSelect) rangeSelect.addEventListener('change', () => this.loadDegradationChart());
        if (viewBySelect) viewBySelect.addEventListener('change', () => this.loadDegradationChart());

        if (countySelect) countySelect.addEventListener('change', () => {
            this.loadDegradationChart();
            this.loadCriticalCalendar();
        });

        if (wardSelect) wardSelect.addEventListener('change', () => {
            this.loadDegradationChart();
            this.loadCriticalCalendar();
        });

        if (calRangeSelect) calRangeSelect.addEventListener('change', () => {
            this.loadCriticalCalendar();
        });
    },

    async loadDashboardData() {
        await Promise.all([
            this.loadKpis(),
            this.loadDegradationChart(),
            this.loadCriticalCalendar(),
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

        // Render recurrence insights from real database history (Section 31)
        this.renderRecurrenceInsights(summary.recurrence_insights);

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

        // Handle empty data state
        if (!hasData) {
            if (emptyState) emptyState.classList.remove('hidden');
            if (this.trendChart) {
                this.trendChart.destroy();
                this.trendChart = null;
            }
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            return;
        } else {
            if (emptyState) emptyState.classList.add('hidden');
        }

        // Section 25: Use Chart.js with smooth monotone cubic interpolation
        if (typeof Chart !== 'undefined') {
            if (this.trendChart) {
                this.trendChart.destroy();
                this.trendChart = null;
            }

            const ctx = canvas.getContext('2d');
            const labels = trendData.map(d => d.period);

            const datasets = series.map(s => {
                const color = COLORS[s] || '#94a3b8';
                return {
                    label: s,
                    data: trendData.map(d => d[s] || 0),
                    borderColor: color,
                    backgroundColor: color + '1a',
                    tension: 0.35,
                    cubicInterpolationMode: 'monotone',
                    fill: false,
                    pointRadius: 3.5,
                    pointHoverRadius: 6,
                    pointBackgroundColor: color,
                    pointBorderColor: '#0f172a',
                    pointBorderWidth: 1.5,
                    borderWidth: 2.5
                };
            });

            this.trendChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            backgroundColor: '#0f172a',
                            titleColor: '#f8fafc',
                            bodyColor: '#cbd5e1',
                            borderColor: 'rgba(255, 255, 255, 0.12)',
                            borderWidth: 1,
                            padding: 10,
                            boxPadding: 4,
                            usePointStyle: true,
                            callbacks: {
                                footer: (items) => {
                                    let sum = 0;
                                    items.forEach(it => { sum += (it.parsed.y || 0); });
                                    return `Total Period Reports: ${sum}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                color: 'rgba(255, 255, 255, 0.05)',
                                drawBorder: false
                            },
                            ticks: {
                                color: '#94a3b8',
                                font: { size: 10, family: 'Inter, Montserrat, sans-serif' }
                            }
                        },
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: 'rgba(255, 255, 255, 0.08)',
                                drawBorder: false
                            },
                            ticks: {
                                color: '#94a3b8',
                                font: { size: 10, family: 'Inter, Montserrat, sans-serif' },
                                precision: 0
                            }
                        }
                    }
                }
            });
        }
    },

    async loadCriticalCalendar() {
        const calRange = document.getElementById('calRangeSelect')?.value || '6m';
        const county = document.getElementById('trendCountySelect')?.value || 'all';
        const ward = document.getElementById('trendWardSelect')?.value || 'all';

        try {
            const calData = await window.Api.getCriticalCalendar({
                range: calRange,
                county: county,
                ward: ward
            });
            this.renderCriticalCalendarGrid(calData);
        } catch (e) {
            console.error("Critical calendar load error:", e);
        }
    },

    renderCriticalCalendarGrid(calData) {
        const gridContainer = document.getElementById('criticalCalendarGrid');
        const subTitle = document.getElementById('calSubtitle');
        if (!gridContainer || !calData) return;

        if (subTitle) {
            const count = calData.total_critical_reports ?? 0;
            subTitle.textContent = `${count} Critical Incident${count === 1 ? '' : 's'} (${calData.time_range})`;
        }

        const days = calData.days || [];
        if (days.length === 0) {
            gridContainer.innerHTML = '<div style="padding:1rem; color:#94a3b8; font-size:0.8rem;">No critical incidents recorded in this timeframe.</div>';
            return;
        }

        // Group continuous daily records into columns of weeks (7 days per column)
        const weekCols = [];
        let currentWeek = [];

        // Pre-pad first week if start day is not Sunday (or Monday)
        const firstDayOfWeek = days[0].day_of_week; // 0=Mon, 6=Sun
        for (let i = 0; i < firstDayOfWeek; i++) {
            currentWeek.push(null);
        }

        days.forEach(day => {
            currentWeek.push(day);
            if (currentWeek.length === 7) {
                weekCols.push(currentWeek);
                currentWeek = [];
            }
        });

        if (currentWeek.length > 0) {
            while (currentWeek.length < 7) {
                currentWeek.push(null);
            }
            weekCols.push(currentWeek);
        }

        gridContainer.innerHTML = weekCols.map(col => `
            <div class="cal-week-col">
                ${col.map(d => {
                    if (!d) {
                        return '<div class="cal-day-cell" style="opacity:0; pointer-events:none;"></div>';
                    }
                    const reportLabel = d.count > 0 && d.reports && d.reports.length
                        ? `\nCases: ${d.reports.slice(0, 3).join(', ')}${d.reports.length > 3 ? ' +' + (d.reports.length - 3) + ' more' : ''}`
                        : '';
                    const titleText = `${d.date}: ${d.count} critical report${d.count === 1 ? '' : 's'}${reportLabel}`;
                    return `
                        <div class="cal-day-cell cal-intensity-${d.intensity}"
                             data-date="${d.date}"
                             data-count="${d.count}"
                             title="${titleText}">
                        </div>
                    `;
                }).join('')}
            </div>
        `).join('');

        // Wire cell click behavior (Section 29: Low-risk filter to prioritized queue)
        gridContainer.querySelectorAll('.cal-day-cell').forEach(cell => {
            const cnt = parseInt(cell.getAttribute('data-count') || '0', 10);
            if (cnt > 0) {
                cell.addEventListener('click', () => {
                    const date = cell.getAttribute('data-date');
                    const severitySelect = document.getElementById('filterSeveritySelect');
                    if (severitySelect) {
                        severitySelect.value = 'Critical';
                        this.loadReportsList();
                    }
                    if (window.App && typeof window.App.showToast === 'function') {
                        window.App.showToast(`Filtered queue to Critical reports. Date selected: ${date} (${cnt} case${cnt === 1 ? '' : 's'})`, 'info');
                    }
                });
            }
        });
    },

    renderRecurrenceInsights(insights) {
        const container = document.getElementById('dashboardRecurrenceInsights');
        if (!container) return;

        if (!insights || !Array.isArray(insights) || insights.length === 0) {
            container.innerHTML = '';
            return;
        }

        const icons = [
            'bx-trending-up',
            'bx-map-pin',
            'bx-calendar-exclamation',
            'bx-sync'
        ];

        container.innerHTML = insights.map((item, idx) => `
            <div class="recurrence-insight-card">
                <div class="insight-header">
                    <i class='bx ${icons[idx % icons.length]}' style="color: #0284c7; font-size: 1rem;"></i>
                    <span>${item.title}</span>
                </div>
                <div class="insight-value">${item.value}</div>
                <div class="insight-basis">${item.basis}</div>
            </div>
        `).join('');
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
                const frameId = r.display_id || (r.report_id ? `#REP-${r.report_id.slice(-6).toUpperCase()}` : `#REP-${String(r._id).slice(-6).toUpperCase()}`);
                const status = r.status || 'Received';
                const statusSlug = status.toLowerCase().replace(' ', '-');
                const isFlagged = r.validation_status === 'unusual' || r.requires_engineer_review === true || r.metadata?.is_unusual === true;

                return `
                    <div class="queue-item-card ${isFlagged ? 'is-flagged' : ''}" data-report-id="${r.report_id || r._id}">
                        <div class="queue-item-info">
                            <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                                <span class="queue-item-title">${location}</span>
                                <span class="status-chip ${statusSlug}">${status}</span>
                                ${isFlagged ? `<span class="badge-tag flagged"><i class='bx bx-error'></i> Unusual Pairing</span>` : ''}
                            </div>
                            <span class="queue-item-meta">${assetType} • ${defectClass} • ${frameId}</span>
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
