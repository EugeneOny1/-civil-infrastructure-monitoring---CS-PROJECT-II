/**
 * Review Module - AI Defect Assessment & Professional Engineer Review Terminal (Figure 4.8)
 *
 * Responsibilities:
 * - Detailed professional casework review of individual infrastructure defect reports.
 * - Real-time case searching and filtering across ID, location, defect, status, severity, and asset type.
 * - Deep-linked casework loading from Monitoring Dashboard ("Review & Sign Off").
 * - Clean empty states (eliminates fake #REP-0000 placeholders).
 * - Multi-detection bounding box rendering with label collision prevention.
 * - Canonical lifecycle management: Received -> Under Review -> Verified -> Resolved.
 * - Professional Engineer sign-off (Confirm AI Assessment vs Override Assessment with mandatory review notes).
 */

const Review = {
    currentReport: null,
    currentAssessment: null,
    caseworkReports: [],
    targetReportId: null,
    activeImageIndex: 0,
    activeReportData: null,

    init() {
        this.bindEvents();
    },

    bindEvents() {
        const signOffBtn = document.getElementById('btnSubmitSignOff');
        if (signOffBtn) {
            signOffBtn.addEventListener('click', () => this.submitProfessionalValidation());
        }

        const decisionRadios = document.querySelectorAll('input[name="reviewDecision"]');
        decisionRadios.forEach(radio => {
            radio.addEventListener('change', (e) => {
                const overrideFields = document.getElementById('overrideFields');
                if (e.target.value === 'Overridden') {
                    if (overrideFields) overrideFields.classList.remove('hidden');
                } else {
                    if (overrideFields) overrideFields.classList.add('hidden');
                }
            });
        });

        const reportSelect = document.getElementById('reviewReportSelect');
        if (reportSelect) {
            reportSelect.addEventListener('change', (e) => {
                if (e.target.value) {
                    this.loadReportForReview(e.target.value);
                } else {
                    this.renderEmptyCaseworkState();
                }
            });
        }

        const searchInput = document.getElementById('reviewSearchInput');
        const filterStatus = document.getElementById('reviewFilterStatus');

        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.filterCasework(e.target.value, filterStatus ? filterStatus.value : '');
            });
        }

        if (filterStatus) {
            filterStatus.addEventListener('change', (e) => {
                this.filterCasework(searchInput ? searchInput.value : '', e.target.value);
            });
        }

        const refreshCaseworkBtn = document.getElementById('btnRefreshCasework');
        if (refreshCaseworkBtn) {
            refreshCaseworkBtn.addEventListener('click', () => {
                this.loadCaseworkList();
                window.App.showToast("Refreshed defect casework queue.");
            });
        }

        // Direct Lifecycle Controls
        const btnUnderReview = document.getElementById('btnMoveUnderReview');
        const btnVerified = document.getElementById('btnMarkVerified');
        const btnResolved = document.getElementById('btnMarkResolved');

        if (btnUnderReview) {
            btnUnderReview.addEventListener('click', () => this.handleLifecycleTransition('Under Review', 'Inspection initiated by certified engineer.'));
        }
        if (btnVerified) {
            btnVerified.addEventListener('click', () => this.handleLifecycleTransition('Verified', 'Engineering defect verification and severity confirmation completed.'));
        }
        if (btnResolved) {
            btnResolved.addEventListener('click', () => this.handleLifecycleTransition('Resolved', 'Infrastructure defect remediation and road maintenance confirmed resolved.'));
        }
    },

    async loadCaseworkList(preselectReportId = null) {
        const reportSelect = document.getElementById('reviewReportSelect');
        if (!reportSelect) return;

        try {
            reportSelect.innerHTML = `<option value="">Loading defect casework...</option>`;
            const data = await window.Api.getReports({ limit: 100 });
            this.caseworkReports = data.reports || [];

            if (this.caseworkReports.length === 0) {
                reportSelect.innerHTML = `<option value="">No defect casework available</option>`;
                this.renderEmptyCaseworkState("No infrastructure reports exist yet in the database.");
                return;
            }

            // Populate select dropdown with real report context
            this.populateReportSelectOptions(this.caseworkReports);

            // Determine which report to load
            let targetId = preselectReportId;
            if (!targetId || !this.caseworkReports.some(r => (r.report_id || r._id) === targetId)) {
                targetId = this.caseworkReports[0].report_id || this.caseworkReports[0]._id;
            }

            reportSelect.value = targetId;
            await this.loadReportForReview(targetId);

        } catch (err) {
            console.error("[Review] Failed loading casework list:", err);
            reportSelect.innerHTML = `<option value="">Failed to load casework queue</option>`;
            this.renderEmptyCaseworkState("Failed to connect to casework repository.");
        }
    },

    populateReportSelectOptions(reportsList) {
        const reportSelect = document.getElementById('reviewReportSelect');
        if (!reportSelect) return;

        if (reportsList.length === 0) {
            reportSelect.innerHTML = `<option value="">No matching defect casework found</option>`;
            return;
        }

        reportSelect.innerHTML = reportsList.map(rep => {
            const ai = rep.assessment || {};
            const defect = ai.defect_class || rep.metadata?.defect_class || 'Distress';
            const status = rep.status || 'Received';
            const loc = rep.asset?.location || rep.metadata?.location_name || 'Corridor';
            const repId = rep.report_id || rep._id;
            const shortId = repId.length > 18 ? repId.slice(0, 16) + '...' : repId;
            const sev = (ai.relative_severity || rep.metadata?.relative_severity || 'Low').toUpperCase();

            return `<option value="${repId}">${shortId} — ${defect} [${status} • ${sev}] • ${loc}</option>`;
        }).join('');
    },

    filterCasework(query = '', statusFilter = '') {
        const q = query.toLowerCase().trim();
        const sf = statusFilter.toLowerCase().trim();

        const filtered = this.caseworkReports.filter(rep => {
            const ai = rep.assessment || {};
            const repId = (rep.report_id || rep._id || '').toLowerCase();
            const loc = (rep.asset?.location || rep.metadata?.location_name || '').toLowerCase();
            const defect = (ai.defect_class || rep.metadata?.defect_class || '').toLowerCase();
            const status = (rep.status || '').toLowerCase();
            const sev = (ai.relative_severity || rep.metadata?.relative_severity || '').toLowerCase();
            const assetType = (rep.asset?.asset_type || rep.metadata?.asset_type || '').toLowerCase();

            const matchesQuery = !q || (
                repId.includes(q) ||
                loc.includes(q) ||
                defect.includes(q) ||
                status.includes(q) ||
                sev.includes(q) ||
                assetType.includes(q)
            );

            const matchesStatus = !sf || status === sf;

            return matchesQuery && matchesStatus;
        });

        this.populateReportSelectOptions(filtered);

        const reportSelect = document.getElementById('reviewReportSelect');
        if (filtered.length > 0) {
            const nextId = filtered[0].report_id || filtered[0]._id;
            if (reportSelect) reportSelect.value = nextId;
            this.loadReportForReview(nextId);
        } else {
            this.renderEmptyCaseworkState("No reports match the search filter criteria.");
        }
    },

    renderEmptyCaseworkState(message = "Select a defect report from the casework list above to begin inspection.") {
        this.currentReport = null;
        this.currentAssessment = null;

        const frameEl = document.getElementById('reviewFrameId');
        const locEl = document.getElementById('reviewGps');
        const statusEl = document.getElementById('reviewHeaderStatus');
        const badgeDot = document.getElementById('reviewBadgeDot');
        const citizenNotesEl = document.getElementById('reviewCitizenNotes');
        const predClassEl = document.getElementById('reviewPredictedClass');
        const calcSevEl = document.getElementById('reviewCalculatedSeverity');
        const confEl = document.getElementById('telemConfidence');
        const sevEl = document.getElementById('telemSeverity');
        const areaEl = document.getElementById('telemArea');

        if (frameEl) frameEl.textContent = 'No Case Selected';
        if (locEl) locEl.textContent = '—';
        if (statusEl) statusEl.textContent = 'Status: Awaiting Case Selection';
        if (badgeDot) badgeDot.className = 'badge-dot';
        if (citizenNotesEl) citizenNotesEl.textContent = message;
        if (predClassEl) predClassEl.textContent = '—';
        if (calcSevEl) calcSevEl.textContent = '[ NO CASE LOADED ]';
        if (confEl) confEl.textContent = '—';
        if (sevEl) sevEl.textContent = '—';
        if (areaEl) areaEl.textContent = '—';

        const gallery = document.getElementById('reviewImageGallery');
        if (gallery) {
            gallery.classList.add('hidden');
            gallery.style.display = 'none';
        }
        const thumbList = document.getElementById('reviewThumbnailList');
        if (thumbList) thumbList.innerHTML = '';
        this.activeReportData = null;
        this.activeImageIndex = 0;

        // Draw clear empty placeholder on canvas
        const canvas = document.getElementById('reviewCanvas');
        if (canvas) {
            canvas.width = 640;
            canvas.height = 420;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#0f172a';
            ctx.fillRect(0, 0, 640, 420);
            ctx.fillStyle = '#94a3b8';
            ctx.font = '14px "Montserrat", sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(message, 320, 210);
        }
    },

    async loadReportForReview(reportId) {
        if (!reportId) {
            this.renderEmptyCaseworkState();
            return;
        }

        try {
            const data = await window.Api.getReportById(reportId);
            this.currentReport = data.report;
            this.currentAssessment = data.assessment;

            // Sync select dropdown if not already matched
            const reportSelect = document.getElementById('reviewReportSelect');
            if (reportSelect && reportSelect.value !== reportId) {
                reportSelect.value = reportId;
            }

            // Sync URL with clean bookmarkable report_id query parameter
            const url = new URL(window.location);
            url.searchParams.set('report_id', reportId);
            window.history.replaceState({}, '', url);

            // Populate Case Meta Header
            const repId = data.report.report_id || data.report._id;
            const frameEl = document.getElementById('reviewFrameId');
            if (frameEl) frameEl.textContent = `#${repId}`;

            const locName = data.asset?.location || data.report.metadata?.location_name || 'Corridor Asset';
            const lat = data.report.latitude || data.report.metadata?.latitude;
            const lng = data.report.longitude || data.report.metadata?.longitude;
            const coordsStr = (lat !== null && lng !== null && lat !== undefined && lng !== undefined)
                ? ` [${Number(lat).toFixed(5)}°, ${Number(lng).toFixed(5)}°]`
                : '';
            const locEl = document.getElementById('reviewGps');
            if (locEl) locEl.textContent = `${locName}${coordsStr}`;

            // Submitter & Authorship distinction
            const submitter = data.submitter || {};
            const submitterName = submitter.name || data.report.metadata?.submitted_by_name || 'Reporter';
            const submitterRole = (submitter.role || data.report.metadata?.submitted_by_role || 'citizen').toUpperCase();
            const submitterEl = document.getElementById('reviewSubmitter');
            if (submitterEl) {
                submitterEl.textContent = `${submitterName} (${submitterRole})`;
            }

            // Self-Review / Authorship Notice
            const currentUser = window.App?.currentUser;
            const currentUserId = currentUser ? String(currentUser.user_id || currentUser._id) : '';
            const reportUserId = String(data.report.user_id || data.report.metadata?.submitted_by_id || '');
            const isSelfSubmit = Boolean(currentUserId && reportUserId && currentUserId === reportUserId);
            const selfReviewBanner = document.getElementById('selfReviewBanner');
            if (selfReviewBanner) {
                selfReviewBanner.classList.toggle('hidden', !isSelfSubmit);
            }

            const citizenNotesEl = document.getElementById('reviewCitizenNotes');
            if (citizenNotesEl) {
                citizenNotesEl.textContent = data.report.description || data.report.metadata?.citizen_notes || 'No citizen field observations recorded.';
            }

            // Canonical Status & Validation Flags
            const status = data.report.status || 'Received';
            const statusSlug = status.toLowerCase().replace(/\s+/g, '-');
            const isUnusual = data.report.metadata?.is_unusual === true || data.report.validation_status === 'unusual';
            const statusEl = document.getElementById('reviewHeaderStatus');
            const badgeDot = document.getElementById('reviewBadgeDot');

            if (data.review) {
                if (statusEl) statusEl.textContent = `Status: ${status} (Validated: ${data.review.decision})`;
                if (badgeDot) badgeDot.className = 'badge-dot success';
                const notesEl = document.getElementById('engineerNotes');
                if (notesEl) notesEl.value = data.review.comments || '';
            } else if (isUnusual) {
                if (statusEl) statusEl.textContent = `Status: ${status} ⚠️ Unusual Pairing Flagged`;
                if (badgeDot) badgeDot.className = 'badge-dot warning';
                const notesEl = document.getElementById('engineerNotes');
                if (notesEl && !notesEl.value) notesEl.value = data.report.metadata?.advisory_notes || '';
            } else {
                if (statusEl) statusEl.textContent = `Status: ${status}`;
                if (badgeDot) badgeDot.className = `badge-dot ${status === 'Resolved' || status === 'Verified' ? 'success' : 'warning'}`;
                const notesEl = document.getElementById('engineerNotes');
                if (notesEl && !notesEl.value) notesEl.value = '';
            }

            // Multi-image angle switching & AI Telemetry rendering
            this.activeReportData = data;
            this.activeImageIndex = 0;
            this.renderImageGallery(data);

        } catch (e) {
            console.error("[Review] Load report review error:", e);
            window.App.showToast("Failed to load defect report for review.", true);
            this.renderEmptyCaseworkState("Could not retrieve defect report.");
        }
    },

    renderImageGallery(data) {
        const galleryContainer = document.getElementById('reviewImageGallery');
        const thumbList = document.getElementById('reviewThumbnailList');
        if (!galleryContainer || !thumbList) return;

        const images = (data.images && data.images.length > 0) ? data.images : (data.image ? [data.image] : []);

        if (images.length <= 1) {
            galleryContainer.classList.add('hidden');
            galleryContainer.style.display = 'none';
            thumbList.innerHTML = '';
            const img = images[0] || {};
            const ass = (data.assessments && data.assessments[0]) || data.assessment || {};
            this.updateTelemetryAndCanvas(img.url, ass);
            return;
        }

        galleryContainer.classList.remove('hidden');
        galleryContainer.style.display = 'flex';
        thumbList.innerHTML = images.map((img, idx) => {
            const isActive = idx === this.activeImageIndex;
            const activeStyle = isActive
                ? 'border: 2px solid #0284c7; box-shadow: 0 0 0 2px rgba(2, 132, 199, 0.4);'
                : 'border: 2px solid transparent; opacity: 0.7;';
            const angleName = img.original_filename || `Photo ${idx + 1}`;
            return `
                <button type="button" class="review-thumb-btn ${isActive ? 'active' : ''}" data-index="${idx}" title="${angleName}" style="cursor: pointer; padding: 0; background: none; border-radius: 4px; overflow: hidden; width: 68px; height: 50px; flex-shrink: 0; ${activeStyle}">
                    <img src="${img.url}" alt="${angleName}" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.src='/api/reports/images/seed_pothole.jpg'">
                </button>
            `;
        }).join('');

        thumbList.querySelectorAll('.review-thumb-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const targetBtn = e.currentTarget;
                const idx = parseInt(targetBtn.getAttribute('data-index'), 10);
                this.selectActiveImage(idx);
            });
        });

        this.selectActiveImage(0);
    },

    selectActiveImage(index) {
        this.activeImageIndex = index;
        const data = this.activeReportData;
        if (!data) return;

        const images = (data.images && data.images.length > 0) ? data.images : (data.image ? [data.image] : []);
        const activeImg = images[index] || images[0] || {};
        const activeAss = (data.assessments && data.assessments[index]) || (index === 0 ? data.assessment : {}) || {};

        // Update active class and styles on thumbnails
        const thumbList = document.getElementById('reviewThumbnailList');
        if (thumbList) {
            thumbList.querySelectorAll('.review-thumb-btn').forEach((btn, idx) => {
                const isActive = idx === index;
                btn.classList.toggle('active', isActive);
                btn.style.border = isActive ? '2px solid #0284c7' : '2px solid transparent';
                btn.style.boxShadow = isActive ? '0 0 0 2px rgba(2, 132, 199, 0.4)' : 'none';
                btn.style.opacity = isActive ? '1' : '0.7';
            });
        }

        this.updateTelemetryAndCanvas(activeImg.url, activeAss);
    },

    updateTelemetryAndCanvas(imageUrl, ai) {
        ai = ai || {};
        const detections = (ai.detections && ai.detections.length > 0)
            ? ai.detections
            : (ai.defect_class && ai.defect_class !== 'None Detected' ? [ai] : []);
        const hasDetections = detections.length > 0;

        const defectClass = ai.class_name || ai.defect_class || (hasDetections ? detections[0].class_name || 'Crack' : 'None Detected');
        const severity = (ai.severity || ai.relative_severity || 'Low').toUpperCase();
        const rawScore = ai.confidence !== undefined ? ai.confidence : (ai.confidence_score !== undefined ? ai.confidence_score : 0.0);
        const confidence = hasDetections ? Math.round(rawScore * 1000) / 10 : 0.0;
        const areaRatio = Math.round((ai.area_percentage || 0) * 10) / 10;

        const predClassEl = document.getElementById('reviewPredictedClass');
        const calcSevEl = document.getElementById('reviewCalculatedSeverity');
        if (predClassEl) predClassEl.textContent = defectClass;
        if (calcSevEl) calcSevEl.textContent = `[ RELATIVE SEVERITY: ${severity} ]`;

        const confEl = document.getElementById('telemConfidence');
        const sevEl = document.getElementById('telemSeverity');
        const areaEl = document.getElementById('telemArea');
        if (confEl) confEl.textContent = hasDetections ? `${confidence}%` : '—';
        if (sevEl) sevEl.textContent = severity;
        if (areaEl) areaEl.textContent = `${areaRatio}%`;

        // Render inspection canvas with scaled bounding boxes
        const url = imageUrl || '/api/reports/images/seed_pothole.jpg';
        this.drawReviewCanvas(url, ai);
    },

    drawReviewCanvas(imageUrl, aiData) {
        const canvas = document.getElementById('reviewCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => {
            const origW = img.naturalWidth || img.width;
            const origH = img.naturalHeight || img.height;
            canvas.width = origW;
            canvas.height = origH;
            ctx.drawImage(img, 0, 0, origW, origH);

            const detections = (aiData.detections && aiData.detections.length > 0)
                ? aiData.detections
                : (aiData.defect_class && aiData.defect_class !== 'None Detected' ? [aiData] : []);

            if (detections.length === 0) {
                const bannerH = Math.max(40, Math.round(origH * 0.08));
                ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
                ctx.fillRect(0, 0, origW, bannerH);
                ctx.fillStyle = '#10b981';
                const fontSize = Math.max(14, Math.round(origW * 0.024));
                ctx.font = `600 ${fontSize}px "Montserrat", sans-serif`;
                ctx.fillText('[ ✓ No Structural Defects Detected (Confidence >= 30%) ]', 16, Math.round(bannerH * 0.65));
                return;
            }

            detections.forEach(det => {
                let xmin, ymin, xmax, ymax;

                if (det.bounding_box && typeof det.bounding_box === 'object' && !Array.isArray(det.bounding_box)) {
                    xmin = det.bounding_box.xmin;
                    ymin = det.bounding_box.ymin;
                    xmax = det.bounding_box.xmax;
                    ymax = det.bounding_box.ymax;
                } else if (Array.isArray(det.bounding_box)) {
                    ymin = det.bounding_box[0] * origH;
                    xmin = det.bounding_box[1] * origW;
                    ymax = det.bounding_box[2] * origH;
                    xmax = det.bounding_box[3] * origW;
                } else if (Array.isArray(det.normalized_box)) {
                    ymin = det.normalized_box[0] * origH;
                    xmin = det.normalized_box[1] * origW;
                    ymax = det.normalized_box[2] * origH;
                    xmax = det.normalized_box[3] * origW;
                } else {
                    return;
                }

                xmin = Math.max(0, Math.min(origW, xmin));
                ymin = Math.max(0, Math.min(origH, ymin));
                xmax = Math.max(xmin, Math.min(origW, xmax));
                ymax = Math.max(ymin, Math.min(origH, ymax));

                const boxW = xmax - xmin;
                const boxH = ymax - ymin;
                const defectClass = det.class_name || det.defect_class || 'Defect';
                const color = defectClass === 'Pothole' ? '#ef4444' : (defectClass === 'Crack' ? '#f59e0b' : '#0284c7');

                const lineWidth = Math.max(3, Math.round(origW / 240));
                ctx.strokeStyle = color;
                ctx.lineWidth = lineWidth;
                ctx.strokeRect(xmin, ymin, boxW, boxH);

                // Precision corner crosshairs
                const ch = Math.max(6, Math.round(origW / 80));
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2;
                [[xmin, ymin], [xmax, ymin], [xmin, ymax], [xmax, ymax]].forEach(([cx, cy]) => {
                    ctx.beginPath();
                    ctx.moveTo(cx - ch, cy); ctx.lineTo(cx + ch, cy);
                    ctx.moveTo(cx, cy - ch); ctx.lineTo(cx, cy + ch);
                    ctx.stroke();
                });

                // Target banner pill with smart edge clamping and collision handling
                const confVal = det.confidence !== undefined ? det.confidence : (det.confidence_score || 0.0);
                const confText = Math.round(confVal * 100);
                const sevVal = det.severity || det.relative_severity || '';
                const labelText = sevVal
                    ? `[ ${defectClass} • ${confText}% • ${sevVal} ]`
                    : `[ ${defectClass} • ${confText}% ]`;

                const fontSize = Math.max(13, Math.round(origW * 0.022));
                ctx.font = `bold ${fontSize}px "JetBrains Mono", monospace`;
                const tw = ctx.measureText(labelText).width;
                const pillW = tw + 16;
                const pillH = fontSize + 12;

                const pillX = Math.max(2, Math.min(origW - pillW - 2, xmin));
                let pillY = (ymin >= pillH + 4) ? (ymin - pillH - 2) : (ymin + lineWidth + 2);

                if (!window._drawnReviewPills) window._drawnReviewPills = [];
                for (const prev of window._drawnReviewPills) {
                    if (Math.abs(prev.x - pillX) < pillW * 0.7 && Math.abs(prev.y - pillY) < pillH) {
                        pillY = prev.y + pillH + 4;
                    }
                }
                window._drawnReviewPills.push({ x: pillX, y: pillY, w: pillW, h: pillH });

                ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
                ctx.fillRect(pillX, pillY, pillW, pillH);
                ctx.strokeStyle = color;
                ctx.lineWidth = 1;
                ctx.strokeRect(pillX, pillY, pillW, pillH);

                ctx.fillStyle = color;
                ctx.fillText(labelText, pillX + 8, pillY + fontSize + 2);
            });
            window._drawnReviewPills = [];
        };

        img.onerror = () => {
            const placeholderW = 640;
            const placeholderH = 400;
            canvas.width = placeholderW;
            canvas.height = placeholderH;
            ctx.fillStyle = '#1e2536';
            ctx.fillRect(0, 0, placeholderW, placeholderH);
            ctx.fillStyle = '#ef4444';
            ctx.font = '14px "JetBrains Mono", monospace';
            ctx.textAlign = 'center';
            ctx.fillText('Inspection photograph could not be loaded.', 320, 200);
        };

        img.src = imageUrl;
    },

    async handleLifecycleTransition(targetStatus, reason = '') {
        if (!this.currentReport) {
            window.App.showToast("No active defect report loaded.", true);
            return;
        }

        const reportId = this.currentReport.report_id || this.currentReport._id;

        try {
            const res = await window.Api.updateReportStatus(reportId, targetStatus, reason);
            window.App.showToast(`Lifecycle status updated: ${res.report.status}`);
            
            // Reload report to refresh indicators
            await this.loadReportForReview(reportId);

            // Also refresh Dashboard queue if active
            if (window.Dashboard) {
                window.Dashboard.loadDashboardData();
            }
        } catch (err) {
            console.error("[Review] Lifecycle transition failed:", err);
            window.App.showToast(err.message || `Cannot transition to '${targetStatus}'.`, true);
        }
    },

    async submitProfessionalValidation() {
        if (!this.currentReport) {
            window.App.showToast("No active defect report loaded to review.", true);
            return;
        }

        const decision = document.querySelector('input[name="reviewDecision"]:checked')?.value || 'Confirmed';
        const comments = document.getElementById('engineerNotes')?.value.trim() || '';
        const reportId = this.currentReport.report_id || this.currentReport._id;

        // Validation rule: professional engineer notes are mandatory
        if (!comments) {
            window.App.showToast("Professional engineer review notes are required before signing off.", true);
            const notesEl = document.getElementById('engineerNotes');
            if (notesEl) notesEl.focus();
            return;
        }

        const overrideDetails = decision === 'Overridden' ? {
            override_class: document.getElementById('overrideClassSelect').value,
            override_severity: document.getElementById('overrideSeveritySelect').value
        } : {};

        try {
            await window.Api.reviewReportDirect(reportId, {
                decision,
                comments,
                override_details: overrideDetails
            });

            // Automatically transition status to Verified
            try {
                await window.Api.updateReportStatus(reportId, 'Verified', `Verified by certified engineer with ${decision} assessment.`);
            } catch (statusErr) {
                console.warn("[Review] Could not transition status to Verified:", statusErr);
            }

            window.App.showToast("Professional validation and engineer review recorded successfully.");

            // Reload report state
            await this.loadReportForReview(reportId);

            // Refresh dashboard
            if (window.Dashboard) {
                window.Dashboard.loadDashboardData();
            }
        } catch (e) {
            console.error("[Review] Sign off error:", e);
            window.App.showToast(e.message || "Failed to submit professional validation.", true);
        }
    }
};

window.Review = Review;
