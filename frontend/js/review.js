/**
 * Review Module - AI Defect Assessment & Professional Engineer Review Terminal (Figure 4.8)
 * Handles Casework switching, lifecycle transitions (Received -> Under Review -> Verified -> Resolved),
 * visual bounding box overlay inspection, and certified engineer sign-off.
 */
const Review = {
    currentReport: null,
    currentAssessment: null,
    caseworkReports: [],

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
                    overrideFields.classList.remove('hidden');
                } else {
                    overrideFields.classList.add('hidden');
                }
            });
        });

        const reportSelect = document.getElementById('reviewReportSelect');
        if (reportSelect) {
            reportSelect.addEventListener('change', (e) => {
                if (e.target.value) {
                    this.loadReportForReview(e.target.value);
                }
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
            const data = await window.Api.getReports({ limit: 50 });
            this.caseworkReports = data.reports || [];

            if (this.caseworkReports.length === 0) {
                reportSelect.innerHTML = `<option value="">No defect casework available</option>`;
                return;
            }

            reportSelect.innerHTML = this.caseworkReports.map(item => {
                const rep = item.report;
                const ai = item.assessment || {};
                const defect = ai.defect_class || rep.defect_type || 'Defect';
                const status = rep.status || 'Received';
                const loc = rep.metadata?.location_name || 'Corridor';
                const repId = rep.report_id || rep._id;
                return `<option value="${repId}">${repId} — ${defect} [${status}] • ${loc}</option>`;
            }).join('');

            const targetId = preselectReportId || this.caseworkReports[0].report.report_id || this.caseworkReports[0].report._id;
            reportSelect.value = targetId;
            await this.loadReportForReview(targetId);
        } catch (err) {
            console.error("Failed to load casework list:", err);
            reportSelect.innerHTML = `<option value="">Failed to load casework</option>`;
        }
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

            // Also refresh Dashboard if open
            if (window.Dashboard) {
                window.Dashboard.loadDashboardData();
            }
        } catch (err) {
            console.error("Lifecycle transition failed:", err);
            window.App.showToast(err.message || `Cannot transition to '${targetStatus}'.`, true);
        }
    },

    async loadReportForReview(reportId) {
        try {
            const data = await window.Api.getReportById(reportId);
            this.currentReport = data.report;
            this.currentAssessment = data.assessment;

            // Sync dropdown selection if needed
            const reportSelect = document.getElementById('reviewReportSelect');
            if (reportSelect && reportSelect.value !== reportId) {
                reportSelect.value = reportId;
            }

            // Update Header Meta
            const frameEl = document.getElementById('reviewFrameId');
            const locEl = document.getElementById('reviewGps');
            const statusEl = document.getElementById('reviewHeaderStatus');
            const badgeDot = document.getElementById('reviewBadgeDot');
            const citizenNotesEl = document.getElementById('reviewCitizenNotes');

            const repId = data.report.report_id || data.report._id;
            if (frameEl) frameEl.textContent = `#${repId}`;

            const locName = data.asset?.location || data.report.metadata?.location_name || 'Corridor Asset';
            const coordsStr = (data.report.latitude && data.report.longitude)
                ? ` [${data.report.latitude.toFixed(4)}°, ${data.report.longitude.toFixed(4)}°]`
                : '';
            if (locEl) locEl.textContent = `${locName}${coordsStr}`;

            if (citizenNotesEl) {
                citizenNotesEl.textContent = data.report.description || data.report.metadata?.citizen_notes || 'No citizen field notes provided.';
            }

            // Review status display
            const status = data.report.status || 'Received';
            const isUnusual = data.report.metadata?.is_unusual === true || data.report.validation_status === 'unusual';

            if (data.review) {
                if (statusEl) statusEl.textContent = `Lifecycle: ${status} (Validated: ${data.review.decision})`;
                if (badgeDot) badgeDot.className = 'badge-dot success';
                const notesEl = document.getElementById('engineerNotes');
                if (notesEl) notesEl.value = data.review.comments || '';
            } else if (isUnusual) {
                if (statusEl) statusEl.textContent = `Lifecycle: ${status} ⚠️ Unusual Combination Flagged`;
                if (badgeDot) badgeDot.className = 'badge-dot warning';
                const notesEl = document.getElementById('engineerNotes');
                if (notesEl) notesEl.value = data.report.metadata?.advisory_notes || '';
            } else {
                if (statusEl) statusEl.textContent = `Lifecycle: ${status}`;
                if (badgeDot) badgeDot.className = `badge-dot ${status === 'Resolved' ? 'success' : 'warning'}`;
                const notesEl = document.getElementById('engineerNotes');
                if (notesEl && !notesEl.value) notesEl.value = '';
            }

            // Telemetry & metrics
            const ai = data.assessment || {};
            const detections = (ai.detections && ai.detections.length > 0)
                ? ai.detections
                : (ai.defect_class && ai.defect_class !== 'None Detected' ? [ai] : []);
            const hasDetections = detections.length > 0;

            const defectClass = ai.class_name || ai.defect_class || (hasDetections ? detections[0].class_name || 'Crack' : 'None Detected');
            const severity = ai.severity || ai.relative_severity || 'Low';
            const rawScore = ai.confidence !== undefined ? ai.confidence : (ai.confidence_score !== undefined ? ai.confidence_score : 0.0);
            const confidence = hasDetections ? Math.round(rawScore * 1000) / 10 : 0.0;
            const areaRatio = Math.round((ai.area_percentage || 0) * 10) / 10;

            // Output panel
            const predClassEl = document.getElementById('reviewPredictedClass');
            const calcSevEl = document.getElementById('reviewCalculatedSeverity');
            if (predClassEl) predClassEl.textContent = defectClass;
            if (calcSevEl) calcSevEl.textContent = `[ RELATIVE SEVERITY: ${severity.toUpperCase()} ]`;

            // Telemetry indicators
            const confEl = document.getElementById('telemConfidence');
            const sevEl = document.getElementById('telemSeverity');
            const areaEl = document.getElementById('telemArea');

            if (confEl) confEl.textContent = hasDetections ? `${confidence}%` : '—';
            if (sevEl) sevEl.textContent = severity;
            if (areaEl) areaEl.textContent = `${areaRatio}%`;

            // Render inspection canvas with bounding boxes
            const imageUrl = data.image?.url || '/api/reports/images/seed_pothole.jpg';
            this.drawReviewCanvas(imageUrl, ai);

        } catch (e) {
            console.error("Load report review error:", e);
            window.App.showToast("Failed to load defect report for review.", true);
        }
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

                // Precision crosshairs
                const ch = Math.max(6, Math.round(origW / 80));
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2;
                [[xmin, ymin], [xmax, ymin], [xmin, ymax], [xmax, ymax]].forEach(([cx, cy]) => {
                    ctx.beginPath();
                    ctx.moveTo(cx - ch, cy); ctx.lineTo(cx + ch, cy);
                    ctx.moveTo(cx, cy - ch); ctx.lineTo(cx, cy + ch);
                    ctx.stroke();
                });

                // Target banner pill
                const confVal = det.confidence !== undefined ? det.confidence : (det.confidence_score || 0.0);
                const conf = Math.round(confVal * 100);
                const sevVal = det.severity || det.relative_severity || '';
                const labelText = sevVal
                    ? `[ ${defectClass} • ${conf}% • ${sevVal} ]`
                    : `[ ${defectClass} • ${conf}% ]`;

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
            ctx.fillText('Inspection photograph could not be loaded.', 40, 200);
        };

        img.src = imageUrl;
    },

    async submitProfessionalValidation() {
        if (!this.currentReport) {
            window.App.showToast("No active defect report loaded to review.", true);
            return;
        }

        const decision = document.querySelector('input[name="reviewDecision"]:checked')?.value || 'Confirmed';
        const comments = document.getElementById('engineerNotes')?.value.trim() || '';
        const reportId = this.currentReport.report_id || this.currentReport._id;

        const overrideDetails = decision === 'Overridden' ? {
            override_class: document.getElementById('overrideClassSelect').value,
            override_severity: document.getElementById('overrideSeveritySelect').value
        } : {};

        try {
            await window.Api.reviewReportDirect(reportId, {
                decision,
                comments: comments || 'Concur with automated AI defect detection.',
                override_details: overrideDetails
            });

            window.App.showToast("Professional validation and engineer review recorded.");

            // Reload report state
            await this.loadReportForReview(reportId);

            // Refresh dashboard
            if (window.Dashboard) {
                window.Dashboard.loadDashboardData();
            }
        } catch (e) {
            console.error("Sign off error:", e);
            window.App.showToast(e.message || "Failed to submit professional validation.", true);
        }
    }
};

window.Review = Review;
