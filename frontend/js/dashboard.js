/**
 * Dashboard Module - Engineer Monitoring Dashboard (Figure 4.7)
 * Apple-Inspired Clean Light Aesthetic with Interactive Chart.js & Critical Calendar
 */
const Dashboard = {
    trendChart: null,
    selectedDateFilter: null,

    init() {
        this.bindEvents();
    },

    bindEvents() {
        const filterSelect = document.getElementById('filterSeveritySelect');
        if (filterSelect) {
            filterSelect.addEventListener('change', () => this.loadReportsList());
        }

        const btnClearDate = document.getElementById('btnClearDateFilter');
        if (btnClearDate) {
            btnClearDate.addEventListener('click', () => {
                this.selectedDateFilter = null;
                const notice = document.getElementById('queueDateFilterNotice');
                if (notice) notice.classList.add('hidden');
                this.loadReportsList();
            });
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
            const cVal = countySelect.value;
            const wVal = wardSelect ? wardSelect.value : 'all';
            this.loadKpis(cVal, wVal);
            this.loadDegradationChart();
            this.loadCriticalCalendar();
            this.loadReportsList();
        });

        if (wardSelect) wardSelect.addEventListener('change', () => {
            const cVal = countySelect ? countySelect.value : 'all';
            const wVal = wardSelect.value;
            this.loadKpis(cVal, wVal);
            this.loadDegradationChart();
            this.loadCriticalCalendar();
            this.loadReportsList();
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

    async loadKpis(countyParam, wardParam) {
        try {
            const county = countyParam !== undefined ? countyParam : (document.getElementById('trendCountySelect')?.value || 'all');
            const ward = wardParam !== undefined ? wardParam : (document.getElementById('trendWardSelect')?.value || 'all');

            const queueEl = document.getElementById('kpiActiveQueue');
            const verifiedEl = document.getElementById('kpiVerifiedCount');
            const modelEl = document.getElementById('kpiModelVersion');
            const critEl = document.getElementById('kpiCriticalHazards');

            const isGeoFiltered = (county && county !== 'all') || (ward && ward !== 'all' && ward !== 'All Areas');

            if (!isGeoFiltered) {
                const summary = await window.Api.getSummary();
                if (queueEl) queueEl.textContent = summary.active_defect_queue ?? 0;
                if (verifiedEl) verifiedEl.textContent = summary.verified_inspections ?? 0;
                if (modelEl) modelEl.textContent = summary.model_version || 'SSD-MobileNetV2';
                if (critEl) critEl.textContent = summary.severity_breakdown?.Critical ?? 0;
            } else {
                // Compute geographic KPI counts from reports matching geographic filter
                const data = await window.Api.getReports({ exclude_status: 'none' });
                let reports = Array.isArray(data.reports) ? data.reports : [];
                if (county && county !== 'all') {
                    reports = reports.filter(r => {
                        const loc = (r.asset?.location || r.metadata?.location_name || '').toLowerCase();
                        return loc.includes(county.toLowerCase());
                    });
                }
                if (ward && ward !== 'all' && ward !== 'All Areas') {
                    reports = reports.filter(r => {
                        const loc = (r.asset?.location || r.metadata?.location_name || '').toLowerCase();
                        return loc.includes(ward.toLowerCase());
                    });
                }

                const activeQueue = reports.filter(r => (r.status || '').toLowerCase() !== 'resolved').length;
                const verified = reports.filter(r => (r.status || '') === 'Verified').length;
                const critical = reports.filter(r => {
                    const sev = (r.assessment?.relative_severity || r.metadata?.relative_severity || '').toLowerCase();
                    return sev === 'critical' || sev === 'high';
                }).length;

                if (queueEl) queueEl.textContent = activeQueue;
                if (verifiedEl) verifiedEl.textContent = verified;
                if (modelEl) modelEl.textContent = 'SSD-MobileNetV2';
                if (critEl) critEl.textContent = critical;
            }
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

    getTrendChartOptions() {
        return {
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
        };
    },

    drawHistoricalDefectChart(apiData) {
        const canvas = document.getElementById('degradationChart');
        const emptyState = document.getElementById('trendEmptyState');
        const legendContainer = document.getElementById('trendLegend');
        if (!canvas) return;

        const trendData = Array.isArray(apiData?.trend_data) ? apiData.trend_data : [];
        const series = Array.isArray(apiData?.series) ? apiData.series : ['Crack', 'Pothole', 'Surface deterioration'];
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
        if (locEl) locEl.textContent = summary.most_active_location || 'None';

        // Render recurrence insights from real database history (Section 31)
        this.renderRecurrenceInsights(summary.recurrence_insights);

        // Render monitoring insights panel (Sections 34, 35, 36)
        this.renderMonitoringInsights(apiData?.monitoring_insights);

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
            'Low': '#0284c7'
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

        const county = document.getElementById('trendCountySelect')?.value || 'all';

        // Section 7: Chart.js Zero-Data Safety
        if (!hasData) {
            const emptyTextEl = document.getElementById('trendEmptyStateText');
            if (emptyTextEl) {
                const geoLabel = county !== 'all' ? `No defect reports recorded for ${county} in the selected period.` : 'No defect reports recorded for this selection.';
                emptyTextEl.innerHTML = `<i class='bx bx-info-circle'></i> ${apiData?.message || geoLabel}`;
            }
            if (emptyState) emptyState.classList.remove('hidden');

            const labels = trendData.length > 0 ? trendData.map(d => d.period) : ['Month 1', 'Month 2', 'Month 3', 'Month 4', 'Month 5', 'Month 6'];
            const zeroDatasets = series.map(s => {
                const color = COLORS[s] || '#94a3b8';
                return {
                    label: s,
                    data: labels.map(() => 0),
                    borderColor: color,
                    backgroundColor: color + '1a',
                    tension: 0.35,
                    cubicInterpolationMode: 'monotone',
                    fill: false,
                    pointRadius: 2,
                    pointHoverRadius: 4,
                    pointBackgroundColor: color,
                    pointBorderColor: '#0f172a',
                    pointBorderWidth: 1.5,
                    borderWidth: 2
                };
            });

            if (this.trendChart) {
                this.trendChart.destroy();
                this.trendChart = null;
            }
            if (typeof Chart !== 'undefined') {
                const ctx = canvas.getContext('2d');
                this.trendChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: zeroDatasets
                    },
                    options: this.getTrendChartOptions()
                });
            }
            return;
        } else {
            if (emptyState) emptyState.classList.add('hidden');
        }

        // Section 25 & 39: Chart.js with smooth monotone cubic interpolation for populated data
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
                    pointRadius: 3,
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
                options: this.getTrendChartOptions()
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

    getCalTooltip() {
        let el = document.getElementById('calCustomTooltip');
        if (!el) {
            el = document.createElement('div');
            el.id = 'calCustomTooltip';
            el.style.cssText = `
                position: fixed;
                display: none;
                z-index: 10000;
                background: #0f172a;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 0.75rem;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
                pointer-events: none;
                max-width: 260px;
                line-height: 1.45;
                transition: opacity 0.12s ease;
            `;
            document.body.appendChild(el);
        }
        return el;
    },

    renderCriticalCalendarGrid(calData) {
        const gridContainer = document.getElementById('criticalCalendarGrid');
        const subTitle = document.getElementById('calSubtitle');
        if (!gridContainer || !calData) return;

        const total = calData.total_critical_reports ?? 0;
        if (subTitle) {
            if (total === 0) {
                subTitle.textContent = `No critical reports recorded for this selection.`;
            } else {
                subTitle.textContent = `${total} Critical Incident${total === 1 ? '' : 's'} (${calData.time_range || 'Selected timeframe'})`;
            }
        }

        const days = Array.isArray(calData.days) ? calData.days : [];
        if (days.length === 0) {
            gridContainer.innerHTML = '<div style="padding:1.5rem; text-align:center; color:#94a3b8; font-size:0.85rem; border:1px dashed var(--border-color); border-radius:6px;">No critical reports recorded for this selection.</div>';
            return;
        }

        const formatCalDate = (dateStr) => {
            if (!dateStr) return '';
            try {
                const parts = dateStr.split('-');
                if (parts.length === 3) {
                    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                    return `${parseInt(parts[2], 10)} ${months[parseInt(parts[1], 10) - 1]} ${parts[0]}`;
                }
            } catch (e) {}
            return dateStr;
        };

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
                    return `
                        <div class="cal-day-cell cal-intensity-${d.intensity}"
                             data-date="${d.date}"
                             data-count="${d.count}"
                             data-breakdown='${JSON.stringify(d.defect_breakdown || {})}'
                             data-corridor="${(d.top_corridor || '').replace(/"/g, '&quot;')}"
                             tabindex="0"
                             role="button"
                             aria-label="${d.date}: ${d.count} critical reports">
                        </div>
                    `;
                }).join('')}
            </div>
        `).join('');

        // Wire interactive hover tooltip (Section 40) & click filter (Section 41)
        const cells = gridContainer.querySelectorAll('.cal-day-cell:not([style*="opacity:0"])');
        cells.forEach(cell => {
            const date = cell.getAttribute('data-date');
            const cnt = parseInt(cell.getAttribute('data-count') || '0', 10);
            let breakdown = {};
            try { breakdown = JSON.parse(cell.getAttribute('data-breakdown') || '{}'); } catch (e) {}
            const corridor = cell.getAttribute('data-corridor') || '';

            const showTooltip = (e) => {
                const tip = this.getCalTooltip();
                const formattedDate = formatCalDate(date);
                let html = `<div style="font-weight:700; color:#f8fafc; margin-bottom:4px; font-size:0.8rem;">${formattedDate}</div>`;

                if (cnt === 0) {
                    html += `<div style="color:#94a3b8; font-size:0.75rem;">0 Critical Reports</div>`;
                } else {
                    html += `<div style="font-weight:700; color:#ef4444; margin-bottom:6px; font-size:0.78rem;">${cnt} Critical Report${cnt === 1 ? '' : 's'}</div>`;

                    const breakdownEntries = Object.entries(breakdown);
                    if (breakdownEntries.length > 0) {
                        const lines = breakdownEntries.map(([cls, c]) => `<span>${c} ${cls}${c > 1 ? 's' : ''}</span>`);
                        html += `<div style="color:#cbd5e1; margin-bottom:6px; font-size:0.74rem; display:flex; flex-direction:column; gap:2px;">${lines.join('')}</div>`;
                    }

                    if (corridor) {
                        html += `<div style="color:#94a3b8; font-size:0.72rem; margin-top:4px; border-top:1px solid #334155; padding-top:4px;">Most active corridor:<br><strong style="color:#38bdf8;">${corridor}</strong></div>`;
                    }
                }

                tip.innerHTML = html;
                tip.style.display = 'block';
                tip.style.opacity = '1';

                const rect = cell.getBoundingClientRect();
                const tipWidth = 220;
                let left = rect.left + (rect.width / 2) - (tipWidth / 2);
                if (left < 10) left = 10;
                if (left + tipWidth > window.innerWidth - 10) left = window.innerWidth - tipWidth - 10;
                tip.style.left = `${left}px`;
                tip.style.top = `${Math.max(10, rect.top - 100)}px`;
            };

            const hideTooltip = () => {
                const tip = document.getElementById('calCustomTooltip');
                if (tip) {
                    tip.style.display = 'none';
                    tip.style.opacity = '0';
                }
            };

            cell.addEventListener('mouseenter', showTooltip);
            cell.addEventListener('focus', showTooltip);
            cell.addEventListener('mouseleave', hideTooltip);
            cell.addEventListener('blur', hideTooltip);

            // Click behavior: filter prioritized queue to reports on this date (Section 41)
            cell.addEventListener('click', () => {
                if (cnt > 0) {
                    this.selectedDateFilter = date;
                    const dateNotice = document.getElementById('queueDateFilterNotice');
                    const dateVal = document.getElementById('queueDateFilterVal');
                    if (dateNotice && dateVal) {
                        dateNotice.classList.remove('hidden');
                        dateVal.textContent = `${formatCalDate(date)} (${cnt} Critical Report${cnt === 1 ? '' : 's'})`;
                    }
                    this.loadReportsList();
                    if (window.App && typeof window.App.showToast === 'function') {
                        window.App.showToast(`Filtered queue to reports on ${formatCalDate(date)}`, 'info');
                    }
                } else {
                    if (window.App && typeof window.App.showToast === 'function') {
                        window.App.showToast(`No critical reports recorded on ${formatCalDate(date)}`, 'info');
                    }
                }
            });
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

    renderMonitoringInsights(insights) {
        const container = document.getElementById('monitoringInsightsContent');
        if (!container) return;

        if (!insights || !insights.has_sufficient_data) {
            container.innerHTML = `
                <div style="padding: 1.25rem; color: #64748b; font-size: 0.85rem; background: rgba(15, 23, 42, 0.04); border-radius: 6px; border: 1px dashed var(--border-color); display: flex; align-items: center; gap: 10px;">
                    <i class='bx bx-info-circle' style="font-size: 1.35rem; color: #0284c7; flex-shrink: 0;"></i>
                    <span>${insights?.message || 'Not enough historical data for this selection.'}</span>
                </div>
            `;
            return;
        }

        const cards = [];

        // 1. Critical Defect Activity (Last 30 Days)
        const isUp = insights.critical_change && insights.critical_change.includes('+');
        cards.push(`
            <div class="recurrence-insight-card">
                <div class="insight-header">
                    <i class='bx bx-alarm-exclamation' style="color: #ef4444; font-size: 1rem;"></i>
                    <span>30-Day Critical Defect Volume</span>
                </div>
                <div class="insight-value">
                    ${insights.critical_last_30d ?? 0} Reports
                    <span style="font-size: 0.76rem; font-weight: 600; color: ${isUp ? '#ef4444' : '#10b981'}; margin-left: 4px;">
                        (${insights.critical_change || 'No prior period comparison'})
                    </span>
                </div>
                <div class="insight-basis">Empirical rolling 30-day window comparison</div>
            </div>
        `);

        // 2. Highest Repeat Corridor
        cards.push(`
            <div class="recurrence-insight-card">
                <div class="insight-header">
                    <i class='bx bx-map-pin' style="color: #f59e0b; font-size: 1rem;"></i>
                    <span>Corridor Defect Recurrence</span>
                </div>
                <div class="insight-value">${insights.top_corridor_repeat || 'Not enough historical data yet'}</div>
                <div class="insight-basis">Corridor with highest repeat-incident density</div>
            </div>
        `);

        // 3. Top Affected Infrastructure Asset
        cards.push(`
            <div class="recurrence-insight-card">
                <div class="insight-header">
                    <i class='bx bx-building' style="color: #0284c7; font-size: 1rem;"></i>
                    <span>Primary Asset Classification</span>
                </div>
                <div class="insight-value">${insights.top_asset_type || 'Road / Pavement'}</div>
                <div class="insight-basis">Most frequently affected civil infrastructure asset</div>
            </div>
        `);

        // 4. Operational Lifecycle Velocity
        cards.push(`
            <div class="recurrence-insight-card">
                <div class="insight-header">
                    <i class='bx bx-time-five' style="color: #10b981; font-size: 1rem;"></i>
                    <span>Average Lifecycle Velocity</span>
                </div>
                <div class="insight-value" style="display: flex; gap: 1rem; font-size: 0.82rem; flex-wrap: wrap;">
                    <span>Received → Verified: <strong>${insights.avg_received_to_verified || 'Pending data'}</strong></span>
                    <span>Verified → Resolved: <strong>${insights.avg_verified_to_resolved || 'Pending data'}</strong></span>
                </div>
                <div class="insight-basis">Recorded duration across professional review transitions</div>
            </div>
        `);

        // 5. Historical Weather Context (Sections 36, 37, 38)
        if (insights.weather_insight) {
            const w = insights.weather_insight;
            if (w.observation) {
                cards.push(`
                    <div class="recurrence-insight-card" style="border-left: 3px solid #0284c7;">
                        <div class="insight-header">
                            <i class='bx bx-cloud-rain' style="color: #0284c7; font-size: 1rem;"></i>
                            <span>${w.headline || 'Observed Weather Association'}</span>
                        </div>
                        <div class="insight-value" style="font-size: 0.82rem; font-weight: 500; color: #1e293b; line-height: 1.45;">
                            ${w.observation}
                        </div>
                        <div class="insight-basis">${w.qualification || 'Observed historical precipitation association. Does not constitute mechanical causation.'}</div>
                    </div>
                `);
            } else if (w.headline) {
                cards.push(`
                    <div class="recurrence-insight-card">
                        <div class="insight-header">
                            <i class='bx bx-cloud' style="color: #64748b; font-size: 1rem;"></i>
                            <span>${w.headline}</span>
                        </div>
                        <div class="insight-value" style="font-size: 0.8rem; color: #64748b;">
                            ${w.message || 'Not enough historical weather data yet.'}
                        </div>
                        <div class="insight-basis">${w.qualification || 'Historical precipitation data from Open-Meteo archive.'}</div>
                    </div>
                `);
            }
        }

        container.innerHTML = cards.join('');
    },

    drawDegradationChart(trendData, threshold = 68) {
        // Backwards compatibility alias
        this.loadDegradationChart();
    },

    async loadReportsList() {
        const queueContainer = document.getElementById('defectQueueList');
        if (!queueContainer) return;

        const filterVal = document.getElementById('filterSeveritySelect')?.value || '';
        const countyVal = document.getElementById('trendCountySelect')?.value || 'all';
        const wardVal = document.getElementById('trendWardSelect')?.value || 'all';

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

            // County / Ward filter
            if (countyVal && countyVal.toLowerCase() !== 'all') {
                reports = reports.filter(r => {
                    const loc = (r.asset?.location || r.metadata?.location_name || '').toLowerCase();
                    return loc.includes(countyVal.toLowerCase());
                });
            }

            if (wardVal && wardVal.toLowerCase() !== 'all' && wardVal.toLowerCase() !== 'all areas') {
                reports = reports.filter(r => {
                    const loc = (r.asset?.location || r.metadata?.location_name || '').toLowerCase();
                    return loc.includes(wardVal.toLowerCase());
                });
            }

            // Calendar date filter (Section 41)
            if (this.selectedDateFilter) {
                reports = reports.filter(r => {
                    const dtStr = r.date_submitted || r.created_at || '';
                    return dtStr.startsWith(this.selectedDateFilter);
                });
            }

            if (reports.length === 0) {
                queueContainer.innerHTML = `
                    <div class="queue-empty-state" style="padding: 2.5rem 1.5rem; text-align: center; color: #64748b; background: rgba(15, 23, 42, 0.03); border: 1px dashed var(--border-color); border-radius: 8px;">
                        <i class='bx bx-folder-open' style="font-size: 2rem; color: #94a3b8; margin-bottom: 0.5rem; display: block;"></i>
                        <p style="font-weight: 500; margin: 0; font-size: 0.88rem;">No reports match the selected filters.</p>
                    </div>
                `;
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
