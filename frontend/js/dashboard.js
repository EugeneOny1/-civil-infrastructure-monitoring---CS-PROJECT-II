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
    hasUserQueriedIntelligence: false,
    rotatingPhrases: [
        'rainfall-related defect patterns',
        'recurrent corridor distress',
        'seasonal maintenance impacts',
        'critical structural hazards',
        'resolution turnaround performance'
    ],
    rotatingPhraseIndex: 0,
    rotatingIntervalId: null,

    init() {
        this.bindEvents();
        this.loadGeographyHierarchy();
        this.initMonitoringIntelligence();
    },

    async loadGeographyHierarchy() {
        try {
            const countySelect = document.getElementById('trendCountySelect');
            const subCountySelect = document.getElementById('trendSubCountySelect');
            const wardSelect = document.getElementById('trendWardSelect');
            if (!countySelect) return;

            const data = await window.Api.getGeographyHierarchy();
            const counties = Array.isArray(data.counties) ? data.counties : [];

            // Populate all 47 counties
            let countyOptions = '<option value="all" selected>All Counties (Kenya)</option>';
            counties.forEach(c => {
                countyOptions += `<option value="${c.name}">${c.name}</option>`;
            });
            countySelect.innerHTML = countyOptions;

            const onCountyChange = async () => {
                const cVal = countySelect.value;
                if (!subCountySelect || !wardSelect) return;

                if (!cVal || cVal.toLowerCase() === 'all') {
                    subCountySelect.innerHTML = '<option value="all" selected>All Sub-Counties</option>';
                    wardSelect.innerHTML = '<option value="all" selected>All Areas / Wards</option>';
                } else {
                    const cData = await window.Api.getGeographyHierarchy(cVal);
                    const consts = Array.isArray(cData.constituencies) ? cData.constituencies : [];
                    const wards = Array.isArray(cData.wards) ? cData.wards : [];

                    let subOptions = '<option value="all" selected>All Sub-Counties</option>';
                    consts.forEach(cn => {
                        subOptions += `<option value="${cn}">${cn}</option>`;
                    });
                    subCountySelect.innerHTML = subOptions;

                    let wardOptions = '<option value="all" selected>All Areas / Wards</option>';
                    wards.forEach(w => {
                        wardOptions += `<option value="${w}">${w}</option>`;
                    });
                    wardSelect.innerHTML = wardOptions;
                }

                this.loadKpis(cVal, wardSelect ? wardSelect.value : 'all');
                this.loadDegradationChart();
                this.loadCriticalCalendar();
                this.loadReportsList();
                if (this.hasUserQueriedIntelligence) {
                    this.loadFocusedIntelligence(this.activeIntelligenceMode, this.activeIntelligenceQuery);
                }
            };

            const onSubCountyChange = async () => {
                const cVal = countySelect.value;
                const scVal = subCountySelect ? subCountySelect.value : 'all';
                if (wardSelect && cVal && cVal.toLowerCase() !== 'all') {
                    const cData = await window.Api.getGeographyHierarchy(cVal, scVal);
                    const wards = Array.isArray(cData.wards) ? cData.wards : [];
                    let wardOptions = '<option value="all" selected>All Areas / Wards</option>';
                    wards.forEach(w => {
                        wardOptions += `<option value="${w}">${w}</option>`;
                    });
                    wardSelect.innerHTML = wardOptions;
                }
                this.loadKpis(cVal, wardSelect ? wardSelect.value : 'all');
                this.loadDegradationChart();
                this.loadCriticalCalendar();
                this.loadReportsList();
                if (this.hasUserQueriedIntelligence) {
                    this.loadFocusedIntelligence(this.activeIntelligenceMode, this.activeIntelligenceQuery);
                }
            };

            const onWardChange = () => {
                const cVal = countySelect.value;
                const wVal = wardSelect ? wardSelect.value : 'all';
                this.loadKpis(cVal, wVal);
                this.loadDegradationChart();
                this.loadCriticalCalendar();
                this.loadReportsList();
                if (this.hasUserQueriedIntelligence) {
                    this.loadFocusedIntelligence(this.activeIntelligenceMode, this.activeIntelligenceQuery);
                }
            };

            countySelect.addEventListener('change', onCountyChange);
            if (subCountySelect) subCountySelect.addEventListener('change', onSubCountyChange);
            if (wardSelect) wardSelect.addEventListener('change', onWardChange);
        } catch (e) {
            console.error("[Dashboard] Geography load error:", e);
        }
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

        // Section 36: My Lead Cases KPI Filter Toggle
        const kpiVerified = document.getElementById('kpiCardVerified');
        const kpiVerifiedCount = document.getElementById('kpiVerifiedCount');
        const kpiLeadCasesCount = document.getElementById('kpiLeadCasesCount');
        const activeBadge = document.getElementById('kpiVerifiedActiveBadge');

        const toggleLeadFilter = () => {
            const select = document.getElementById('filterSeveritySelect');
            if (!select) return;

            if (this.isVerifiedFilterActive) {
                // Second click: restore prior queue filter
                this.isVerifiedFilterActive = false;
                if (kpiVerified) kpiVerified.classList.remove('kpi-card-active');
                if (activeBadge) activeBadge.classList.add('hidden');
                select.value = this.previousFilterSeverityValue || 'awaiting_verification';
                this.loadReportsList();
            } else {
                // First click: filter queue to My Lead Cases
                this.previousFilterSeverityValue = select.value === 'my_lead_cases' ? 'awaiting_verification' : select.value;
                this.isVerifiedFilterActive = true;
                if (kpiVerified) kpiVerified.classList.add('kpi-card-active');
                if (activeBadge) {
                    activeBadge.classList.remove('hidden');
                    activeBadge.innerHTML = "<i class='bx bx-check'></i> My Cases";
                }
                select.value = 'my_lead_cases';
                this.loadReportsList();
                const queueCard = document.querySelector('.queue-card');
                if (queueCard && typeof queueCard.scrollIntoView === 'function') {
                    queueCard.scrollIntoView({ behavior: 'smooth' });
                }
            }
        };

        if (kpiVerified) kpiVerified.addEventListener('click', toggleLeadFilter);
        if (kpiVerifiedCount) kpiVerifiedCount.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleLeadFilter();
        });
        if (kpiLeadCasesCount) kpiLeadCasesCount.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleLeadFilter();
        });

        if (filterSelect) {
            filterSelect.addEventListener('change', () => {
                if (filterSelect.value === 'my_lead_cases' || filterSelect.value === 'Verified') {
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

        if (calRangeSelect) calRangeSelect.addEventListener('change', () => {
            this.loadCriticalCalendar();
            if (this.hasUserQueriedIntelligence) {
                this.loadFocusedIntelligence(this.activeIntelligenceMode, this.activeIntelligenceQuery);
            }
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
        const results = await Promise.allSettled([
            this.loadKpis(),
            this.loadDegradationChart(),
            this.loadCriticalCalendar(),
            this.loadReportsList()
        ]);
        results.forEach((res, idx) => {
            if (res.status === 'rejected') {
                console.error(`[Dashboard] Component ${idx} error:`, res.reason);
            }
        });
        if (this.hasUserQueriedIntelligence) {
            try {
                await this.loadFocusedIntelligence(this.activeIntelligenceMode, this.activeIntelligenceQuery);
            } catch (err) {
                console.error("[Dashboard] Focused intelligence error:", err);
            }
        }
    },

    async loadKpis(countyParam, wardParam) {
        try {
            const county = countyParam !== undefined ? countyParam : (document.getElementById('trendCountySelect')?.value || 'all');
            const ward = wardParam !== undefined ? wardParam : (document.getElementById('trendWardSelect')?.value || 'all');

            const queueEl = document.getElementById('kpiActiveQueue');
            const verifiedEl = document.getElementById('kpiVerifiedCount');
            const leadEl = document.getElementById('kpiLeadCasesCount');
            const modelEl = document.getElementById('kpiModelVersion');
            const critEl = document.getElementById('kpiCriticalHazards');

            const isGeoFiltered = (county && county !== 'all') || (ward && ward !== 'all' && ward !== 'All Areas');

            if (!isGeoFiltered) {
                const summary = await window.Api.getSummary();
                if (queueEl) queueEl.textContent = summary.active_defect_queue ?? 0;
                if (leadEl) leadEl.textContent = summary.my_lead_cases ?? 0;
                if (verifiedEl) verifiedEl.textContent = summary.verified_inspections ?? 0;
                if (modelEl) modelEl.textContent = summary.model_version || 'SSD-MobileNetV2';
                if (critEl) critEl.textContent = summary.critical_received_count ?? summary.critical_hazards ?? 0;
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

                const receivedReports = reports.filter(r => (r.status || '').toLowerCase() === 'received');
                const activeQueue = receivedReports.length;
                const verified = reports.filter(r => (r.status || '') === 'Verified').length;
                const critical = receivedReports.filter(r => {
                    const sev = (r.assessment?.relative_severity || r.metadata?.relative_severity || r.severity || '').toLowerCase();
                    return sev === 'critical' || sev === 'high';
                }).length;

                const curUser = window.App?.currentUser;
                const curUserId = String(curUser?._id || curUser?.user_id || '');
                const leadCount = reports.filter(r => {
                    const st = (r.status || '').toLowerCase();
                    if (st === 'resolved') return false;
                    const leadId = String(r.metadata?.current_lead_engineer?.user_id || r.metadata?.assigned_engineer_id || '');
                    return leadId && leadId === curUserId;
                }).length;

                if (queueEl) queueEl.textContent = activeQueue;
                if (leadEl) leadEl.textContent = leadCount;
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
        // Architectural specification note: cubicInterpolationMode: 'monotone' and tension: 0.35 superseded for sharp point-to-point empirical rendering
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
            const stage = document.getElementById('criticalCalendarCarouselStage');
            const currentMonthLabel = document.getElementById('calCurrentMonthLabel');
            const subTitle = document.getElementById('calSubtitle');
            if (currentMonthLabel) currentMonthLabel.textContent = 'Unavailable';
            if (subTitle) subTitle.textContent = 'Calendar data temporarily unavailable.';
            if (stage) stage.innerHTML = '<div style="padding:2rem; text-align:center; color:#94a3b8; font-size:0.85rem; width:100%;">Calendar data could not be retrieved.</div>';
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
                    } else if (cnt === 1) {
                        const defectType = Object.keys(breakdown)[0] || 'Critical Defect';
                        html += `
                            <div style="font-weight:700; color:#ef4444; margin-bottom:3px; font-size:0.78rem;">1 Critical Report</div>
                            <div style="color:#cbd5e1; font-size:0.75rem;">${defectType}</div>
                        `;
                    } else {
                        html += `<div style="font-weight:700; color:#ef4444; margin-bottom:4px; font-size:0.78rem;">${cnt} Critical Reports</div>`;
                        const breakdownEntries = Object.entries(breakdown);
                        if (breakdownEntries.length > 0) {
                            const lines = breakdownEntries.map(([cls, c]) => `<span>${c} ${cls}${c > 1 ? 's' : ''}</span>`);
                            html += `<div style="color:#cbd5e1; font-size:0.74rem; display:flex; flex-direction:column; gap:2px;">${lines.join('')}</div>`;
                        }
                    }

                    if (rainfall !== null && rainfall !== '' && rainfall !== undefined) {
                        html += `<div style="color:#38bdf8; font-size:0.72rem; margin-top:5px; border-top:1px solid #334155; padding-top:4px;"><i class='bx bx-cloud-rain'></i> Preceding 7-Day Rainfall: <strong>${rainfall} mm</strong></div>`;
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

        // Redundant lower summary container removed per architectural specification (Section 11 & 47)
        if (summaryStrip) {
            summaryStrip.innerHTML = '';
        }
    },

    renderRecurrenceInsights(insights) {
        const container = document.getElementById('dashboardRecurrenceInsights');
        if (!container) return;
        // Keep container clean to eliminate duplicate card slab under calendar
        container.innerHTML = '';
    },

    initRotatingPhrases() {
        if (this.rotatingIntervalId) {
            clearInterval(this.rotatingIntervalId);
            this.rotatingIntervalId = null;
        }
        const textEl = document.getElementById('intelRotatingText');
        if (!textEl) return;

        const prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        this.rotatingIntervalId = setInterval(() => {
            this.rotatingPhraseIndex = (this.rotatingPhraseIndex + 1) % this.rotatingPhrases.length;
            const nextText = this.rotatingPhrases[this.rotatingPhraseIndex];

            if (prefersReducedMotion) {
                textEl.textContent = nextText;
                return;
            }

            textEl.classList.add('fade-out');
            setTimeout(() => {
                textEl.textContent = nextText;
                textEl.classList.remove('fade-out');
                textEl.classList.add('fade-in');
                setTimeout(() => {
                    textEl.classList.remove('fade-in');
                }, 300);
            }, 260);
        }, 3800);
    },

    initMonitoringIntelligence() {
        this.initRotatingPhrases();

        // 1. Embedded category selector pill (ChatGPT Search pill style)
        const catSelect = document.getElementById('intelCategorySelect');
        if (catSelect) {
            catSelect.addEventListener('change', () => {
                const val = catSelect.value;
                if (val && val !== 'auto') {
                    this.activeIntelligenceMode = val;
                }
            });
        }

        // 2. Mode Selector Grid (legacy / backwards compatibility)
        const selectorGrid = document.getElementById('intelModeSelector');
        if (selectorGrid) {
            selectorGrid.querySelectorAll('.intel-mode-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const mode = btn.getAttribute('data-mode');
                    if (!mode) return;
                    this.hasUserQueriedIntelligence = true;
                    this.activeIntelligenceMode = mode;
                    this.activeIntelligenceQuery = '';

                    selectorGrid.querySelectorAll('.intel-mode-btn').forEach(b => b.classList.remove('is-active'));
                    btn.classList.add('is-active');

                    if (catSelect) catSelect.value = mode;

                    const interpBanner = document.getElementById('intelQueryExplanation');
                    if (interpBanner) interpBanner.classList.add('hidden');
                    const nlpInput = document.getElementById('intelNlpInput');
                    if (nlpInput) nlpInput.value = '';

                    this.loadFocusedIntelligence(this.activeIntelligenceMode, '');
                });
            });
        }

        // 3. Capsule Form submission
        const nlpForm = document.getElementById('intelNlpForm');
        if (nlpForm) {
            nlpForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const nlpInput = document.getElementById('intelNlpInput');
                const query = (nlpInput?.value || '').trim();
                const selectedCategory = catSelect?.value;
                const modeToSend = (selectedCategory && selectedCategory !== 'auto') ? selectedCategory : null;

                if (!query && !modeToSend) return;

                this.hasUserQueriedIntelligence = true;
                this.activeIntelligenceQuery = query;
                if (modeToSend) {
                    this.activeIntelligenceMode = modeToSend;
                }
                this.loadFocusedIntelligence(modeToSend, query);
            });
        }

        // 4. Compact suggestion chips: populates composer and selects appropriate category
        const suggestionsStrip = document.getElementById('intelNlpSuggestions');
        if (suggestionsStrip) {
            suggestionsStrip.querySelectorAll('.intel-chip-suggestion').forEach(chip => {
                chip.addEventListener('click', () => {
                    const prompt = chip.getAttribute('data-prompt');
                    const cat = chip.getAttribute('data-category');
                    const nlpInput = document.getElementById('intelNlpInput');
                    if (prompt && nlpInput) {
                        nlpInput.value = prompt;
                        nlpInput.focus();
                    }
                    if (cat && catSelect) {
                        catSelect.value = cat;
                        this.activeIntelligenceMode = cat;
                    }
                });
            });
        }

        // 5. Clear interpretation banner
        const clearBtn = document.getElementById('btnClearQueryInterpretation');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                this.activeIntelligenceQuery = '';
                const nlpInput = document.getElementById('intelNlpInput');
                if (nlpInput) nlpInput.value = '';
                const interpBanner = document.getElementById('intelQueryExplanation');
                if (interpBanner) interpBanner.classList.add('hidden');
                if (this.hasUserQueriedIntelligence) {
                    this.loadFocusedIntelligence(this.activeIntelligenceMode, '');
                }
            });
        }
    },

    async loadFocusedIntelligence(mode = null, query = null) {
        const container = document.getElementById('intelResultWorkspace');
        if (!container) return;

        // Render sleek loading state
        container.innerHTML = `
            <div style="padding: 2.5rem 1rem; text-align: center; color: #64748b; font-size: 0.85rem;">
                <i class='bx bx-loader-alt bx-spin' style="font-size: 1.8rem; color: #0070d1; display: block; margin: 0 auto 0.65rem auto;"></i>
                <span style="font-weight: 600; color: #1e293b;">Computing Civil Infrastructure Intelligence</span>
                <p style="font-size: 0.76rem; color: #64748b; margin-top: 4px;">Evaluating verified records &amp; telemetry correlations...</p>
            </div>
        `;

        try {
            const params = {};
            if (query && query.trim()) {
                params.query = query.trim();
            }
            if (mode && mode !== 'auto') {
                params.mode = mode;
            } else if (!query) {
                params.mode = this.activeIntelligenceMode || 'rainfall_defect_pattern';
            }

            const county = document.getElementById('trendCountySelect')?.value || 'all';
            const ward = document.getElementById('trendWardSelect')?.value || 'all';
            const range = document.getElementById('calRangeSelect')?.value || '6m';

            if (county && county !== 'all') params.county = county;
            if (ward && ward !== 'all' && ward !== 'all areas') params.ward = ward;
            if (range) params.time_range = range;

            const res = await window.Api.getMonitoringIntelligence(params);

            // Synchronize active mode and category dropdown
            if (res && res.active_mode) {
                this.activeIntelligenceMode = res.active_mode;
                const catSelect = document.getElementById('intelCategorySelect');
                if (catSelect && catSelect.value === 'auto') {
                    // keep auto or reflect
                } else if (catSelect && res.active_mode) {
                    catSelect.value = res.active_mode;
                }

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
                <div class="intel-empty-state" style="padding: 2.25rem 1rem; text-align: center; color: #64748b; background: #f8fafc; border: 1px dashed #e2e8f0; border-radius: 8px;">
                    <i class='bx bx-brain' style="font-size: 1.8rem; color: #0070d1; display: block; margin-bottom: 0.35rem;"></i>
                    <span style="font-size: 0.92rem; font-weight: 600; color: #1e293b;">What would you like to monitor?</span>
                    <p style="font-size: 0.78rem; color: #64748b; margin: 0.25rem 0 0 0;">Ask a question or select a focus above to analyze verified defect patterns.</p>
                </div>
            `;
            return;
        }

        const escapeHtml = (str) => {
            if (!str) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        };

        const userQuestion = data.user_query || this.activeIntelligenceQuery;
        const userBubbleHtml = userQuestion ? `
            <div class="intel-user-bubble">
                <div class="intel-user-meta"><i class='bx bx-user-pin'></i> Civil Engineer</div>
                <div class="intel-user-text">${escapeHtml(userQuestion)}</div>
            </div>
        ` : '';

        // 1. Prompt Injection Refusal State
        if (data.status === 'injection_refused') {
            const topicsHtml = (data.supported_topics || []).map(t => `
                <li style="margin-bottom: 3px; display: flex; align-items: center; gap: 5px;">
                    <i class='bx bx-check' style="color: #0070d1; font-size: 0.95rem;"></i> <span>${escapeHtml(t)}</span>
                </li>
            `).join('');

            container.innerHTML = `
                ${userBubbleHtml}
                <div class="intel-response-card" style="border-left-color: #ef4444;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                        <span class="intel-result-badge" style="background: rgba(239, 68, 68, 0.1); color: #dc2626; border-color: rgba(239, 68, 68, 0.25);">
                            <i class='bx bx-shield-x'></i> Instruction Override Refused
                        </span>
                        <span class="intel-grounding-badge" style="color: #dc2626; background: #fef2f2; border-color: #fecaca;">
                            <i class='bx bx-lock-alt'></i> Policy Protected
                        </span>
                    </div>
                    <div class="intel-prose-body">
                        <p style="color: #991b1b; font-weight: 500;">
                            ${escapeHtml(data.message)}
                        </p>
                    </div>
                    <div style="margin-top: 0.65rem; font-size: 0.78rem; color: #475569; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.65rem 0.85rem;">
                        <span style="font-weight: 600; color: #1e293b; display: block; margin-bottom: 4px;">InfraVision Monitoring Intelligence exclusively analyzes:</span>
                        <ul style="margin: 0; padding-left: 0.5rem; color: #64748b; list-style-type: none;">
                            ${topicsHtml}
                        </ul>
                    </div>
                </div>
            `;
            container.scrollTop = container.scrollHeight;
            return;
        }

        // 2. Unsupported Query State
        if (data.status === 'unsupported') {
            const suggestionsHtml = (data.suggestions || []).map(s => `
                <button type="button" class="intel-chip-suggestion dynamic-suggestion" data-prompt="${escapeHtml(s)}">
                    ${escapeHtml(s)}
                </button>
            `).join('');

            const topicsHtml = (data.supported_topics || []).map(t => `
                <li style="margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
                    <i class='bx bx-check' style="color: #0070d1; font-size: 1rem;"></i> <span>${escapeHtml(t)}</span>
                </li>
            `).join('');

            container.innerHTML = `
                ${userBubbleHtml}
                <div class="intel-response-card" style="border-left-color: #f59e0b;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                        <span class="intel-result-badge" style="background: rgba(245, 158, 11, 0.1); color: #d97706; border-color: rgba(245, 158, 11, 0.25);">
                            <i class='bx bx-help-circle'></i> Unsupported Query
                        </span>
                    </div>
                    <div class="intel-prose-body">
                        <p>${escapeHtml(data.message)}</p>
                    </div>
                    <div style="font-size: 0.78rem; color: #475569; background: #fffbeb; border: 1px solid #fef3c7; border-radius: 6px; padding: 0.75rem 1rem; margin-top: 0.6rem;">
                        <p style="margin: 0 0 0.5rem 0; font-weight: 600; color: #92400e;">InfraVision provides controlled, evidence-grounded civil engineering analytics for:</p>
                        <ul style="margin: 0; padding-left: 0.5rem; color: #78350f; list-style-type: none;">
                            ${topicsHtml}
                        </ul>
                    </div>
                    <div style="margin-top: 0.65rem;">
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
            container.scrollTop = container.scrollHeight;
            return;
        }

        // 3. Insufficient Data State
        if (data.status === 'insufficient_data') {
            const rawProse = data.prose_summary || data.explanation || data.primary_finding || 'Empirical civil engineering analysis requires additional recorded defect reports in this geographic area.';
            const paragraphsHtml = rawProse.split('\n\n').map(p => `<p>${escapeHtml(p)}</p>`).join('');

            container.innerHTML = `
                ${userBubbleHtml}
                <div class="intel-response-card" style="border-left-color: #64748b;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                        <span class="intel-result-badge" style="background: rgba(100, 116, 139, 0.1); color: #475569; border-color: rgba(100, 116, 139, 0.25);">
                            <i class='bx bx-radar'></i> Data Accumulation • Sparsity Notice
                        </span>
                        <span style="font-size: 0.72rem; color: #64748b; font-weight: 600;">${escapeHtml(data.location || 'Selected Location')}</span>
                    </div>
                    <div class="intel-prose-body">
                        ${paragraphsHtml}
                    </div>
                    <div class="intel-compact-evidence-footer">
                        <span><i class='bx bx-info-circle'></i> Requirement: <strong>${escapeHtml(data.evidence_threshold || '≥ 3 Reports')}</strong> • Current Empirical: <strong>${data.current_count ?? 0} report(s)</strong></span>
                    </div>
                </div>
            `;
            container.scrollTop = container.scrollHeight;
            return;
        }

        // 4. Success State - Cohesive 1-2 Paragraph Civil Engineering Analysis with Collapsible Evidence
        const rawProse = data.prose_summary || data.primary_finding || '';
        const paragraphsHtml = rawProse.split('\n\n').map(p => `<p>${escapeHtml(p)}</p>`).join('');

        const stats = data.supporting_stats || data.supporting_statistics || [];
        const statsHtml = stats.map(s => `
            <div class="intel-stat-box">
                <span class="intel-stat-label">${escapeHtml(s.label)}</span>
                <span class="intel-stat-val">${escapeHtml(s.value)}</span>
            </div>
        `).join('');

        // Build comparison breakdown view
        let comparisonHtml = '';
        if (data.comparison && Array.isArray(data.comparison.data) && data.comparison.data.length > 0) {
            const comp = data.comparison;
            comparisonHtml = `
                <div class="intel-comparison-box">
                    <div style="font-weight: 700; color: #1e293b; margin-bottom: 0.6rem; font-size: 0.82rem; display: flex; align-items: center; justify-content: space-between;">
                        <span>${escapeHtml(comp.title || 'Distribution Breakdown')}</span>
                        <span style="font-size: 0.7rem; color: #64748b; font-weight: 500;">Empirical Breakdown</span>
                    </div>
            `;

            if (comp.type === 'rainfall_windows' || comp.type === 'rainfall_thresholds' || comp.type === 'season_breakdown' || comp.type === 'seasonal_distribution' || comp.type === 'severity_breakdown') {
                comparisonHtml += `<div style="display: flex; flex-direction: column; gap: 0.5rem;">`;
                comp.data.forEach(item => {
                    const label = item.window || item.season || item.bucket || item.severity || 'Category';
                    const val = item.rainfall || item.share || (item.count !== undefined ? `${item.count} reports` : '');
                    comparisonHtml += `
                        <div style="display: flex; justify-content: space-between; font-size: 0.75rem; border-bottom: 1px dashed #f1f5f9; padding-bottom: 3px;">
                            <span style="font-weight: 600; color: #334155;">${escapeHtml(label)}</span>
                            <span style="font-weight: 700; color: #0070d1;">${escapeHtml(String(val))}</span>
                        </div>
                    `;
                });
                comparisonHtml += `</div>`;
            } else if (comp.type === 'corridor_breakdown') {
                comparisonHtml += `
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0.5rem;">
                `;
                comp.data.forEach(c => {
                    comparisonHtml += `
                        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.55rem 0.75rem;">
                            <div style="font-weight: 700; color: #1e293b; font-size: 0.78rem;">${escapeHtml(c.defect_class || c.corridor)}</div>
                            <div style="font-size: 0.72rem; color: #64748b; margin-top: 3px;">
                                <span style="color: #0070d1; font-weight: 600;">${c.count} report${c.count === 1 ? '' : 's'}</span> • ${escapeHtml(c.share || '')}
                            </div>
                        </div>
                    `;
                });
                comparisonHtml += `</div>`;
            } else if (comp.type === 'lifecycle_funnel' || comp.type === 'status_distribution') {
                comparisonHtml += `
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.5rem;">
                `;
                comp.data.forEach(step => {
                    comparisonHtml += `
                        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.55rem 0.75rem; text-align: center;">
                            <div style="font-size: 0.68rem; color: #64748b; font-weight: 600; text-transform: uppercase;">${escapeHtml(step.stage || step.status)}</div>
                            <div style="font-size: 1.15rem; font-weight: 700; color: #0070d1; margin-top: 2px;">${step.count}</div>
                        </div>
                    `;
                });
                comparisonHtml += `</div>`;
            }

            comparisonHtml += `</div>`;
        }

        const ev = data.evidence || {};
        const sourceLabel = ev.weather_source || ev.geospatial_source || ev.climate_source || ev.lifecycle_source || 'MongoDB verified records';

        // Limit to at most 2 primary actions (View Reports, Show on Map)
        const primaryActions = (data.actions || []).slice(0, 2);
        const actionsHtml = primaryActions.map(act => `
            <button type="button" class="btn-workspace-action"
                    data-action-id="${act.id}"
                    data-corridor="${escapeHtml(act.corridor || '')}"
                    data-severity="${escapeHtml(act.severity || '')}"
                    data-defect="${escapeHtml(act.defect || '')}">
                <i class='bx ${act.icon || 'bx-right-arrow-alt'}'></i> ${escapeHtml(act.label)}
            </button>
        `).join('');

        const retrievedOrg = (data.retrieved_sources && data.retrieved_sources.length > 0)
            ? data.retrieved_sources[0].source_org.split('(')[0].trim()
            : null;
        const retrievedCitation = (data.retrieved_sources && data.retrieved_sources.length > 0)
            ? data.retrieved_sources[0].citation
            : null;

        container.innerHTML = `
            ${userBubbleHtml}
            <div class="intel-response-card">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                    <div style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                        <span class="intel-result-badge">
                            <i class='bx ${data.mode_icon || 'bx-bulb'}'></i> ${escapeHtml(data.title || 'Analysis')}
                        </span>
                        ${data.active_mode === 'rainfall_defect_pattern' ? `
                            <span style="display: inline-flex; align-items: center; gap: 4px; font-size: 0.72rem; color: #0284c7; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 9999px; padding: 2px 8px; font-weight: 600;">
                                <i class='bx bx-cloud-rain rain-pulse-icon'></i> Precipitation Analyzed
                            </span>
                        ` : ''}
                        ${retrievedOrg ? `
                            <span class="intel-grounding-badge" title="${escapeHtml(retrievedCitation || '')}">
                                <i class='bx bx-shield-quarter'></i> ${escapeHtml(retrievedOrg)} Grounded
                            </span>
                        ` : ''}
                    </div>
                    <span style="font-size: 0.72rem; color: #64748b; font-weight: 600;">
                        ${ev.reports_analyzed ?? 0} Reports Analyzed • ${escapeHtml(ev.location || 'All Monitored Locations')}
                    </span>
                </div>

                <!-- 1-2 Cohesive Professional Analytical Paragraphs -->
                <div class="intel-prose-body">
                    ${paragraphsHtml}
                </div>

                <!-- Compact Evidence Footer Strip -->
                <div class="intel-compact-evidence-footer">
                    <span>
                        <i class='bx bx-data'></i> ${ev.reports_analyzed ?? 0} reports · ${escapeHtml(ev.period || 'Last 6M')} · ${escapeHtml(sourceLabel)}
                    </span>
                    <button type="button" class="btn-text-subtle" id="btnToggleIntelEvidence"
                        style="font-size: 0.76rem; color: #0070d1; background: none; border: none; cursor: pointer; padding: 0; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;">
                        <i class='bx bx-chevron-down' id="intelEvidenceChevron"></i>
                        <span id="intelEvidenceToggleText">View evidence &amp; breakdown</span>
                    </button>
                </div>

                <!-- Collapsible Evidence & Breakdown Drawer -->
                <div id="intelCollapsibleEvidence" class="hidden" style="display: none; margin-top: 0.65rem;">
                    ${comparisonHtml}

                    <div class="intel-stats-grid" style="margin-top: 0.6rem;">
                        ${statsHtml}
                    </div>

                    <div class="intel-evidence-panel" style="margin-top: 0.6rem;">
                        <div style="font-weight: 700; color: #1e293b; margin-bottom: 2px;">Evidence Basis &amp; Observation Window:</div>
                        <div>Period: <strong>${escapeHtml(ev.period || 'Selected Time Range')}</strong> • Scope: <strong>${escapeHtml(ev.location || 'All Monitored Locations')}</strong></div>
                        <div style="font-size: 0.72rem; color: #64748b; margin-top: 3px;">Data Grounding: ${escapeHtml(sourceLabel)}</div>
                        ${retrievedCitation ? `
                            <div style="font-size: 0.72rem; color: #047857; margin-top: 3px;">
                                Authoritative Reference: <strong>${escapeHtml(data.retrieved_sources[0].source_title)}</strong> (${escapeHtml(retrievedCitation)})
                            </div>
                        ` : ''}
                    </div>

                    ${data.recommendation ? `
                        <div class="intel-recommendation-box" style="margin-top: 0.5rem;">
                            <i class='bx bx-check-shield' style="font-size: 1.05rem; vertical-align: -2px; margin-right: 4px;"></i>
                            <strong>Engineering Advisory:</strong> ${escapeHtml(data.recommendation)}
                        </div>
                    ` : ''}
                </div>

                <!-- Maximum 2 Direct Action Buttons -->
                ${actionsHtml ? `
                    <div class="intel-actions-row" style="margin-top: 0.85rem;">
                        ${actionsHtml}
                    </div>
                ` : ''}
            </div>
        `;

        // Wire progressive disclosure toggle
        const btnToggle = container.querySelector('#btnToggleIntelEvidence');
        const collPanel = container.querySelector('#intelCollapsibleEvidence');
        const chevron = container.querySelector('#intelEvidenceChevron');
        const toggleText = container.querySelector('#intelEvidenceToggleText');
        if (btnToggle && collPanel) {
            btnToggle.addEventListener('click', () => {
                const isHidden = collPanel.style.display === 'none';
                collPanel.style.display = isHidden ? 'block' : 'none';
                if (chevron) chevron.className = isHidden ? 'bx bx-chevron-up' : 'bx bx-chevron-down';
                if (toggleText) toggleText.textContent = isHidden ? 'Hide evidence & breakdown' : 'View evidence & breakdown';
            });
        }

        this.wireWorkspaceActions(container);
        container.scrollTop = container.scrollHeight;
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

        const filterVal = document.getElementById('filterSeveritySelect')?.value || 'awaiting_verification';
        const countyVal = document.getElementById('trendCountySelect')?.value || 'all';
        const wardVal = document.getElementById('trendWardSelect')?.value || 'all';

        try {
            const data = await window.Api.getReports({ exclude_status: 'none' });
            let reports = Array.isArray(data.reports) ? data.reports : [];
            const curUser = window.App?.currentUser;
            const curUserId = String(curUser?._id || curUser?.user_id || '');

            if (filterVal === 'awaiting_verification' || !filterVal) {
                // Operational Default: Received reports awaiting initial engineer verification
                reports = reports.filter(r => (r.status || '').toLowerCase() === 'received');
            } else if (filterVal === 'my_lead_cases') {
                // Cases where logged-in engineer is assigned lead, unresolved
                reports = reports.filter(r => {
                    const st = (r.status || '').toLowerCase();
                    if (st === 'resolved') return false;
                    const leadId = String(r.metadata?.current_lead_engineer?.user_id || r.metadata?.assigned_engineer_id || r.assigned_engineer_id || '');
                    return leadId && leadId === curUserId;
                });
            } else if (filterVal === 'all_unresolved') {
                reports = reports.filter(r => (r.status || '').toLowerCase() !== 'resolved');
            } else if (filterVal === 'Verified') {
                reports = reports.filter(r => (r.status || '') === 'Verified');
            } else if (filterVal === 'Critical') {
                reports = reports.filter(r => {
                    const sev = (r.assessment?.relative_severity || r.metadata?.relative_severity || r.severity || '').toLowerCase();
                    return sev === 'critical' || sev === 'high';
                });
            } else if (filterVal === 'Resolved') {
                reports = reports.filter(r => (r.status || '').toLowerCase() === 'resolved');
            } else if (filterVal === 'Flagged') {
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

            // Prioritization: Critical -> Medium -> Low, then oldest submitted first
            const SEV_RANKS = { 'critical': 3, 'high': 3, 'moderate': 2, 'medium': 2, 'low': 1 };
            reports.sort((a, b) => {
                const sevA = (a.assessment?.relative_severity || a.metadata?.relative_severity || a.severity || 'low').toLowerCase();
                const sevB = (b.assessment?.relative_severity || b.metadata?.relative_severity || b.severity || 'low').toLowerCase();
                const rankA = SEV_RANKS[sevA] || 1;
                const rankB = SEV_RANKS[sevB] || 1;
                if (rankB !== rankA) {
                    return rankB - rankA;
                }
                const dateA = new Date(a.date_submitted || a.created_at || 0).getTime();
                const dateB = new Date(b.date_submitted || b.created_at || 0).getTime();
                return dateA - dateB;
            });

            if (reports.length === 0) {
                queueContainer.innerHTML = `
                    <div class="queue-empty-state" style="padding: 2.5rem 1.5rem; text-align: center; color: #64748b; background: rgba(15, 23, 42, 0.03); border: 1px dashed var(--border-color); border-radius: 8px;">
                        <i class='bx bx-folder-open' style="font-size: 2rem; color: #94a3b8; margin-bottom: 0.5rem; display: block;"></i>
                        <p style="font-weight: 500; margin: 0; font-size: 0.88rem;">No reports match the selected filters.</p>
                    </div>
                `;
                return;
            }

            const formatRelativeAge = (dateStr) => {
                if (!dateStr) return '';
                const dt = new Date(dateStr);
                const now = new Date();
                const diffMs = now - dt;
                if (diffMs < 0) return 'Just now';
                const diffMins = Math.floor(diffMs / (60 * 1000));
                if (diffMins < 60) return `Submitted ${diffMins}m ago`;
                const diffHours = Math.floor(diffMins / 60);
                if (diffHours < 24) return `Submitted ${diffHours}h ago`;
                const diffDays = Math.floor(diffHours / 24);
                if (diffDays < 30) return `Submitted ${diffDays}d ago`;
                return `Submitted ${dt.toLocaleDateString('en-KE', { dateStyle: 'medium' })}`;
            };

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
                const dateStr = r.date_submitted || r.created_at;
                const ageStr = formatRelativeAge(dateStr);

                let actionBtnLabel = 'Review & Sign Off';
                if (status === 'Received') {
                    actionBtnLabel = 'Verify Defect';
                } else if (status === 'Verified') {
                    actionBtnLabel = 'Start Inspection';
                } else if (status === 'Under Review') {
                    actionBtnLabel = 'Review & Sign Off';
                } else if (status === 'Resolved') {
                    actionBtnLabel = 'View Case';
                }

                return `
                    <div class="queue-item-card ${isFlagged ? 'is-flagged' : ''}" data-report-id="${r.report_id || r._id}">
                        <div class="queue-item-info">
                            <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                                <span class="queue-item-title">${location}</span>
                                <span class="status-chip ${statusSlug}">${status}</span>
                                ${ageStr ? `<span class="queue-age-pill" style="font-size: 0.72rem; color: #64748b; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; display: inline-flex; align-items: center; gap: 3px;"><i class='bx bx-time'></i> ${ageStr}</span>` : ''}
                                ${isFlagged ? `<span class="badge-tag flagged"><i class='bx bx-error'></i> Unusual Pairing</span>` : ''}
                            </div>
                            <span class="queue-item-meta">${assetType} • ${defectClass} • ${frameId}</span>
                            ${isFlagged && r.metadata?.advisory_notes ? `<span style="font-size: 0.72rem; color: #b45309;">${r.metadata.advisory_notes}</span>` : ''}
                        </div>
                        <div class="queue-item-actions">
                            <span class="severity-pill ${severity.toLowerCase()}">${severity.toUpperCase()}</span>
                            <button type="button" class="btn-review-item btn-open-review" data-report-id="${r.report_id || r._id}">
                                ${actionBtnLabel}
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
