/**
 * Submission Module - Citizen Defect Submission & AI Pre-Assessment (Figure 4.6)
 */
const Submission = {
    selectedFiles: [],
    lastAssessment: null,
    currentPreviewIndex: 0,

    init() {
        this.bindEvents();
    },

    bindEvents() {
        const fileInput = document.getElementById('imageFileInput');
        const triggerBtn = document.getElementById('btnTriggerUpload');
        const addMoreBtn = document.getElementById('btnAddMorePhotos');
        const dropzone = document.getElementById('uploadDropzone');
        const sampleBtn = document.getElementById('btnSamplePhoto');
        const submitAiBtn = document.getElementById('btnSubmitAiAnalysis');
        const resetBtn = document.getElementById('btnResetForm');
        const gpsBtn = document.getElementById('btnAutoGps');

        if (triggerBtn && fileInput) {
            triggerBtn.addEventListener('click', () => fileInput.click());
        }

        if (addMoreBtn && fileInput) {
            addMoreBtn.addEventListener('click', () => fileInput.click());
        }

        if (fileInput) {
            fileInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files.length > 0) {
                    this.handleFilesSelected(Array.from(e.target.files));
                    fileInput.value = '';
                }
            });
        }

        // Drag & Drop Handling
        if (dropzone) {
            dropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropzone.classList.add('drag-active');
            });
            dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-active'));
            dropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropzone.classList.remove('drag-active');
                if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                    this.handleFilesSelected(Array.from(e.dataTransfer.files));
                }
            });
        }

        if (sampleBtn) {
            sampleBtn.addEventListener('click', () => this.loadSamplePhoto());
        }

        if (gpsBtn) {
            gpsBtn.addEventListener('click', () => this.openLocationPicker());
        }

        const closePickerBtn = document.getElementById('btnCloseLocationPicker');
        const cancelPickerBtn = document.getElementById('btnCancelLocationPicker');
        const confirmPickerBtn = document.getElementById('btnConfirmLocationPicker');
        const currentLocBtn = document.getElementById('btnPickerCurrentLocation');
        const pickerModal = document.getElementById('locationPickerModal');

        if (closePickerBtn) closePickerBtn.addEventListener('click', () => this.closeLocationPicker());
        if (cancelPickerBtn) cancelPickerBtn.addEventListener('click', () => this.closeLocationPicker());
        if (confirmPickerBtn) confirmPickerBtn.addEventListener('click', () => this.confirmPickedLocation());

        if (currentLocBtn) {
            currentLocBtn.addEventListener('click', () => {
                if (navigator.geolocation) {
                    window.App?.showToast("Acquiring GPS location from device...");
                    navigator.geolocation.getCurrentPosition(
                        (position) => {
                            const lat = position.coords.latitude;
                            const lng = position.coords.longitude;
                            this.updatePickerPosition(lat, lng, true, true);
                            window.App?.showToast(`GPS acquired: ${lat.toFixed(4)}°, ${lng.toFixed(4)}°`);
                        },
                        (err) => {
                            console.warn("Geolocation warning:", err);
                            window.App?.showToast("Could not access device GPS. You can click on the map to place a pin.", true);
                        },
                        { timeout: 8000, enableHighAccuracy: true }
                    );
                } else {
                    window.App?.showToast("Geolocation not supported by browser. Enter location manually.", true);
                }
            });
        }

        if (pickerModal) {
            pickerModal.addEventListener('click', (e) => {
                if (e.target === pickerModal) this.closeLocationPicker();
            });
        }

        if (submitAiBtn) {
            submitAiBtn.addEventListener('click', () => this.processAiSubmission());
        }

        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                this.clearFiles();
                this.selectedCoordinates = null;
                this.tempCoordinates = null;

                const taggedBtn = document.getElementById('btnAutoGps');
                if (taggedBtn) taggedBtn.classList.remove('tagged');
                const taggedText = document.getElementById('btnAutoGpsText');
                if (taggedText) taggedText.textContent = '📍 Tag Location';
                const summaryInput = document.getElementById('pickerLocationSummary');
                if (summaryInput) {
                    summaryInput.value = '';
                    delete summaryInput.dataset.autofilled;
                }

                document.getElementById('defectLocation').value = '';
                document.getElementById('defectNotes').value = '';
                document.getElementById('resDefectClass').textContent = '—';
                document.getElementById('resConfidence').textContent = '—';
                document.getElementById('resSeverity').textContent = '—';
                document.getElementById('resSeverity').className = 'severity-pill';
                document.getElementById('resAreaRatio').textContent = '—';
                
                const badgeList = document.getElementById('multiDetectionsList');
                if (badgeList) badgeList.innerHTML = '';

                const placeholder = document.getElementById('canvasPlaceholder');
                if (placeholder) placeholder.classList.remove('hidden');
                
                const canvas = document.getElementById('detectionCanvas');
                if (canvas) {
                    const ctx = canvas.getContext('2d');
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                }

                const banner = document.getElementById('unusualDefectBanner');
                if (banner) banner.classList.add('hidden');

                document.getElementById('btnViewTrackingAfterSubmit').disabled = true;
                window.App.showToast("Ready for new defect submission.");
            });
        }
    },

    openLocationPicker() {
        const modal = document.getElementById('locationPickerModal');
        if (!modal) return;
        modal.classList.add('active');

        // Initial coordinates: existing selectedCoordinates or Nairobi fallback
        const initialLat = this.selectedCoordinates?.latitude ?? -1.286389;
        const initialLng = this.selectedCoordinates?.longitude ?? 36.817223;
        this.tempCoordinates = { latitude: initialLat, longitude: initialLng };

        const summaryInput = document.getElementById('pickerLocationSummary');
        const locInput = document.getElementById('defectLocation');
        if (summaryInput && locInput && locInput.value.trim() && !summaryInput.value.trim()) {
            summaryInput.value = locInput.value.trim();
        }

        // Initialize or invalidate picker map
        setTimeout(() => {
            if (!this.pickerMap) {
                this.initPickerMap(initialLat, initialLng);
            } else {
                this.pickerMap.invalidateSize();
                this.updatePickerPosition(initialLat, initialLng, true, false);
            }

            // If user has not tagged yet, attempt browser geolocation politely
            if (!this.selectedCoordinates && navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (pos) => {
                        this.updatePickerPosition(pos.coords.latitude, pos.coords.longitude, true, true);
                        window.App?.showToast("Device coordinates acquired.");
                    },
                    (err) => {
                        console.warn("[LocationPicker] Browser geolocation not granted:", err.message);
                    },
                    { timeout: 7000, enableHighAccuracy: true }
                );
            }
        }, 120);
    },

    closeLocationPicker() {
        const modal = document.getElementById('locationPickerModal');
        if (modal) modal.classList.remove('active');
    },

    initPickerMap(lat, lng) {
        const container = document.getElementById('pickerMapContainer');
        if (!container || typeof L === 'undefined') return;

        this.pickerMap = L.map(container, {
            center: [lat, lng],
            zoom: 14,
            zoomControl: true
        });

        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'
        }).addTo(this.pickerMap);

        const customPinIcon = L.divIcon({
            className: 'picker-pin-wrapper',
            html: `
                <div style="position:relative; width:30px; height:38px; cursor:grab;">
                    <svg viewBox="0 0 30 38" width="30" height="38" style="filter: drop-shadow(0 2px 4px rgba(0,0,0,0.4));">
                        <path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 15 23 15 23s15-12.5 15-23c0-8.3-6.7-15-15-15z" fill="#0071e3"/>
                        <circle cx="15" cy="14" r="5" fill="#ffffff"/>
                    </svg>
                </div>
            `,
            iconSize: [30, 38],
            iconAnchor: [15, 38]
        });

        this.pickerMarker = L.marker([lat, lng], {
            draggable: true,
            icon: customPinIcon
        }).addTo(this.pickerMap);

        this.pickerMarker.on('dragend', (e) => {
            const pos = e.target.getLatLng();
            this.updatePickerPosition(pos.lat, pos.lng, false, true);
        });

        this.pickerMap.on('click', (e) => {
            this.updatePickerPosition(e.latlng.lat, e.latlng.lng, false, true);
        });

        this.updatePickerCoordsBadge(lat, lng);
    },

    updatePickerPosition(lat, lng, shouldPan = true, reverseGeocode = true) {
        this.tempCoordinates = { latitude: lat, longitude: lng };
        if (this.pickerMarker) {
            this.pickerMarker.setLatLng([lat, lng]);
        }
        if (shouldPan && this.pickerMap) {
            this.pickerMap.setView([lat, lng], Math.max(this.pickerMap.getZoom(), 14));
        }
        this.updatePickerCoordsBadge(lat, lng);

        if (reverseGeocode) {
            this.reverseGeocodeCoordinates(lat, lng);
        }
    },

    updatePickerCoordsBadge(lat, lng) {
        const badge = document.getElementById('pickerCoordsDisplay');
        if (badge) {
            badge.textContent = `Lat: ${lat.toFixed(5)}, Lng: ${lng.toFixed(5)}`;
        }
    },

    reverseGeocodeCoordinates(lat, lng) {
        if (this.reverseGeocodeTimeout) {
            clearTimeout(this.reverseGeocodeTimeout);
        }
        this.reverseGeocodeTimeout = setTimeout(async () => {
            try {
                const url = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lng)}&zoom=17&addressdetails=1`;
                const resp = await fetch(url, {
                    headers: { 'Accept-Language': 'en' }
                });
                if (resp.ok) {
                    const data = await resp.json();
                    const addr = data.address || {};
                    const road = addr.road || addr.pedestrian || addr.suburb || addr.neighbourhood || addr.city || '';
                    const summary = document.getElementById('pickerLocationSummary');
                    if (summary && road && (!summary.value || summary.dataset.autofilled === 'true')) {
                        summary.value = road + (addr.city ? `, ${addr.city}` : '');
                        summary.dataset.autofilled = 'true';
                    }
                }
            } catch (e) {
                // Ignore geocoding network errors gracefully
            }
        }, 600);
    },

    confirmPickedLocation() {
        if (!this.tempCoordinates) {
            window.App?.showToast("Please place a pin on the map first.", true);
            return;
        }

        this.selectedCoordinates = {
            latitude: this.tempCoordinates.latitude,
            longitude: this.tempCoordinates.longitude
        };

        const summaryInput = document.getElementById('pickerLocationSummary');
        const locInput = document.getElementById('defectLocation');
        const summaryText = summaryInput ? summaryInput.value.trim() : '';

        if (summaryText) {
            locInput.value = summaryText;
        } else if (!locInput.value.trim()) {
            locInput.value = `Location [${this.selectedCoordinates.latitude.toFixed(5)}°, ${this.selectedCoordinates.longitude.toFixed(5)}°]`;
        }

        const gpsBtn = document.getElementById('btnAutoGps');
        const gpsBtnText = document.getElementById('btnAutoGpsText');
        if (gpsBtn) {
            gpsBtn.classList.add('tagged');
            gpsBtn.title = "Defect coordinates tagged. Click to re-position.";
        }
        if (gpsBtnText) {
            gpsBtnText.textContent = `✓ 📍 Tagged (${this.selectedCoordinates.latitude.toFixed(4)}°, ${this.selectedCoordinates.longitude.toFixed(4)}°)`;
        }

        this.closeLocationPicker();
        window.App?.showToast(`Defect coordinates confirmed: ${this.selectedCoordinates.latitude.toFixed(4)}°, ${this.selectedCoordinates.longitude.toFixed(4)}°`);
    },

    handleFilesSelected(files) {
        if (!files || files.length === 0) return;

        // Filter valid images under 16MB
        const validImages = files.filter(f => {
            const isImg = f.type.startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(f.name);
            const validSize = f.size <= 16 * 1024 * 1024;
            if (!isImg) window.App?.showToast(`File "${f.name}" is not a supported image format.`, true);
            if (!validSize) window.App?.showToast(`File "${f.name}" exceeds the 16MB size limit.`, true);
            return isImg && validSize;
        });

        if (validImages.length === 0) return;

        const currentCount = this.selectedFiles.length;
        const availableSlots = 3 - currentCount;

        if (availableSlots <= 0) {
            window.App?.showToast("Maximum of 3 photos reached. Remove a photo to add a different one.", true);
            return;
        }

        if (validImages.length > availableSlots) {
            window.App?.showToast(`You may upload up to 3 photos of the same defect. Adding first ${availableSlots} selected photo(s).`, true);
        }

        const toAdd = validImages.slice(0, availableSlots);
        this.selectedFiles = this.selectedFiles.concat(toAdd);
        this.renderImagePreviews();
    },

    renderImagePreviews() {
        const badge = document.getElementById('imageCountBadge');
        const prompt = document.getElementById('dropzonePrompt');
        const grid = document.getElementById('multiPreviewGrid');
        const addRow = document.getElementById('multiAddRow');

        const count = this.selectedFiles.length;
        if (badge) {
            badge.textContent = `${count} / 3 photos`;
        }

        if (count === 0) {
            if (prompt) prompt.classList.remove('hidden');
            if (grid) {
                grid.classList.add('hidden');
                grid.innerHTML = '';
            }
            if (addRow) addRow.classList.add('hidden');
            return;
        }

        if (prompt) prompt.classList.add('hidden');
        if (grid) {
            grid.classList.remove('hidden');
            grid.innerHTML = '';

            this.selectedFiles.forEach((file, idx) => {
                const card = document.createElement('div');
                card.className = 'preview-card';

                const img = document.createElement('img');
                img.alt = `Angle #${idx + 1}`;
                const objectUrl = URL.createObjectURL(file);
                img.src = objectUrl;

                const badgeEl = document.createElement('div');
                badgeEl.className = 'preview-card-badge';
                badgeEl.textContent = `Photo #${idx + 1}`;

                const actions = document.createElement('div');
                actions.className = 'preview-card-actions';

                const removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.className = 'btn-card-remove';
                removeBtn.innerHTML = '✕ Remove';
                removeBtn.title = 'Remove this photo';
                removeBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.removeFile(idx);
                });

                actions.appendChild(removeBtn);
                card.appendChild(img);
                card.appendChild(badgeEl);
                card.appendChild(actions);
                grid.appendChild(card);
            });
        }

        if (addRow) {
            if (count < 3) {
                addRow.classList.remove('hidden');
            } else {
                addRow.classList.add('hidden');
            }
        }

        const relGroup = document.getElementById('multiImageRelationshipGroup');
        if (relGroup) {
            relGroup.classList.toggle('hidden', count <= 1);
        }
    },

    removeFile(index) {
        if (index >= 0 && index < this.selectedFiles.length) {
            this.selectedFiles.splice(index, 1);
            this.renderImagePreviews();
            window.App?.showToast("Photo removed.");
        }
    },

    clearFiles() {
        this.selectedFiles = [];
        const fileInput = document.getElementById('imageFileInput');
        if (fileInput) fileInput.value = '';
        this.renderImagePreviews();
    },

    loadSamplePhoto() {
        const canvas = document.createElement('canvas');
        canvas.width = 640;
        canvas.height = 480;
        const ctx = canvas.getContext('2d');

        // Asphalt road texture
        ctx.fillStyle = '#2b2e38';
        ctx.fillRect(0, 0, 640, 480);

        // Road lane marking
        ctx.strokeStyle = '#e2b024';
        ctx.lineWidth = 12;
        ctx.setLineDash([40, 30]);
        ctx.beginPath();
        ctx.moveTo(320, 0);
        ctx.lineTo(320, 480);
        ctx.stroke();
        ctx.setLineDash([]);

        // Defect cavity texture (Pothole representation)
        ctx.fillStyle = '#14161b';
        ctx.beginPath();
        ctx.ellipse(320, 240, 110, 65, Math.PI / 12, 0, 2 * Math.PI);
        ctx.fill();
        ctx.strokeStyle = '#0a0a0c';
        ctx.lineWidth = 5;
        ctx.stroke();

        // Radiating surface distress fractures
        ctx.strokeStyle = '#1a1c22';
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.moveTo(220, 240);
        ctx.lineTo(130, 260);
        ctx.lineTo(90, 310);
        ctx.moveTo(420, 230);
        ctx.lineTo(510, 210);
        ctx.lineTo(560, 180);
        ctx.stroke();

        canvas.toBlob((blob) => {
            const count = this.selectedFiles.length + 1;
            const file = new File([blob], `sample_pavement_defect_${count}.jpg`, { type: "image/jpeg" });
            this.handleFilesSelected([file]);
            window.App.showToast(`Demonstration infrastructure defect photo #${count} loaded.`);
        }, 'image/jpeg');
    },

    async processAiSubmission() {
        if (!this.selectedFiles || this.selectedFiles.length === 0) {
            window.App.showToast("Please upload at least 1 defect photograph (up to 3 photos allowed).", true);
            return;
        }

        if (this.selectedFiles.length > 3) {
            window.App.showToast("Maximum of 3 photos allowed per report.", true);
            return;
        }

        // Require citizen login
        if (!window.App.currentUser) {
            window.App.showToast("Please sign in or register to submit a defect report.", true);
            window.App.showAuthView('login');
            return;
        }

        const infraType = document.getElementById('infraType').value;
        const location = document.getElementById('defectLocation').value.trim();
        const notes = document.getElementById('defectNotes').value.trim();

        if (!location) {
            window.App.showToast("Defect location is required.", true);
            return;
        }

        const formData = new FormData();
        this.selectedFiles.forEach(file => {
            formData.append('images', file);
        });
        // Backwards compatibility for single-image field expectation
        formData.append('image', this.selectedFiles[0]);
        formData.append('asset_type', infraType);
        formData.append('location', location);
        formData.append('description', notes);

        if (this.selectedFiles.length > 1) {
            const relChoice = document.querySelector('input[name="multiImageRelationship"]:checked')?.value || 'same_defect';
            formData.append('multi_image_mode', relChoice);
        }

        if (this.selectedCoordinates) {
            formData.append('latitude', this.selectedCoordinates.latitude);
            formData.append('longitude', this.selectedCoordinates.longitude);
        }

        const btn = document.getElementById('btnSubmitAiAnalysis');
        const originalText = btn.innerHTML;
        btn.innerHTML = `<span>⏳</span> Analyzing ${this.selectedFiles.length} photo(s) with SSD-MobileNetV2...`;
        btn.disabled = true;

        try {
            const data = await window.Api.submitDefect(formData);
            this.lastAssessment = data;
            this.renderAssessmentResults(data);
            window.App.showToast("Defect analyzed and report recorded successfully.");
            document.getElementById('btnViewTrackingAfterSubmit').disabled = false;
        } catch (err) {
            console.error("Submission failed:", err);
            window.App.showToast(err.message || "Failed to submit defect report.", true);
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    },

    renderAssessmentResults(data) {
        const ai = data.ai_assessment;
        if (!ai) return;

        // Aggregate defect classes across all submitted images if returned
        let defectName = 'None Detected';
        if (data.detected_classes && data.detected_classes.length > 0) {
            defectName = data.detected_classes.join(', ');
        } else if (ai.defect_class && ai.defect_class !== 'None Detected') {
            defectName = ai.defect_class;
        }

        const isSameDefect = (data.multi_image_mode === 'same_defect' || data.report?.metadata?.multi_image_mode === 'same_defect');
        const isMultiDefect = (data.multi_image_mode === 'multi_defect' || data.report?.metadata?.multi_image_mode === 'multi_defect');

        const sev = data.overall_visual_severity || ai.relative_severity || ai.severity || 'Low';
        const sevEl = document.getElementById('resSeverity');
        if (isSameDefect) {
            sevEl.textContent = `[ COMBINED SEVERITY: ${sev.toUpperCase()} ]`;
        } else if (isMultiDefect) {
            sevEl.textContent = `[ CORRIDOR SEVERITY: ${sev.toUpperCase()} ]`;
        } else {
            sevEl.textContent = `[ ${sev.toUpperCase()} ]`;
        }
        sevEl.className = `severity-pill ${sev.toLowerCase()}`;

        document.getElementById('resDefectClass').textContent = defectName;

        // Primary assessment detection metrics
        const allAssessments = data.ai_assessments && data.ai_assessments.length > 0
            ? data.ai_assessments
            : [ai];

        const primaryAssessment = allAssessments[0];
        const detections = (primaryAssessment.detections && primaryAssessment.detections.length > 0)
            ? primaryAssessment.detections
            : (primaryAssessment.defect_class && primaryAssessment.defect_class !== 'None Detected' ? [primaryAssessment] : []);

        const hasDetections = detections.length > 0;
        document.getElementById('resConfidence').textContent = hasDetections
            ? `${primaryAssessment.confidence_percentage || Math.round((primaryAssessment.confidence_score || 0) * 100)}%`
            : '—';

        document.getElementById('resAreaRatio').textContent = hasDetections
            ? `${primaryAssessment.area_percentage || 0.0}% of image extent`
            : '0.0% of image extent';

        // Multi-detection summary badge chips across all images
        const badgeList = document.getElementById('multiDetectionsList');
        if (badgeList) {
            const combinedBadges = [];
            allAssessments.forEach((assItem, imgIdx) => {
                const itemDets = (assItem.detections && assItem.detections.length > 0)
                    ? assItem.detections
                    : (assItem.defect_class && assItem.defect_class !== 'None Detected' ? [assItem] : []);
                itemDets.forEach(d => {
                    const cls = d.class_name || d.defect_class || 'Defect';
                    const confVal = d.confidence !== undefined ? d.confidence : (d.confidence_score || 0);
                    const conf = Math.round(confVal * 100);
                    const dSev = d.severity || d.relative_severity || 'Low';
                    const slug = cls.toLowerCase().includes('crack') ? 'crack' : (cls.toLowerCase().includes('pothole') ? 'pothole' : 'surface');
                    const imgTag = allAssessments.length > 1 ? `[Photo #${imgIdx + 1}] ` : '';
                    combinedBadges.push(`<span class="defect-badge-pill ${slug}">${imgTag}${cls} • ${conf}% Conf • [${dSev} Severity]</span>`);
                });
            });

            if (combinedBadges.length > 0) {
                badgeList.innerHTML = combinedBadges.join('');
            } else {
                badgeList.innerHTML = `<span class="badge-tag" style="background:#f1f5f9; color:#64748b;">No defect detections above threshold</span>`;
            }
        }

        const noticeEl = document.getElementById('noticeText');
        if (noticeEl && ai.disclaimer) {
            noticeEl.textContent = ai.disclaimer;
        }

        // Defect integrity flag for unusual combinations (e.g. Building + Pothole)
        const flagBanner = document.getElementById('unusualDefectBanner');
        const flagMsgEl = document.getElementById('unusualDefectMessage');
        if (flagBanner && flagMsgEl) {
            if (data.validation && data.validation.is_unusual) {
                flagBanner.classList.remove('hidden');
                flagMsgEl.textContent = data.validation.validation_message
                    || (data.validation.flag_reasons && data.validation.flag_reasons.length > 0 ? data.validation.flag_reasons.join(' • ') : '')
                    || 'Unusual defect-infrastructure pairing detected. Retained under canonical status Received for certified civil engineer review.';
            } else {
                flagBanner.classList.add('hidden');
            }
        }

        // Render Canvas Bounding Box with primary image
        const primaryImage = data.image || (data.images && data.images[0]);
        if (primaryImage) {
            this.drawBoundingBoxOnCanvas(primaryImage.url, primaryAssessment);
        }
    },

    drawBoundingBoxOnCanvas(imageUrl, aiData) {
        const canvas = document.getElementById('detectionCanvas');
        const placeholder = document.getElementById('canvasPlaceholder');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        const resolvedUrl = window.Api?.resolveImageUrl(imageUrl) || imageUrl;

        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => {
            if (placeholder) placeholder.classList.add('hidden');

            const origW = img.naturalWidth || img.width;
            const origH = img.naturalHeight || img.height;
            canvas.width = origW;
            canvas.height = origH;
            ctx.drawImage(img, 0, 0, origW, origH);

            const detections = (aiData.detections && aiData.detections.length > 0)
                ? aiData.detections
                : (aiData.defect_class && aiData.defect_class !== 'None Detected' ? [aiData] : []);

            if (detections.length === 0) {
                // Zero detections overlay banner
                const bannerH = Math.max(40, Math.round(origH * 0.08));
                ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
                ctx.fillRect(0, 0, origW, bannerH);
                ctx.fillStyle = '#10b981';
                const fontSize = Math.max(14, Math.round(origW * 0.024));
                ctx.font = `600 ${fontSize}px "Inter", sans-serif`;
                ctx.fillText('[ ✓ No Structural Defects Detected (Confidence >= 30%) ]', 16, Math.round(bannerH * 0.65));
                return;
            }

            // Render responsive bounding boxes for each detection
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
                const color = defectClass === 'Pothole' ? '#ef4444' : (defectClass === 'Crack' ? '#f59e0b' : '#06b6d4');

                // Responsive stroke width
                const lineWidth = Math.max(3, Math.round(origW / 240));
                ctx.strokeStyle = color;
                ctx.lineWidth = lineWidth;
                ctx.setLineDash([lineWidth * 2, lineWidth]);
                ctx.strokeRect(xmin, ymin, boxW, boxH);
                ctx.setLineDash([]);

                // Label background pill with smart edge-clamping and collision handling
                const confVal = det.confidence !== undefined ? det.confidence : (det.confidence_score || 0.0);
                const confText = Math.round(confVal * 100);
                const sevVal = det.severity || det.relative_severity || '';
                const labelText = sevVal
                    ? `[ ${defectClass} • ${confText}% • ${sevVal} ]`
                    : `[ ${defectClass} • ${confText}% ]`;

                const fontSize = Math.max(13, Math.round(origW * 0.022));
                ctx.font = `bold ${fontSize}px "JetBrains Mono", monospace`;
                const textWidth = ctx.measureText(labelText).width;
                const pillW = textWidth + 16;
                const pillH = fontSize + 12;

                // Clamp horizontally within image bounds
                const pillX = Math.max(2, Math.min(origW - pillW - 2, xmin));

                // Position label above box if space permits, else inside top edge of box
                let pillY = (ymin >= pillH + 4) ? (ymin - pillH - 2) : (ymin + lineWidth + 2);

                // Anti-collision offset for multiple overlapping labels
                if (!window._drawnPills) window._drawnPills = [];
                for (const prev of window._drawnPills) {
                    if (Math.abs(prev.x - pillX) < pillW * 0.7 && Math.abs(prev.y - pillY) < pillH) {
                        pillY = prev.y + pillH + 4;
                    }
                }
                window._drawnPills.push({ x: pillX, y: pillY, w: pillW, h: pillH });

                ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
                ctx.fillRect(pillX, pillY, pillW, pillH);
                ctx.strokeStyle = color;
                ctx.lineWidth = 1;
                ctx.strokeRect(pillX, pillY, pillW, pillH);

                ctx.fillStyle = color;
                ctx.fillText(labelText, pillX + 8, pillY + fontSize + 2);
            });
            window._drawnPills = [];
        };

        img.onerror = () => {
            if (placeholder) placeholder.classList.add('hidden');
            const placeholderW = 640;
            const placeholderH = 400;
            canvas.width = placeholderW;
            canvas.height = placeholderH;
            ctx.fillStyle = '#0f172a';
            ctx.fillRect(0, 0, placeholderW, placeholderH);
            ctx.fillStyle = '#f59e0b';
            ctx.font = 'bold 15px "Inter", sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('📷 Evidence image unavailable', 320, 185);
            ctx.fillStyle = '#94a3b8';
            ctx.font = '12px "Inter", sans-serif';
            ctx.fillText('Source photographic file could not be loaded.', 320, 215);
        };

        img.src = resolvedUrl;
    }
};

window.Submission = Submission;
