/**
 * Review Module - AI Defect Assessment & Professional Engineer Review Terminal (Figure 4.8)
 */
const Review = {
    currentReport: null,
    currentAssessment: null,

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
    },

    async loadReportForReview(reportId) {
        try {
            const data = await window.Api.getReportById(reportId);
            this.currentReport = data.report;
            this.currentAssessment = data.assessment;

            // Update Header Meta
            const frameEl = document.getElementById('reviewFrameId');
            const locEl = document.getElementById('reviewGps');
            const statusEl = document.getElementById('reviewHeaderStatus');
            const badgeDot = document.getElementById('reviewBadgeDot');

            if (frameEl) frameEl.textContent = `#${data.report.report_id || data.report._id}`;
            if (locEl) locEl.textContent = data.asset?.location || data.report.metadata?.location_name || 'Corridor Asset';

            // Review status display
            if (data.review) {
                if (statusEl) statusEl.textContent = `Status: Validated (${data.review.decision})`;
                if (badgeDot) {
                    badgeDot.className = 'badge-dot success';
                }
                const notesEl = document.getElementById('engineerNotes');
                if (notesEl) notesEl.value = data.review.comments || '';
            } else {
                if (statusEl) statusEl.textContent = `Status: Pending Engineer Review`;
                if (badgeDot) {
                    badgeDot.className = 'badge-dot warning';
                }
                const notesEl = document.getElementById('engineerNotes');
                if (notesEl) notesEl.value = '';
            }

            const ai = data.assessment || {};
            const defectClass = ai.defect_class || 'Pothole';
            const severity = ai.relative_severity || 'Critical';
            const confidence = Math.round((ai.confidence_score || 0.94) * 1000) / 10;
            const areaRatio = Math.round((ai.area_percentage || 20) * 10) / 10;

            // Output panel
            const predClassEl = document.getElementById('reviewPredictedClass');
            const calcSevEl = document.getElementById('reviewCalculatedSeverity');
            if (predClassEl) predClassEl.textContent = defectClass;
            if (calcSevEl) calcSevEl.textContent = `[ RELATIVE SEVERITY: ${severity.toUpperCase()} ]`;

            // Telemetry indicators
            const confEl = document.getElementById('telemConfidence');
            const sevEl = document.getElementById('telemSeverity');
            const areaEl = document.getElementById('telemArea');

            if (confEl) confEl.textContent = `${confidence}%`;
            if (sevEl) confEl.textContent = severity;
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
        img.onload = () => {
            canvas.width = img.width;
            canvas.height = img.height;
            ctx.drawImage(img, 0, 0);

            // Draw bounding box
            const box = aiData.bounding_box || [0.22, 0.25, 0.72, 0.78];
            const ymin = box[0] * img.height;
            const xmin = box[1] * img.width;
            const ymax = box[2] * img.height;
            const xmax = box[3] * img.width;
            const boxW = xmax - xmin;
            const boxH = ymax - ymin;

            ctx.strokeStyle = '#ef4444';
            ctx.lineWidth = 4;
            ctx.strokeRect(xmin, ymin, boxW, boxH);

            // Precision crosshair markers
            const ch = 10;
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 2;
            [[xmin, ymin], [xmax, ymin], [xmin, ymax], [xmax, ymax]].forEach(([cx, cy]) => {
                ctx.beginPath();
                ctx.moveTo(cx - ch, cy); ctx.lineTo(cx + ch, cy);
                ctx.moveTo(cx, cy - ch); ctx.lineTo(cx, cy + ch);
                ctx.stroke();
            });

            // Target banner
            const conf = Math.round((aiData.confidence_score || 0.94) * 100);
            const labelText = `[ ${aiData.defect_class || 'Defect'} - ${conf}% ]`;
            ctx.font = 'bold 15px "JetBrains Mono", monospace';
            const tw = ctx.measureText(labelText).width;

            ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
            ctx.fillRect(xmin, Math.max(0, ymin - 28), tw + 16, 28);
            ctx.fillStyle = '#ef4444';
            ctx.fillText(labelText, xmin + 8, Math.max(20, ymin - 9));
        };

        img.onerror = () => {
            canvas.width = 640;
            canvas.height = 400;
            ctx.fillStyle = '#1e2536';
            ctx.fillRect(0, 0, 640, 400);

            ctx.strokeStyle = '#ef4444';
            ctx.lineWidth = 4;
            ctx.strokeRect(140, 90, 360, 220);

            ctx.fillStyle = '#ffffff';
            ctx.font = '14px "JetBrains Mono", monospace';
            ctx.fillText(`[ ${aiData.defect_class || 'Pothole'} - Detected ]`, 150, 75);
        };

        img.src = imageUrl;
    },

    async submitProfessionalValidation() {
        if (!this.currentAssessment) {
            window.App.showToast("No active defect report loaded to review.", true);
            return;
        }

        const decision = document.querySelector('input[name="reviewDecision"]:checked')?.value || 'Confirmed';
        const comments = document.getElementById('engineerNotes')?.value.trim() || '';
        const assessmentId = this.currentAssessment._id || this.currentAssessment.assessment_id;

        const overrideDetails = decision === 'Overridden' ? {
            override_class: document.getElementById('overrideClassSelect').value,
            override_severity: document.getElementById('overrideSeveritySelect').value
        } : {};

        try {
            const res = await window.Api.submitReview(assessmentId, {
                decision,
                comments: comments || 'Concur with automated AI defect detection.',
                override_details: overrideDetails
            });

            const statusEl = document.getElementById('reviewHeaderStatus');
            const badgeDot = document.getElementById('reviewBadgeDot');
            if (statusEl) statusEl.textContent = `Status: Validated (${decision})`;
            if (badgeDot) badgeDot.className = 'badge-dot success';

            window.App.showToast("Professional validation and engineer review recorded.");

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
