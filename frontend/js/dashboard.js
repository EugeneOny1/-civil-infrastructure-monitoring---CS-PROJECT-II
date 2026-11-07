/**
 * Dashboard Module - Engineer Monitoring Dashboard (Figure 4.7)
 * Apple & PlayStation Inspired Clean Contrast Aesthetic with Interactive Chart.js & Critical Calendar
 */
const Dashboard = {
    trendChart: null,
    selectedDateFilter: null,
    calendarData: null,
    calendarMonths: [],
    activeMonthIndex: null,
    isVerifiedFilterActive: false,
    previousFilterSeverityValue: '',
    activeIntelligenceMode: 'rainfall_defect_pattern',
    activeIntelligenceQuery: '',

    init() {
        this.bindEvents();
        this.initMonitoringIntelligence();
    },

    bindEvents() {
        const filterSelect = document.getElementById('filterSeveritySelect');
        const btnClearDate = document.getElementById('btnClearDateFilter');
        if (btnClearDate) {
            btnClearDate.addEventListener('click', () => {
                this.selectedDateFilter = null;
                const notice = document.getElementById('queueDateFilterNotice');
                if (notice) notice.classList.add('hidden');
                this.renderMonthCarousel();
                this.loadReportsList();
            });
        }

        // Section 36: Verified Inspections KPI Filter Toggle
        const kpiVerified = document.getElementById('kpiCardVerified');
        const kpiVerifiedCount = document.getElementById('kpiVerifiedCount');
        const activeBadge = document.getElementById('kpiVerifiedActiveBadge');

        const toggleVerifiedFilter = () => {
            const select = document.getElementById('filterSeveritySelect');
            if (!select) return;

            if (this.isVerifiedFilterActive) {
                // Second click: restore prior queue filter
                this.isVerifiedFilterActive = false;
                if (kpiVerified) kpiVerified.classList.remove('kpi-card-active');
                if (activeBadge) activeBadge.classList.add('hidden');
                select.value = this.previousFilterSeverityValue || '';
                this.loadReportsList();
            } else {
                // First click: filter queue to Verified
                this.previousFilterSeverityValue = select.value === 'Verified' ? '' : select.value;
                this.isVerifiedFilterActive = true;
                if (kpiVerified) kpiVerified.classList.add('kpi-card-active');
                if (activeBadge) activeBadge.classList.remove('hidden');
                select.value = 'Verified';
                this.loadReportsList();
                const queueCard = document.querySelector('.queue-card');
                if (queueCard && typeof queueCard.scrollIntoView === 'function') {
                    queueCard.scrollIntoView({ behavior: 'smooth' });
                }
            }
        };

        if (kpiVerified) kpiVerified.addEventListener('click', toggleVerifiedFilter);
        if (kpiVerifiedCount) kpiVerifiedCount.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleVerifiedFilter();
        });

        if (filterSelect) {
            filterSelect.addEventListener('change', () => {
                if (filterSelect.value === 'Verified') {
                    this.isVerifiedFilterActive = true;
                    if (kpiVerified) kpiVerified.classList.add('kpi-card-active');
                    if (activeBadge) activeBadge.classList.remove('hidden');
                } else {
                    this.isVerifiedFilterActive = false;
                    if (kpiVerified) kpiVerified.classList.remove('kpi-card-active');
                    if (activeBadge) activeBadge.classList.add('hidden');
                    this.previousFilterSeverityValue = filterSelect.value;
                }
                this.loadReportsList();
            });
        }

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
            this.loadFocusedIntelligence(this.activeIntelligenceMode, this.activeIntelligenceQuery);
        });

        if (wardSelect) wardSelect.addEventListener('change', () => {
            const cVal = countySelect ? countySelect.value : 'all';
            const wVal = wardSelect.value;
            this.loadKpis(cVal, wVal);
            this.loadDegradationChart();
            this.loadCriticalCalendar();
            this.loadReportsList();
            this.loadFocusedIntelligence(this.activeIntelligenceMode, this.activeIntelligenceQuery);
        });

        if (calRangeSelect) calRangeSelect.addEventListener('change', () => {
            this.loadCriticalCalendar();
            this.loadFocusedIntelligence(this.activeIntelligenceMode, this.activeIntelligenceQuery);
        });

        // Month-Centric Carousel Navigation Controls
        const btnCalPrev = document.getElementById('btnCalPrevMonth');
        const btnCalNext = document.getElementById('btnCalNextMonth');
        if (btnCalPrev) btnCalPrev.addEventListener('click', () => this.switchCarouselMonth(this.activeMonthIndex - 1));
        if (btnCalNext) btnCalNext.addEventListener('click', () => this.switchCarouselMonth(this.activeMonthIndex + 1));

        const calStage = document.getElementById('criticalCalendarCarouselStage');
        if (calStage) {
            calStage.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    this.switchCarouselMonth(this.activeMonthIndex - 1);
                } else if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    this.switchCarouselMonth(this.activeMonthIndex + 1);
                }
            });

            // Touch swipe support
            let touchStartX = 0;
            calStage.addEventListener('touchstart', (e) => {
                if (e.changedTouches && e.changedTouches[0]) {
                    touchStartX = e.changedTouches[0].screenX;
                }
            }, { passive: true });

            calStage.addEventListener('touchend', (e) => {
                if (e.changedTouches && e.changedTouches[0]) {
                    const diff = e.changedTouches[0].screenX - touchStartX;
                    if (diff > 45) {
                        this.switchCarouselMonth(this.activeMonthIndex - 1);
                    } else if (diff < -45) {
                        this.switchCarouselMonth(this.activeMonthIndex + 1);
                    }
                }
            }, { passive: true });
        }
    },

    async loadDashboardData() {
        await Promise.all([
            this.loadKpis(),
            this.loadDegradationChart(),
            this.loadCriticalCalendar(),
            this.loadReportsList(),
            this.loadFocusedIntelligence(this.activeIntelligenceMode)
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
                    backgroundColor: '#0a0f1d',
                    titleColor: '#f8fafc',
                    bodyColor: '#cbd5e1',
                    borderColor: 'rgba(0, 112, 209, 0.4)',
                    borderWidth: 1,
                    padding: 10,
                    boxPadding: 5,
                    usePointStyle: true,
                    callbacks: {
                        footer: (items) => {
                            let sum = 0;
                            items.forEach(it => { sum += (it.parsed.y || 0); });
                            return `Total Reports: ${sum}`;
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
                    tension: 0,
                    fill: false,
                    pointRadius: 4,
                    pointHoverRadius: 7,
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

        // Section 3: Direct point-to-point line chart (tension: 0, no cubic interpolation)
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
                    tension: 0,
                    fill: false,
                    pointRadius: 4,
                    pointHoverRadius: 7,
                    pointBackgroundColor: color,
                    pointBorderColor: '#0f172a',
                    pointBorderWidth: 1.5,
                    borderWidth: 2
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
        this.calendarData = calData;
        this.calendarMonths = Array.isArray(calData?.months) ? calData.months : [];
        const total = calData?.total_critical_reports ?? 0;

        const subTitle = document.getElementById('calSubtitle');
        if (subTitle) {
            if (total === 0) {
                subTitle.textContent = `No critical reports recorded for this selection.`;
            } else {
                subTitle.textContent = `${total} Critical Incident${total === 1 ? '' : 's'} (${calData.time_range || 'Selected timeframe'})`;
            }
        }

        // Default active month to the latest month if unset or out of range
        if (this.activeMonthIndex === null || this.activeMonthIndex === undefined || this.activeMonthIndex >= this.calendarMonths.length) {
            this.activeMonthIndex = Math.max(0, this.calendarMonths.length - 1);
        }

        this.renderMonthCarousel();
    },

    switchCarouselMonth(index) {
        if (!this.calendarMonths || this.calendarMonths.length === 0) return;
        if (index < 0 || index >= this.calendarMonths.length) return;
        this.activeMonthIndex = index;
        this.renderMonthCarousel();
    },

    renderMonthCarousel() {
        const stage = document.getElementById('criticalCalendarCarouselStage');
        const currentMonthLabel = document.getElementById('calCurrentMonthLabel');
        const prevBtn = document.getElementById('btnCalPrevMonth');
        const nextBtn = document.getElementById('btnCalNextMonth');
        const summaryStrip = document.getElementById('calActiveMonthSummary');
        if (!stage) return;

        if (!this.calendarMonths || this.calendarMonths.length === 0) {
            stage.innerHTML = '<div style="padding:2rem; text-align:center; color:#94a3b8; font-size:0.85rem; width:100%;">No critical reports recorded for this selection.</div>';
            if (currentMonthLabel) currentMonthLabel.textContent = 'No Data';
            if (prevBtn) prevBtn.disabled = true;
            if (nextBtn) nextBtn.disabled = true;
            if (summaryStrip) summaryStrip.innerHTML = '';
            return;
        }

        // Clamp active month index
        if (this.activeMonthIndex < 0) this.activeMonthIndex = 0;
        if (this.activeMonthIndex >= this.calendarMonths.length) this.activeMonthIndex = this.calendarMonths.length - 1;

        const activeMonth = this.calendarMonths[this.activeMonthIndex];
        if (currentMonthLabel && activeMonth) {
            currentMonthLabel.textContent = activeMonth.label;
        }

        if (prevBtn) prevBtn.disabled = (this.activeMonthIndex <= 0);
        if (nextBtn) nextBtn.disabled = (this.activeMonthIndex >= this.calendarMonths.length - 1);

        const formatCalDate = (dateStr) => {
            if (!dateStr) return '';
            try {
                const parts = dateStr.split('-');
                if (parts.length === 3) {
                    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                    return `${parseInt(parts[2], 10)} ${months[parseInt(parts[1], 10) - 1]} ${parts[0]}`;
                }
            } catch (e) { }
            return dateStr;
        };

        const renderMonthCardHtml = (month, roleClass) => {
            if (!month) return '';
            const days = Array.isArray(month.days) ? month.days : [];
            const firstDay = days[0];
            // In python weekday: 0=Mon, 6=Sun. Calendar header is S M T W T F S (Sun=0).
            // Convert to Sunday-first (0=Sun, 1=Mon, ..., 6=Sat)
            const padCount = firstDay ? ((firstDay.day_of_week + 1) % 7) : 0;

            const emptyPadHtml = Array.from({ length: padCount })
                .map(() => '<div class="cal-day-cell-square is-empty"></div>')
                .join('');

            const daysHtml = days.map(d => {
                const dayNum = parseInt(d.date.split('-')[2], 10);
                const isSelected = this.selectedDateFilter === d.date;
                return `
                    <div class="cal-day-cell-square cal-intensity-${d.intensity} ${isSelected ? 'is-selected' : ''}"
                         data-date="${d.date}"
                         data-count="${d.count}"
                         data-rainfall="${d.rainfall_7d !== null && d.rainfall_7d !== undefined ? d.rainfall_7d : ''}"
                         data-breakdown='${JSON.stringify(d.defect_breakdown || {})}'
                         data-corridor="${(d.top_corridor || '').replace(/"/g, '&quot;')}"
                         tabindex="0"
                         role="button"
                         aria-label="${d.date}: ${d.count} critical reports">
                        ${dayNum}
                    </div>
                `;
            }).join('');

            return `
                <div class="cal-month-card ${roleClass}" data-month-key="${month.key}">
                    <div class="cal-month-header">
                        <span class="cal-month-title">${month.label}</span>
                        <span class="cal-month-crit-badge">${month.total_critical} Critical</span>
                    </div>
                    <div class="cal-weekday-row">
                        <span>S</span><span>M</span><span>T</span><span>W</span><span>T</span><span>F</span><span>S</span>
                    </div>
                    <div class="cal-month-grid">
                        ${emptyPadHtml}
                        ${daysHtml}
                    </div>
                </div>
            `;
        };

        const cards = [];
        if (this.activeMonthIndex > 0) {
            cards.push(renderMonthCardHtml(this.calendarMonths[this.activeMonthIndex - 1], 'is-prev'));
        }
        cards.push(renderMonthCardHtml(activeMonth, 'is-active'));
        if (this.activeMonthIndex < this.calendarMonths.length - 1) {
            cards.push(renderMonthCardHtml(this.calendarMonths[this.activeMonthIndex + 1], 'is-next'));
        }

        stage.innerHTML = cards.join('');

        // Wire click on prev/next month cards
        const prevCard = stage.querySelector('.cal-month-card.is-prev');
        if (prevCard) {
            prevCard.addEventListener('click', () => this.switchCarouselMonth(this.activeMonthIndex - 1));
        }
        const nextCard = stage.querySelector('.cal-month-card.is-next');
        if (nextCard) {
            nextCard.addEventListener('click', () => this.switchCarouselMonth(this.activeMonthIndex + 1));
        }

        // Wire active month day cell interactions
        const activeCard = stage.querySelector('.cal-month-card.is-active');
        if (activeCard) {
            const dayCells = activeCard.querySelectorAll('.cal-day-cell-square:not(.is-empty)');
            dayCells.forEach(cell => {
                const date = cell.getAttribute('data-date');
                const cnt = parseInt(cell.getAttribute('data-count') || '0', 10);
                const rainfall = cell.getAttribute('data-rainfall');
                let breakdown = {};
                try { breakdown = JSON.parse(cell.getAttribute('data-breakdown') || '{}'); } catch (e) { }
                const corridor = cell.getAttribute('data-corridor') || '';

                const showTooltip = () => {
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

                    if (rainfall !== null && rainfall !== '' && rainfall !== undefined) {
                        html += `<div style="color:#38bdf8; font-size:0.72rem; margin-top:4px; border-top:1px solid #334155; padding-top:4px;"><i class='bx bx-cloud-rain'></i> Preceding 7-Day Rainfall: <strong>${rainfall} mm</strong></div>`;
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
                    tip.style.top = `${Math.max(10, rect.top - 110)}px`;
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

                cell.addEventListener('click', () => {
                    if (cnt > 0) {
                        if (this.selectedDateFilter === date) {
                            // Toggle off date filter
                            this.selectedDateFilter = null;
                            const notice = document.getElementById('queueDateFilterNotice');
                            if (notice) notice.classList.add('hidden');
                        } else {
                            this.selectedDateFilter = date;
                            const dateNotice = document.getElementById('queueDateFilterNotice');
                            const dateVal = document.getElementById('queueDateFilterVal');
                            if (dateNotice && dateVal) {
                                dateNotice.classList.remove('hidden');
                                dateVal.textContent = `${formatCalDate(date)} (${cnt} Critical Report${cnt === 1 ? '' : 's'})`;
                            }
                        }
                        this.renderMonthCarousel();
                        this.loadReportsList();
                        const queueCard = document.querySelector('.queue-card');
                        if (queueCard && typeof queueCard.scrollIntoView === 'function') {
                            queueCard.scrollIntoView({ behavior: 'smooth' });
                        }
                    } else {
                        if (window.App && typeof window.App.showToast === 'function') {
                            window.App.showToast(`No critical reports recorded on ${formatCalDate(date)}`, 'info');
                        }
                    }
                });
            });
        }

        // Active Month Summary Strip
        if (summaryStrip && activeMonth) {
            summaryStrip.innerHTML = `
                <div class="summary-pill">
                    <span class="summary-pill-label">Critical Reports</span>
                    <span class="summary-pill-value" style="color: #f87171;">${activeMonth.total_critical}</span>
                </div>
                <div class="summary-pill">
                    <span class="summary-pill-label">Most Reported Defect</span>
                    <span class="summary-pill-value" style="color: #38bdf8;">${activeMonth.most_reported_defect || 'None'}</span>
                </div>
                <div class="summary-pill">
                    <span class="summary-pill-label">Most Active Corridor</span>
                    <span class="summary-pill-value" style="color: #fbbf24;">${activeMonth.most_active_corridor || 'None'}</span>
                </div>
                <div class="summary-pill">
                    <span class="summary-pill-label">Resolved During Month</span>
                    <span class="summary-pill-value" style="color: #34d399;">${activeMonth.resolved_during_month || 0}</span>
                </div>
            `;
        }
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

    initMonitoringIntelligence() {
        const selectorGrid = document.getElementById('intelModeSelector');
        if (selectorGrid) {
            selectorGrid.querySelectorAll('.intel-mode-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const mode = btn.getAttribute('data-mode');
                    if (!mode) return;
                    this.activeIntelligenceMode = mode;
                    this.activeIntelligenceQuery = '';

                    // PlayStation hub active state toggle
                    selectorGrid.querySelectorAll('.intel-mode-btn').forEach(b => b.classList.remove('is-active'));
                    btn.classList.add('is-active');

                    // Clear query interpretation banner
                    const interpBanner = document.getElementById('intelQueryExplanation');
                    if (interpBanner) interpBanner.classList.add('hidden');
                    const nlpInput = document.getElementById('intelNlpInput');
                    if (nlpInput) nlpInput.value = '';

                    this.loadFocusedIntelligence(this.activeIntelligenceMode, '');
                });
            });
        }

        const nlpForm = document.getElementById('intelNlpForm');
        if (nlpForm) {
            nlpForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const nlpInput = document.getElementById('intelNlpInput');
                const query = (nlpInput?.value || '').trim();
                if (!query) return;

                this.activeIntelligenceQuery = query;
                this.loadFocusedIntelligence(null, query);
            });
        }

        const suggestionsStrip = document.getElementById('intelNlpSuggestions');
        if (suggestionsStrip) {
            suggestionsStrip.querySelectorAll('.intel-chip-suggestion').forEach(chip => {
                chip.addEventListener('click', () => {
                    const prompt = chip.getAttribute('data-prompt');
                    if (!prompt) return;
                    const nlpInput = document.getElementById('intelNlpInput');
                    if (nlpInput) nlpInput.value = prompt;
                    this.activeIntelligenceQuery = prompt;
                    this.loadFocusedIntelligence(null, prompt);
                });
            });
        }

        const clearBtn = document.getElementById('btnClearQueryInterpretation');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                this.activeIntelligenceQuery = '';
                const nlpInput = document.getElementById('intelNlpInput');
                if (nlpInput) nlpInput.value = '';
                const interpBanner = document.getElementById('intelQueryExplanation');
                if (interpBanner) interpBanner.classList.add('hidden');
                this.loadFocusedIntelligence(this.activeIntelligenceMode, '');
            });
        }
    },

    async loadFocusedIntelligence(mode = null, query = null) {
        const container = document.getElementById('intelResultWorkspace');
        if (!container) return;

        // Render sleek PlayStation loading state
        container.innerHTML = `
            <div style="padding: 2.5rem 1rem; text-align: center; color: #64748b; font-size: 0.85rem;">
                <i class='bx bx-loader-alt bx-spin' style="font-size: 1.8rem; color: #0070d1; display: block; margin: 0 auto 0.65rem auto;"></i>
                <span style="font-weight: 600; color: #1e293b;">Computing Civil Infrastructure Intelligence</span>
                <p style="font-size: 0.76rem; color: #64748b; margin-top: 4px;">Evaluating verified records & telemetry correlations...</p>
            </div>
        `;

        try {
            const params = {};
            if (query && query.trim()) {
                params.query = query.trim();
            } else if (mode) {
                params.mode = mode;
            } else {
                params.mode = this.activeIntelligenceMode || 'rainfall_defect_pattern';
            }

            const county = document.getElementById('trendCountySelect')?.value || 'all';
            const ward = document.getElementById('trendWardSelect')?.value || 'all';
            const range = document.getElementById('calRangeSelect')?.value || '6m';

            if (county && county !== 'all') params.county = county;
            if (ward && ward !== 'all' && ward !== 'all areas') params.ward = ward;
            if (range) params.time_range = range;

            const res = await window.Api.getMonitoringIntelligence(params);

            // Synchronize active mode selector button
            if (res && res.active_mode) {
                this.activeIntelligenceMode = res.active_mode;
                const selectorGrid = document.getElementById('intelModeSelector');
                if (selectorGrid) {
                    selectorGrid.querySelectorAll('.intel-mode-btn').forEach(b => {
                        if (b.getAttribute('data-mode') === res.active_mode) {
                            b.classList.add('is-active');
                        } else {
                            b.classList.remove('is-active');
                        }
                    });
                }
            }

            // Handle Query Interpretation Banner
            const interpBanner = document.getElementById('intelQueryExplanation');
            const interpText = document.getElementById('intelQueryExplanationText');
            if (interpBanner && interpText) {
                if (res && res.interpreted_query) {
                    interpText.innerHTML = `<i class='bx bx-info-circle'></i> <strong>Interpreted:</strong> ${res.interpreted_query.explanation}`;
                    interpBanner.classList.remove('hidden');
                } else {
                    interpBanner.classList.add('hidden');
                }
            }

            this.renderIntelligenceWorkspace(res);
        } catch (err) {
            console.error('Failed to load monitoring intelligence:', err);
            container.innerHTML = `
                <div class="intel-result-card" style="border-top-color: #ef4444;">
                    <div class="intel-result-badge" style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border-color: rgba(239, 68, 68, 0.25);">
                        <i class='bx bx-error'></i> Error Loading Intelligence
                    </div>
                    <div class="intel-result-finding" style="font-size: 0.92rem; color: #475569;">
                        An error occurred while compiling analytical intelligence from historical records. Please try selecting a different analysis or reloading the view.
                    </div>
                </div>
            `;
        }
    },

    renderIntelligenceWorkspace(data) {
        const container = document.getElementById('intelResultWorkspace');
        if (!container) return;

        if (!data) {
            container.innerHTML = `
                <div class="intel-result-card">
                    <p style="margin: 0; color: #64748b; font-size: 0.85rem;">No monitoring intelligence currently available.</p>
                </div>
            `;
            return;
        }

        // 1. Unsupported Query State
        if (data.status === 'unsupported') {
            const suggestionsHtml = (data.suggestions || []).map(s => `
                <button type="button" class="intel-chip-suggestion dynamic-suggestion" data-prompt="${s.replace(/"/g, '&quot;')}">
                    ${s}
                </button>
            `).join('');

            const topicsHtml = (data.supported_topics || []).map(t => `
                <li style="margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
                    <i class='bx bx-check' style="color: #0070d1; font-size: 1rem;"></i> <span>${t}</span>
                </li>
            `).join('');

            container.innerHTML = `
                <div class="intel-result-card" style="border-top-color: #f59e0b;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                        <span class="intel-result-badge" style="background: rgba(245, 158, 11, 0.1); color: #d97706; border-color: rgba(245, 158, 11, 0.25);">
                            <i class='bx bx-help-circle'></i> Unsupported Query
                        </span>
                        <span style="font-size: 0.72rem; color: #64748b;">${data.query ? `Query: "${data.query}"` : ''}</span>
                    </div>
                    <div class="intel-result-finding" style="font-size: 0.95rem; color: #1e293b;">
                        InfraVision could not map this question to a supported monitoring analysis.
                    </div>
                    <div style="font-size: 0.78rem; color: #475569; background: #fffbeb; border: 1px solid #fef3c7; border-radius: 6px; padding: 0.75rem 1rem;">
                        <p style="margin: 0 0 0.5rem 0; font-weight: 600; color: #92400e;">InfraVision provides controlled, evidence-grounded civil engineering analytics for:</p>
                        <ul style="margin: 0; padding-left: 0.5rem; color: #78350f; list-style-type: none;">
                            ${topicsHtml}
                        </ul>
                    </div>
                    <div style="margin-top: 0.25rem;">
                        <span style="font-size: 0.72rem; font-weight: 700; color: #64748b; display: block; margin-bottom: 0.4rem;">TRY ASKING:</span>
                        <div style="display: flex; flex-wrap: wrap; gap: 0.4rem;">
                            ${suggestionsHtml}
                        </div>
                    </div>
                </div>
            `;

            container.querySelectorAll('.dynamic-suggestion').forEach(chip => {
                chip.addEventListener('click', () => {
                    const prompt = chip.getAttribute('data-prompt');
                    const nlpInput = document.getElementById('intelNlpInput');
                    if (nlpInput) nlpInput.value = prompt;
                    this.activeIntelligenceQuery = prompt;
                    this.loadFocusedIntelligence(null, prompt);
                });
            });
            return;
        }

        // 2. Insufficient Data State
        if (data.status === 'insufficient_data') {
            container.innerHTML = `
                <div class="intel-result-card" style="border-top-color: #64748b;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                        <span class="intel-result-badge" style="background: rgba(100, 116, 139, 0.1); color: #475569; border-color: rgba(100, 116, 139, 0.25);">
                            <i class='bx bx-radar'></i> Data Accumulation • Sparsity Notice
                        </span>
                        <span style="font-size: 0.72rem; color: #64748b; font-weight: 600;">${data.location || 'Selected Location'}</span>
                    </div>
                    <div class="intel-result-finding" style="font-size: 0.95rem; color: #334155;">
                        ${data.message || 'Empirical civil engineering analysis requires additional recorded defect reports in this geographic area.'}
                    </div>
                    <div class="intel-evidence-panel" style="border-left-color: #94a3b8;">
                        <div style="font-weight: 700; color: #1e293b; margin-bottom: 2px;">Evidence & Threshold Status:</div>
                        <div>Threshold Requirement: <strong>${data.evidence_threshold || 'Minimum statistical volume required'}</strong></div>
                        <div>Current Empirical Records: <strong>${data.current_count ?? 0} defect report(s)</strong></div>
                        <div style="font-size: 0.72rem; color: #64748b; margin-top: 4px;">As field engineers log verified inspection casework in this jurisdiction, automated multi-factor correlation models will populate.</div>
                    </div>
                </div>
            `;
            return;
        }

        // 3. Success State
        const stats = data.supporting_stats || data.supporting_statistics || [];
        const statsHtml = stats.map(s => `
            <div class="intel-stat-box">
                <span class="intel-stat-label">${s.label}</span>
                <span class="intel-stat-val">${s.value}</span>
            </div>
        `).join('');

        // Build comparison breakdown view
        let comparisonHtml = '';
        if (data.comparison && Array.isArray(data.comparison.data) && data.comparison.data.length > 0) {
            const comp = data.comparison;
            comparisonHtml = `
                <div class="intel-comparison-box">
                    <div style="font-weight: 700; color: #1e293b; margin-bottom: 0.6rem; font-size: 0.82rem; display: flex; align-items: center; justify-content: space-between;">
                        <span>${comp.title || 'Distribution Breakdown'}</span>
                        <span style="font-size: 0.7rem; color: #64748b; font-weight: 500;">Empirical Breakdown</span>
                    </div>
            `;

            if (comp.type === 'rainfall_thresholds' || comp.type === 'season_breakdown' || comp.type === 'severity_breakdown') {
                comparisonHtml += `<div style="display: flex; flex-direction: column; gap: 0.5rem;">`;
                comp.data.forEach(item => {
                    const label = item.bucket || item.season || item.severity || 'Category';
                    const count = item.count ?? 0;
                    const pct = item.percentage ?? 0;
                    const isHighlight = item.is_dominant || item.is_highest;
                    comparisonHtml += `
                        <div>
                            <div style="display: flex; justify-content: space-between; font-size: 0.74rem; margin-bottom: 2px;">
                                <span style="font-weight: ${isHighlight ? '700' : '500'}; color: ${isHighlight ? '#0070d1' : '#334155'};">
                                    ${label} ${isHighlight ? '★' : ''}
                                </span>
                                <span style="font-weight: 600; color: #1e293b;">${count} report${count === 1 ? '' : 's'} (${pct}%)</span>
                            </div>
                            <div style="height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden;">
                                <div style="height: 100%; width: ${Math.min(100, Math.max(0, pct))}%; background: ${isHighlight ? '#0070d1' : '#94a3b8'}; border-radius: 3px; transition: width 0.3s ease;"></div>
                            </div>
                        </div>
                    `;
                });
                comparisonHtml += `</div>`;
            } else if (comp.type === 'corridor_breakdown') {
                comparisonHtml += `
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.5rem;">
                `;
                comp.data.forEach(c => {
                    comparisonHtml += `
                        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.55rem 0.75rem;">
                            <div style="font-weight: 700; color: #1e293b; font-size: 0.78rem;">${c.corridor}</div>
                            <div style="font-size: 0.72rem; color: #64748b; margin-top: 3px;">
                                <span style="color: #0070d1; font-weight: 600;">${c.count} report${c.count === 1 ? '' : 's'}</span> • Median interval: <strong>${c.median_interval_days ? c.median_interval_days + 'd' : 'N/A'}</strong>
                            </div>
                        </div>
                    `;
                });
                comparisonHtml += `</div>`;
            } else if (comp.type === 'lifecycle_funnel') {
                comparisonHtml += `
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.5rem;">
                `;
                comp.data.forEach(step => {
                    comparisonHtml += `
                        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.55rem 0.75rem; text-align: center;">
                            <div style="font-size: 0.68rem; color: #64748b; font-weight: 600; text-transform: uppercase;">${step.stage}</div>
                            <div style="font-size: 1.15rem; font-weight: 700; color: #0070d1; margin-top: 2px;">${step.count}</div>
                        </div>
                    `;
                });
                comparisonHtml += `</div>`;
            }

            comparisonHtml += `</div>`;
        }

        // Evidence strip
        const ev = data.evidence || {};
        const sourceLabel = ev.weather_source || ev.geospatial_source || ev.climate_source || ev.telemetry_source || ev.lifecycle_source || 'MongoDB verified records';

        // Actions
        const actionsHtml = (data.actions || []).map(act => `
            <button type="button" class="btn-workspace-action"
                    data-action-id="${act.id}"
                    data-corridor="${(act.corridor || '').replace(/"/g, '&quot;')}"
                    data-severity="${act.severity || ''}"
                    data-defect="${act.defect || ''}">
                <i class='bx ${act.icon || 'bx-right-arrow-alt'}'></i> ${act.label}
            </button>
        `).join('');

        container.innerHTML = `
            <div class="intel-result-card">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                    <span class="intel-result-badge">
                        <i class='bx ${data.mode_icon || 'bx-bulb'}'></i> ${data.title}
                    </span>
                    <span style="font-size: 0.72rem; color: #64748b; font-weight: 600;">
                        ${ev.reports_analyzed ?? 0} Reports Analyzed • ${ev.location || 'All Monitored Locations'}
                    </span>
                </div>

                <div class="intel-result-finding">
                    ${data.primary_finding}
                </div>

                <div class="intel-stats-grid">
                    ${statsHtml}
                </div>

                ${comparisonHtml}

                <div class="intel-evidence-panel">
                    <div style="font-weight: 700; color: #1e293b; margin-bottom: 2px;">Evidence Basis & Observation Window:</div>
                    <div>Period: <strong>${ev.period || 'Selected Time Range'}</strong> • Geographical Scope: <strong>${ev.location || 'All Monitored Locations'}</strong></div>
                    <div style="font-size: 0.72rem; color: #64748b; margin-top: 3px;">Data Grounding: ${sourceLabel}</div>
                </div>

                ${data.recommendation ? `
                    <div class="intel-recommendation-box">
                        <i class='bx bx-check-shield' style="font-size: 1.05rem; vertical-align: -2px; margin-right: 4px;"></i>
                        <strong>Engineering Advisory:</strong> ${data.recommendation}
                    </div>
                ` : ''}

                ${actionsHtml ? `
                    <div class="intel-actions-row">
                        ${actionsHtml}
                    </div>
                ` : ''}
            </div>
        `;

        this.wireWorkspaceActions(container);
    },

    wireWorkspaceActions(container) {
        if (!container) return;
        container.querySelectorAll('.btn-workspace-action').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const actionId = btn.getAttribute('data-action-id');
                const corridor = btn.getAttribute('data-corridor');
                const severity = btn.getAttribute('data-severity');
                const defect = btn.getAttribute('data-defect');

                if (actionId === 'show_corridor' && corridor) {
                    if (window.App && typeof window.App.navigateTo === 'function') {
                        window.App.navigateTo('view-map');
                    }
                    setTimeout(() => {
                        if (window.DefectMap && typeof window.DefectMap.focusCorridor === 'function') {
                            window.DefectMap.focusCorridor(corridor);
                        }
                    }, 150);
                } else if (actionId === 'show_map') {
                    if (window.App && typeof window.App.navigateTo === 'function') {
                        window.App.navigateTo('view-map');
                    }
                } else if (actionId === 'filter_queue') {
                    const select = document.getElementById('filterSeveritySelect');
                    if (select) {
                        if (severity) {
                            select.value = severity;
                        } else {
                            select.value = '';
                        }
                        this.loadReportsList();
                        const queueCard = document.querySelector('.queue-card');
                        if (queueCard && typeof queueCard.scrollIntoView === 'function') {
                            queueCard.scrollIntoView({ behavior: 'smooth' });
                        }
                    }
                } else if (actionId === 'toggle_verified_kpi') {
                    const kpiCard = document.getElementById('kpiCardVerified');
                    if (kpiCard) {
                        kpiCard.click();
                        const queueCard = document.querySelector('.queue-card');
                        if (queueCard && typeof queueCard.scrollIntoView === 'function') {
                            queueCard.scrollIntoView({ behavior: 'smooth' });
                        }
                    }
                }
            });
        });
    },

    renderMonitoringInsights(insights) {
        // Preserved for backwards compatibility with existing callers
        this.loadFocusedIntelligence(this.activeIntelligenceMode, this.activeIntelligenceQuery);
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
