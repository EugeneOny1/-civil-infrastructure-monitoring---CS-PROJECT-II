/**
 * InfraVision Map Module - Interactive Civil Infrastructure Defect Map
 * Powered by Google Maps JavaScript API with Advanced Markers / Clustering (@googlemaps/markerclusterer).
 *
 * Defaults:
 *   Center: Nairobi, Kenya (Latitude: -1.286389, Longitude: 36.817223)
 *   Zoom: 12
 *
 * Privacy:
 *   Strips private citizen identities (names, emails, phone numbers) to safeguard privacy.
 */

// Source: Google Maps Platform Code Assist
const DefectMap = {
    mapInstance: null,
    markers: [],
    clusterer: null,
    infoWindow: null,
    reportsData: [],
    apiKey: '',
    defaultCenter: { lat: -1.286389, lng: 36.817223 },
    defaultZoom: 12,
    activeFilters: {
        defect_class: '',
        status: '',
        severity: '',
        asset_type: ''
    },
    isScriptLoading: false,

    async init() {
        this.bindEvents();
        await this.loadConfig();
        await this.loadMapData();
    },

    bindEvents() {
        const classFilter = document.getElementById('mapFilterClass');
        const statusFilter = document.getElementById('mapFilterStatus');
        const severityFilter = document.getElementById('mapFilterSeverity');
        const assetFilter = document.getElementById('mapFilterAsset');
        const refreshBtn = document.getElementById('btnRefreshMap');
        const resetBtn = document.getElementById('btnResetMapFilters');

        if (classFilter) {
            classFilter.addEventListener('change', (e) => {
                this.activeFilters.defect_class = e.target.value;
                this.loadMapData();
            });
        }
        if (statusFilter) {
            statusFilter.addEventListener('change', (e) => {
                this.activeFilters.status = e.target.value;
                this.loadMapData();
            });
        }
        if (severityFilter) {
            severityFilter.addEventListener('change', (e) => {
                this.activeFilters.severity = e.target.value;
                this.loadMapData();
            });
        }
        if (assetFilter) {
            assetFilter.addEventListener('change', (e) => {
                this.activeFilters.asset_type = e.target.value;
                this.loadMapData();
            });
        }
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.loadMapData();
                window.App.showToast("Refreshed infrastructure map data.");
            });
        }
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                this.resetFilters();
            });
        }
    },

    resetFilters() {
        this.activeFilters = {
            defect_class: '',
            status: '',
            severity: '',
            asset_type: ''
        };
        const classFilter = document.getElementById('mapFilterClass');
        const statusFilter = document.getElementById('mapFilterStatus');
        const severityFilter = document.getElementById('mapFilterSeverity');
        const assetFilter = document.getElementById('mapFilterAsset');

        if (classFilter) classFilter.value = '';
        if (statusFilter) statusFilter.value = '';
        if (severityFilter) severityFilter.value = '';
        if (assetFilter) assetFilter.value = '';

        this.loadMapData();
    },

    async loadConfig() {
        try {
            const config = await window.Api.getMapConfig();
            if (config && config.api_key) {
                this.apiKey = config.api_key;
            }
            if (config && config.default_center) {
                this.defaultCenter = config.default_center;
            }
            if (config && config.default_zoom) {
                this.defaultZoom = config.default_zoom;
            }
        } catch (e) {
            console.warn("[DefectMap] Could not fetch map config from backend:", e);
        }

        // Check local override or demo key saved by user in session
        const localKey = localStorage.getItem('GOOGLE_MAPS_API_KEY') || sessionStorage.getItem('GOOGLE_MAPS_API_KEY');
        if (localKey) {
            this.apiKey = localKey.trim();
        }
    },

    ensureGoogleMapsLoaded() {
        if (window.google && window.google.maps) {
            return Promise.resolve(true);
        }

        if (!this.apiKey) {
            return Promise.resolve(false);
        }

        if (this.isScriptLoading) {
            return new Promise((resolve) => {
                const interval = setInterval(() => {
                    if (window.google && window.google.maps) {
                        clearInterval(interval);
                        resolve(true);
                    }
                }, 100);
                setTimeout(() => {
                    clearInterval(interval);
                    resolve(Boolean(window.google && window.google.maps));
                }, 10000);
            });
        }

        this.isScriptLoading = true;

        return new Promise((resolve) => {
            // Global auth failure hook
            window.gm_authFailure = () => {
                console.error("[DefectMap] Google Maps authentication failed. Key may be restricted, expired, or lack Maps JavaScript API permissions.");
                const container = document.getElementById('infrastructureMapContainer');
                if (container) {
                    this.renderConfigurationState(container, "Google Maps Authentication Failed: The API key entered was rejected by Google Cloud. Please verify key restrictions and enable the 'Maps JavaScript API'.");
                }
            };

            const script = document.createElement('script');
            script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(this.apiKey)}&v=weekly&libraries=marker`;
            script.async = true;
            script.defer = true;
            script.onload = () => {
                this.isScriptLoading = false;
                resolve(true);
            };
            script.onerror = () => {
                this.isScriptLoading = false;
                console.error("[DefectMap] Failed loading Google Maps JavaScript API script.");
                resolve(false);
            };
            document.head.appendChild(script);
        });
    },

    async loadMapData() {
        const container = document.getElementById('infrastructureMapContainer');
        if (!container) return;

        try {
            // Fetch real reports with valid geographic coordinates from backend MongoDB
            const data = await window.Api.getMapPoints(this.activeFilters);
            this.reportsData = data.points || [];

            const countEl = document.getElementById('mapReportCount');
            if (countEl) countEl.textContent = `${this.reportsData.length} Pinpoints`;

            // Try loading Google Maps JS API
            const hasGoogle = await this.ensureGoogleMapsLoaded();

            if (hasGoogle && window.google && window.google.maps) {
                this.renderGoogleMap(container, this.reportsData);
            } else {
                this.renderConfigurationState(container);
            }
        } catch (err) {
            console.error("[DefectMap] Failed loading map points:", err);
            container.innerHTML = `
                <div class="map-config-card">
                    <div class="map-config-icon" style="color:#ef4444;">⚠️</div>
                    <h3 class="map-config-title">Infrastructure Map Offline</h3>
                    <p class="map-config-desc">Failed to connect to the backend defect reports service. Please verify server connectivity.</p>
                </div>`;
        }
    },

    renderConfigurationState(container, customError = '') {
        container.innerHTML = `
            <div class="map-config-card">
                <div class="map-config-icon">🗺️</div>
                <h3 class="map-config-title">Google Maps Platform Configuration</h3>
                <p class="map-config-desc">
                    The InfraVision defect monitoring map renders an interactive geographic view of Nairobi infrastructure corridors 
                    using the <strong>Google Maps JavaScript API</strong> with marker clustering and real-time defect inspection.
                </p>

                ${customError ? `<div style="background:#fef2f2; border:1px solid #fecaca; color:#b91c1c; padding:0.75rem 1rem; border-radius:6px; font-size:0.8rem; margin-bottom:1rem; max-width:540px; text-align:left;"><strong>Configuration Alert:</strong> ${customError}</div>` : ''}

                <div class="map-config-box">
                    <h4>⚙️ External Setup Instructions:</h4>
                    <ol>
                        <li>In your project root, open <code>backend/.env</code> and configure: <br><code>GOOGLE_MAPS_API_KEY=YOUR_ACTUAL_KEY</code></li>
                        <li>Enable the <strong>Maps JavaScript API</strong> in your <a href="https://console.cloud.google.com/google/maps-apis/overview" target="_blank" style="color:#0284c7; text-decoration:underline;">Google Cloud Console</a>.</li>
                        <li><strong>For Prototyping / Development:</strong> You may also use a free <a href="https://mapsplatform.google.com/maps-demo-key" target="_blank" style="color:#0284c7; text-decoration:underline;">Google Maps Demo Key</a> without billing setup.</li>
                    </ol>
                </div>

                <div class="map-key-form">
                    <input type="text" id="inlineMapKeyInput" class="map-key-input" placeholder="Paste Google Maps API key or Demo Key here..." value="${this.apiKey || ''}">
                    <button type="button" class="btn-primary btn-sm" id="btnApplyInlineKey">Apply Key & Load Map</button>
                </div>

                <div style="font-size: 0.75rem; color: #64748b; margin-top: 1rem;">
                    Default Center: <strong>Nairobi, Kenya</strong> (Latitude: -1.286389, Longitude: 36.817223) • Zoom: 12
                </div>
            </div>
        `;

        const applyBtn = document.getElementById('btnApplyInlineKey');
        const keyInput = document.getElementById('inlineMapKeyInput');
        if (applyBtn && keyInput) {
            applyBtn.addEventListener('click', async () => {
                const enteredKey = keyInput.value.trim();
                if (!enteredKey) {
                    window.App.showToast("Please enter a valid Google Maps API Key or Demo Key.", true);
                    return;
                }
                this.apiKey = enteredKey;
                localStorage.setItem('GOOGLE_MAPS_API_KEY', enteredKey);
                window.App.showToast("Loading Google Maps JavaScript API...");
                applyBtn.disabled = true;
                applyBtn.textContent = "Loading Map...";
                this.isScriptLoading = false;
                await this.loadMapData();
            });
        }
    },

    renderGoogleMap(container, points) {
        // Clear any previous configuration card from container
        if (!container.querySelector('.gm-style')) {
            container.innerHTML = '';
        }

        // Initialize Google Map with Nairobi default center
        if (!this.mapInstance || !container.querySelector('.gm-style')) {
            this.mapInstance = new google.maps.Map(container, {
                zoom: this.defaultZoom,
                center: this.defaultCenter,
                mapTypeId: google.maps.MapTypeId.ROADMAP,
                mapTypeControl: true,
                mapTypeControlOptions: {
                    style: google.maps.MapTypeControlStyle.HORIZONTAL_BAR,
                    position: google.maps.ControlPosition.TOP_RIGHT
                },
                streetViewControl: true,
                fullscreenControl: true,
                zoomControl: true,
                styles: [
                    { featureType: 'poi.business', stylers: [{ visibility: 'off' }] },
                    { featureType: 'transit', stylers: [{ visibility: 'simplified' }] }
                ]
            });

            this.infoWindow = new google.maps.InfoWindow();
        }

        // Clear existing markers and clusterer
        if (this.clusterer) {
            this.clusterer.clearMarkers();
        }
        this.markers.forEach(m => m.setMap(null));
        this.markers = [];

        // Check if there are no matching reports
        const hasFilters = Boolean(
            this.activeFilters.defect_class ||
            this.activeFilters.status ||
            this.activeFilters.severity ||
            this.activeFilters.asset_type
        );

        let emptyNotice = document.getElementById('mapEmptyNotice');
        if (points.length === 0) {
            if (!emptyNotice) {
                emptyNotice = document.createElement('div');
                emptyNotice.id = 'mapEmptyNotice';
                emptyNotice.className = 'map-empty-overlay';
                container.appendChild(emptyNotice);
            }
            emptyNotice.style.display = 'block';
            emptyNotice.textContent = hasFilters
                ? 'No defect reports match the selected filters.'
                : 'No infrastructure defect reports exist yet. Use "Report Defect" to submit one.';
            return;
        } else if (emptyNotice) {
            emptyNotice.style.display = 'none';
        }

        // Create markers from real backend report points
        const bounds = new google.maps.LatLngBounds();

        points.forEach(pt => {
            const sev = (pt.relative_severity || 'Low').toLowerCase();
            const color = sev === 'critical' ? '#ef4444' : (sev === 'medium' ? '#f59e0b' : '#10b981');

            const marker = new google.maps.Marker({
                position: { lat: pt.latitude, lng: pt.longitude },
                title: `${pt.defect_class || 'Distress'} [${(pt.relative_severity || 'Low').toUpperCase()}]`,
                icon: {
                    path: google.maps.SymbolPath.CIRCLE,
                    scale: 9,
                    fillColor: color,
                    fillOpacity: 0.95,
                    strokeWeight: 2,
                    strokeColor: '#ffffff'
                }
            });

            // Marker click handler: displays sanitized defect inspection card (NO citizen PII)
            marker.addListener('click', () => {
                const dateStr = pt.date_submitted ? new Date(pt.date_submitted).toLocaleDateString() : 'Recent';
                const statusSlug = (pt.status || 'Received').toLowerCase().replace(/\s+/g, '-');
                const frameId = (pt.report_id || '').slice(0, 16);

                const contentHtml = `
                    <div class="map-popup-card">
                        <div class="map-popup-title">${pt.defect_class || 'Infrastructure Defect'}</div>
                        <div class="map-popup-meta">${pt.asset_type || 'Civil Asset'} • ${pt.location_name || 'Corridor'}</div>
                        <div style="margin: 0.4rem 0; display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap;">
                            <span class="status-chip ${statusSlug}">${pt.status || 'Received'}</span>
                            <span class="severity-pill ${sev}">${(pt.relative_severity || 'Low').toUpperCase()}</span>
                            ${pt.is_unusual ? `<span class="badge-tag" style="background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;font-size:0.7rem;">⚠️ Unusual</span>` : ''}
                        </div>
                        <div style="font-size:0.75rem; color:#64748b; line-height: 1.4; margin-top:0.35rem;">
                            <strong>Case:</strong> #${frameId}<br>
                            <strong>GPS:</strong> ${pt.latitude.toFixed(5)}°, ${pt.longitude.toFixed(5)}°<br>
                            <strong>Date:</strong> ${dateStr}
                        </div>
                        <div style="margin-top:0.5rem; font-size:0.68rem; color:#94a3b8; border-top:1px solid #f1f5f9; padding-top:0.3rem;">
                            🔒 Reporter Privacy Protected • Verified Public Record
                        </div>
                    </div>
                `;

                this.infoWindow.setContent(contentHtml);
                this.infoWindow.open(this.mapInstance, marker);
            });

            this.markers.push(marker);
            bounds.extend({ lat: pt.latitude, lng: pt.longitude });
        });

        // Initialize Marker Clustering via @googlemaps/markerclusterer
        if (window.markerClusterer && window.markerClusterer.MarkerClusterer) {
            this.clusterer = new window.markerClusterer.MarkerClusterer({
                map: this.mapInstance,
                markers: this.markers
            });
        } else {
            // Fallback: place markers directly on map if clusterer library was not available
            this.markers.forEach(m => m.setMap(this.mapInstance));
        }

        // Keep view reasonable
        if (points.length === 1) {
            this.mapInstance.setCenter({ lat: points[0].latitude, lng: points[0].longitude });
            this.mapInstance.setZoom(14);
        } else if (points.length > 1) {
            this.mapInstance.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
        }
    }
};

window.DefectMap = DefectMap;
