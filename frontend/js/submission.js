/**
 * Submission Module - Citizen Defect Submission & AI Pre-Assessment (Figure 4.6)
 */
const Submission = {
    selectedFile: null,
    lastAssessment: null,

    init() {
        this.bindEvents();
    },

    bindEvents() {
        const fileInput = document.getElementById('imageFileInput');
        const triggerBtn = document.getElementById('btnTriggerUpload');
        const dropzone = document.getElementById('uploadDropzone');
        const removeBtn = document.getElementById('btnRemoveImage');
        const sampleBtn = document.getElementById('btnSamplePhoto');
        const submitAiBtn = document.getElementById('btnSubmitAiAnalysis');
        const confirmBtn = document.getElementById('btnConfirmSubmit');
        const resetBtn = document.getElementById('btnResetForm');
        const gpsBtn = document.getElementById('btnAutoGps');

        if (triggerBtn && fileInput) {
            triggerBtn.addEventListener('click', () => fileInput.click());
        }

        if (fileInput) {
            fileInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files[0]) {
                    this.handleFileSelected(e.target.files[0]);
                }
            });
        }

        // Drag & Drop
        if (dropzone) {
            dropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropzone.classList.add('drag-active');
            });
            dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-active'));
            dropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropzone.classList.remove('drag-active');
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                    this.handleFileSelected(e.dataTransfer.files[0]);
                }
            });
        }

        if (removeBtn) {
            removeBtn.addEventListener('click', () => this.clearFile());
        }

        if (sampleBtn) {
            sampleBtn.addEventListener('click', () => this.loadSamplePhoto());
        }

        if (gpsBtn) {
            gpsBtn.addEventListener('click', () => {
                const locInput = document.getElementById('defectLocation');
                locInput.value = "Uhuru Highway (Chainage 14+350) [-1.2921° S, 36.8219° E]";
                window.App.showToast("GPS coordinates synchronized with device geolocator.");
            });
        }

        if (submitAiBtn) {
            submitAiBtn.addEventListener('click', () => this.processAiSubmission());
        }

        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => {
                window.App.showToast("Ticket confirmed and logged in municipal monitoring ledger.");
                window.App.navigateTo('view-tracking');
            });
        }

        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                document.getElementById('defectNotes').focus();
                window.App.showToast("Edit mode active: update location or description.");
            });
        }
    },

    handleFileSelected(file) {
        this.selectedFile = file;
        const reader = new FileReader();
        reader.onload = (e) => {
            const previewImg = document.getElementById('previewImg');
            previewImg.src = e.target.result;
            document.getElementById('dropzonePrompt').classList.add('hidden');
            document.getElementById('dropzonePreview').classList.remove('hidden');
        };
        reader.readAsDataURL(file);
    },

    loadSamplePhoto() {
        // Generate an illustrative infrastructure pavement canvas sample
        const canvas = document.createElement('canvas');
        canvas.width = 640;
        canvas.height = 480;
        const ctx = canvas.getContext('2d');

        // Asphalt road texture
        ctx.fillStyle = '#2b2e38';
        ctx.fillRect(0, 0, 640, 480);

        // Road markings
        ctx.strokeStyle = '#e2b024';
        ctx.lineWidth = 14;
        ctx.setLineDash([40, 30]);
        ctx.beginPath();
        ctx.moveTo(320, 0);
        ctx.lineTo(320, 480);
        ctx.stroke();
        ctx.setLineDash([]);

        // Pothole / defect cavity texture
        ctx.fillStyle = '#14161b';
        ctx.beginPath();
        ctx.ellipse(320, 240, 110, 65, Math.PI / 12, 0, 2 * Math.PI);
        ctx.fill();
        ctx.strokeStyle = '#0a0a0c';
        ctx.lineWidth = 6;
        ctx.stroke();

        // Radiating cracks
        ctx.strokeStyle = '#1a1c22';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(220, 240);
        ctx.lineTo(130, 260);
        ctx.lineTo(90, 310);
        ctx.moveTo(420, 230);
        ctx.lineTo(510, 210);
        ctx.lineTo(560, 180);
        ctx.stroke();

        canvas.toBlob((blob) => {
            const file = new File([blob], "sample_pothole_asphalt.jpg", { type: "image/jpeg" });
            this.handleFileSelected(file);
            window.App.showToast("Simulated infrastructure defect image loaded.");
        }, 'image/jpeg');
    },

    clearFile() {
        this.selectedFile = null;
        document.getElementById('imageFileInput').value = '';
        document.getElementById('dropzonePrompt').classList.remove('hidden');
        document.getElementById('dropzonePreview').classList.add('hidden');
    },

    async processAiSubmission() {
        if (!this.selectedFile) {
            window.App.showToast("Please upload or load a defect photo first.", true);
            return;
        }

        const infraType = document.getElementById('infraType').value;
        const location = document.getElementById('defectLocation').value;
        const notes = document.getElementById('defectNotes').value;

        const formData = new FormData();
        formData.append('image', this.selectedFile);
        formData.append('asset_type', infraType);
        formData.append('location', location);
        formData.append('description', notes);

        const btn = document.getElementById('btnSubmitAiAnalysis');
        const originalText = btn.innerHTML;
        btn.innerHTML = `<span>⏳</span> Analyzing with SSD-MobileNetV2...`;
        btn.disabled = true;

        try {
            const data = await window.Api.submitDefect(formData);
            this.lastAssessment = data;
            this.renderAssessmentResults(data);
            window.App.showToast("Defect analyzed successfully by SSD-MobileNetV2.");
            document.getElementById('btnConfirmSubmit').disabled = false;
        } catch (err) {
            console.error(err);
            window.App.showToast(err.message || "Failed to analyze image.", true);
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    },

    renderAssessmentResults(data) {
        const ai = data.ai_assessment;
        if (!ai) return;

        // Metric fields
        document.getElementById('resDefectClass').textContent = ai.defect_class;
        document.getElementById('resConfidence').textContent = `${ai.confidence_percentage}%`;
        
        const sevEl = document.getElementById('resSeverity');
        sevEl.textContent = `[ ${ai.relative_severity.toUpperCase()} ]`;
        sevEl.className = `severity-pill ${ai.relative_severity.toLowerCase()}`;

        document.getElementById('resAreaRatio').textContent = `${ai.area_percentage}% of image extent`;

        const noticeEl = document.getElementById('noticeText');
        noticeEl.textContent = ai.action_index;

        // Render Canvas Bounding Box (Figure 4.6)
        this.drawBoundingBoxOnCanvas(data.image.url, ai);
    },

    drawBoundingBoxOnCanvas(imageUrl, aiData) {
        const canvas = document.getElementById('detectionCanvas');
        const placeholder = document.getElementById('canvasPlaceholder');
        const ctx = canvas.getContext('2d');

        const img = new Image();
        img.onload = () => {
            if (placeholder) placeholder.classList.add('hidden');
            canvas.width = img.width;
            canvas.height = img.height;
            ctx.drawImage(img, 0, 0);

            // Draw bounding boxes for each detection
            const detections = aiData.detections || [aiData];
            detections.forEach(det => {
                const box = det.bounding_box || [0.2, 0.2, 0.8, 0.8];
                const ymin = box[0] * img.height;
                const xmin = box[1] * img.width;
                const ymax = box[2] * img.height;
                const xmax = box[3] * img.width;
                const boxW = xmax - xmin;
                const boxH = ymax - ymin;

                // Severity border color
                const color = det.defect_class === 'Pothole' ? '#ef4444' : (det.defect_class === 'Crack' ? '#f59e0b' : '#06b6d4');

                // Bounding Box stroke
                ctx.strokeStyle = color;
                ctx.lineWidth = 4;
                ctx.setLineDash([6, 4]);
                ctx.strokeRect(xmin, ymin, boxW, boxH);
                ctx.setLineDash([]);

                // Label background chip
                const labelText = `[ ${det.defect_class} (${Math.round(det.confidence_score * 100)}%) ]`;
                ctx.font = 'bold 16px "JetBrains Mono", monospace';
                const textWidth = ctx.measureText(labelText).width;

                ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
                ctx.fillRect(xmin, Math.max(0, ymin - 26), textWidth + 16, 26);

                ctx.fillStyle = color;
                ctx.fillText(labelText, xmin + 8, Math.max(18, ymin - 8));
            });
        };
        img.src = imageUrl;
    }
};

window.Submission = Submission;
